"""Binding, daily window, verified extraction, and report completion for WorkBuddy.

Standard library only. This helper does not generate clinical summaries or schedule jobs.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))
TEMPLATE_CONFIG = Path(__file__).resolve().parents[1] / "config.json"
DEFAULT_CONFIG = Path.home() / ".workbuddy" / "patient-daily-summary" / "config.json"


def load_config(path):
    path = Path(path).expanduser().resolve()
    if path.exists():
        return read_json(path)
    if path == DEFAULT_CONFIG.resolve():
        return read_json(TEMPLATE_CONFIG)
    raise ValueError("指定配置不存在：" + str(path))


def resolve_paths(cfg):
    cfg = copy.deepcopy(cfg)
    base = Path.home() / ".workbuddy"
    output = base / "patient-daily-summary" / "output"
    defaults = {
        "py": sys.executable,
        "wx_daily": base / "skills" / "wx4-chat-reader" / "scripts" / "wx_daily.py",
        "wx_find": base / "skills" / "wx4-chat-reader" / "scripts" / "wx_find.py",
        "workdir": base / "patient-daily-summary" / "cache",
        "out": output, "latest": output / "latest.md", "reports": output / "reports",
    }
    paths = cfg.setdefault("paths", {})
    for key, value in defaults.items():
        paths[key] = os.path.expandvars(os.path.expanduser(paths.get(key) or str(value)))
    paths["data_root"] = os.path.expandvars(os.path.expanduser(paths.get("data_root") or ""))
    return cfg


def check_paths(cfg):
    errors = []
    for key in ("py", "wx_daily"):
        if not Path(cfg["paths"][key]).is_file():
            errors.append(key + " 文件不存在")
    data = cfg["paths"].get("data_root")
    if not data or not Path(data).is_dir():
        errors.append("data_root 必须设置为本机微信数据目录")
    if errors:
        raise ValueError("；".join(errors))



def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fingerprint(cfg):
    relevant = {key: cfg[key] for key in ("ward", "beds", "sources", "window")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()


def binding_report(cfg):
    """List what is still missing before any window work may run."""
    missing = []
    if not str(cfg.get("ward", "")).strip():
        missing.append("ward（病区/单元名称）")
    beds = cfg.get("beds") or []
    if not isinstance(beds, list):
        raise ValueError("beds 必须为数组")
    if not beds:
        missing.append("beds（至少一张关注床位）")
    elif any(isinstance(bed, bool) or not isinstance(bed, int) or bed <= 0 for bed in beds):
        missing.append("beds（床号必须为正整数）")
    sources = cfg.get("sources") or []
    if not isinstance(sources, list) or any(not isinstance(s, dict) for s in sources):
        raise ValueError("sources 必须为对象数组")
    if not sources:
        missing.append("sources（至少一个会话来源）")
    else:
        names = [str(item.get("name", "")).strip() for item in sources]
        wxids = [str(item.get("wxid", "")).strip() for item in sources]
        if not all(names) or not all(wxids):
            missing.append("sources（每项都要有 wxid 与显示名）")
        if any(not isinstance(s.get(k), str) for s in sources for k in ("wxid", "name")):
            raise ValueError("来源 wxid 和显示名必须为字符串")
        if any(re.search(r"[\r\n|]", n) for n in names) or any(re.search(r"\s", w) for w in wxids):
            raise ValueError("来源名称不能含换行或竖线，wxid 不能含空白")
        if len(set(names)) != len(names):
            missing.append("sources（显示名必须唯一）")
        if len(set(wxids)) != len(wxids):
            missing.append("sources（wxid 重复）")
    return missing


def parse_beds(text):
    beds = []
    for token in re.split(r"[\s,，、]+", text.strip()):
        if not token:
            continue
        if not token.isdigit():
            raise ValueError("床号必须是数字：" + token)
        if int(token) <= 0:
            raise ValueError("床号必须为正整数")
        beds.append(int(token))
    if not beds:
        raise ValueError("未提供床号")
    return sorted(set(beds))


def split_source(text):
    if "|" in text:
        wxid, name = text.split("|", 1)
    else:
        parts = text.split(None, 1)
        if len(parts) != 2:
            raise ValueError("来源格式应为 '<wxid> <显示名>' 或 '<wxid>|<显示名>'：" + text)
        wxid, name = parts
    wxid, name = wxid.strip(), name.strip()
    if not wxid or not name:
        raise ValueError("来源的 wxid 与显示名都不能为空：" + text)
    return {"wxid": wxid, "name": name}


def bind(cfg, config_path, args):
    """Write bed and source bindings supplied by the user into the config file."""
    cfg = copy.deepcopy(cfg)
    changed = []
    if args.ward is not None:
        cfg["ward"] = args.ward.strip()
        changed.append("ward")
    if args.beds is not None:
        cfg["beds"] = parse_beds(args.beds)
        changed.append("beds")
    for item in args.add_source or []:
        entry = split_source(item)
        sources = cfg.setdefault("sources", [])
        if any(str(s.get("wxid")) == entry["wxid"] for s in sources):
            raise ValueError("来源已存在：" + entry["wxid"])
        sources.append(entry)
        changed.append("add-source " + entry["wxid"])
    for wxid in args.remove_source or []:
        target = wxid.strip()
        sources = cfg.get("sources") or []
        kept = [s for s in sources if str(s.get("wxid")) != target]
        if len(kept) == len(sources):
            raise ValueError("未找到来源：" + target)
        cfg["sources"] = kept
        changed.append("remove-source " + target)
    if args.start_hour is not None:
        if not 0 <= args.start_hour <= 23:
            raise ValueError("start_hour must be 0..23")
        cfg.setdefault("window", {})["start_hour"] = args.start_hour
        changed.append("window.start_hour")
    if args.exclude_note is not None:
        cfg["exclude_note"] = args.exclude_note.strip()
        changed.append("exclude_note")
    if args.data_root is not None:
        cfg.setdefault("paths", {})["data_root"] = args.data_root.strip()
        changed.append("paths.data_root")
    missing = binding_report(cfg)
    # Allow incremental setup, but never persist malformed values or duplicate sources.
    invalid = [item for item in missing if item not in (
        "ward（病区/单元名称）", "beds（至少一张关注床位）", "sources（至少一个会话来源）")]
    if invalid:
        raise ValueError("；".join(invalid))
    if changed and Path(config_path).resolve() == TEMPLATE_CONFIG.resolve():
        raise ValueError("共享模板不可写入绑定；请省略 --config 使用个人配置")
    if changed:
        atomic_write(config_path, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    missing = binding_report(cfg)
    return {
        "status": "bound" if not missing else "unbound",
        "config": str(config_path),
        "changed": changed,
        "missing": missing,
        "ward": cfg.get("ward", ""),
        "beds": cfg.get("beds", []),
        "sources": [{"wxid": s.get("wxid"), "name": s.get("name")} for s in cfg.get("sources") or []],
    }


def plan(cfg, now=None, stat_date=None):
    now = now or datetime.now(BEIJING)
    if now.tzinfo is None:
        raise ValueError("now must have an explicit timezone")
    now = now.astimezone(BEIJING)
    hour = int(cfg["window"]["start_hour"])
    if not 0 <= hour <= 23:
        raise ValueError("start_hour must be 0..23")
    if stat_date:
        start = datetime.strptime(stat_date, "%Y-%m-%d").replace(tzinfo=BEIJING, hour=hour)
        end = start + timedelta(days=1)
        if end > now:
            raise ValueError("Requested window is not closed yet")
    else:
        end = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    result = {
        "stat_date": start.strftime("%Y-%m-%d"),
        "since": start.strftime("%Y-%m-%d %H:%M"),
        "until": end.strftime("%Y-%m-%d %H:%M"),
        "timezone": "Asia/Shanghai", "fingerprint": fingerprint(cfg),
        "status": "due" if now >= end else "not_due",
    }
    root = Path(cfg["paths"]["reports"])
    result["report"] = str(root / (result["stat_date"] + ".md"))
    result["receipt"] = str(root / (result["stat_date"] + ".complete.json"))
    result["manifest"] = str(root / (result["stat_date"] + ".capture.json"))
    if result["status"] == "due" and Path(result["receipt"]).exists():
        try:
            receipt = read_json(result["receipt"])
            if not isinstance(receipt, dict):
                receipt = {}
        except (ValueError, OSError):
            receipt = {}
        report = Path(result["report"])
        if (receipt.get("fingerprint") == result["fingerprint"] and report.exists()
                and receipt.get("sha256") == hashlib.sha256(report.read_bytes()).hexdigest()):
            result["status"] = "complete"
    return result


def source_status(text, sources):
    # Inspect only the exporter's status footer, not quoted patient messages.
    footer = text.rsplit("\n## 本次读取状态\n", 1)
    if len(footer) != 2:
        raise RuntimeError("Missing extraction status footer")
    statuses = {}
    for source in sources:
        prefix = "- " + source["name"] + "："
        matches = [line for line in footer[1].splitlines() if line.startswith(prefix)]
        if len(matches) != 1:
            raise RuntimeError("Missing or ambiguous source status: " + source["name"])
        statuses[source["wxid"]] = matches[0][len(prefix):].startswith("读取成功")
    return statuses


def scrape(cfg, job):
    if job["status"] != "due":
        return job
    check_paths(cfg)
    paths = cfg["paths"]
    # Never allow a failed fresh attempt to leave a usable completion manifest.
    Path(job["manifest"]).unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(WX_DATA_ROOT=paths["data_root"], WX_WORKDIR=paths["workdir"],
               WX_SOURCES=json.dumps([[s["wxid"], s["name"]] for s in cfg["sources"]], ensure_ascii=False),
               PYTHONIOENCODING="utf-8", TZ="Asia/Shanghai")
    # wx_daily uses naive datetime.timestamp/fromtimestamp. Enforce its Windows
    # local timezone requirement instead of silently exporting the wrong window.
    for value in (job["since"], job["until"]):
        local = datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()
        if local.utcoffset() != timedelta(hours=8):
            raise RuntimeError("wx_daily requires the Windows timezone to be UTC+08:00")
    command = [paths["py"], paths["wx_daily"], "--since", job["since"],
               "--until", job["until"], "--out", paths["out"]]
    proc = subprocess.run(command, env=env, capture_output=True, encoding="utf-8",
                          errors="replace", timeout=int(cfg["schedule"]["scrape_timeout_seconds"]))
    log = proc.stdout + "\n" + proc.stderr
    if proc.returncode or "Traceback (most recent call last)" in log:
        raise RuntimeError("Extraction failed: " + log[-3000:])
    files = re.findall(r"^OUT_FILE=(.+)$", proc.stdout, flags=re.M)
    if len(files) != 1:
        raise RuntimeError("Extractor did not return exactly one output file")
    raw_path = Path(files[0].strip()).resolve()
    if not raw_path.is_file() or Path(paths["out"]).resolve() not in raw_path.parents:
        raise RuntimeError("Invalid extraction output path")
    raw = raw_path.read_text(encoding="utf-8-sig")
    expected = "# 抓取范围 " + job["since"] + " ~ " + job["until"] + "（北京时间）"
    if not raw.splitlines() or raw.splitlines()[0] != expected:
        raise RuntimeError("Extraction window does not match this run")
    statuses = source_status(raw, cfg["sources"])
    manifest = dict(job, raw=str(raw_path), sources=statuses,
                    raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                    captured_at=datetime.now(BEIJING).isoformat())
    atomic_write(job["manifest"], json.dumps(manifest, ensure_ascii=False, indent=2))
    if not all(statuses.values()):
        raise RuntimeError("Some sources failed; inspect capture manifest/raw file. Retry later.")
    atomic_write(paths["latest"], raw)
    return dict(job, raw=str(raw_path), latest=paths["latest"])


def complete(cfg, job):
    if job["status"] == "complete":
        return job
    if job["status"] == "not_due":
        raise RuntimeError("Window is not closed")
    manifest = read_json(job["manifest"])
    for key in ("since", "until", "fingerprint"):
        if manifest.get(key) != job[key]:
            raise RuntimeError("Capture manifest does not match current job")
    if (set(manifest["sources"]) != {s["wxid"] for s in cfg["sources"]}
            or not all(manifest["sources"].values())):
        raise RuntimeError("Cannot complete a report with missing sources")
    raw = Path(manifest["raw"])
    if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest["raw_sha256"]:
        raise RuntimeError("Captured data changed")
    report = Path(job["report"])
    content = report.read_text(encoding="utf-8-sig")
    if ("| 床号 | 时间、情况与处理 | 消息来源 |" not in content
            or job["since"] not in content or job["until"] not in content):
        raise RuntimeError("Report must contain the three-column table and exact window")
    receipt = dict(job, completed_at=datetime.now(BEIJING).isoformat(),
                   sha256=hashlib.sha256(report.read_bytes()).hexdigest())
    atomic_write(job["receipt"], json.dumps(receipt, ensure_ascii=False, indent=2))
    return dict(job, status="complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bind", "plan", "scrape", "complete"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--date", help="Explicit historical start date; only on user request")
    parser.add_argument("--ward", help="病区/单元名称")
    parser.add_argument("--beds", help="关注床号，逗号或空格分隔，如 '2 4 6'（虚构示例）")
    parser.add_argument("--add-source", action="append", help="'<wxid> <显示名>' 形式的会话来源")
    parser.add_argument("--remove-source", action="append", help="要移除的会话 wxid")
    parser.add_argument("--start-hour", type=int, help="统计起点小时，0..23")
    parser.add_argument("--exclude-note", help="易混淆会话的排除说明")
    parser.add_argument("--data-root", help="本机微信数据目录，仅用于 bind")
    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
        if args.action == "bind":
            print(json.dumps(bind(cfg, args.config, args), ensure_ascii=False, indent=2))
            return 0
        missing = binding_report(cfg)
        if missing:
            print(json.dumps({"status": "unbound", "missing": missing,
                              "hint": "先完成床位与来源绑定：见 references/binding.md 或 -Action bind"},
                             ensure_ascii=False), file=sys.stderr)
            return 1
        cfg = resolve_paths(cfg)
        job = plan(cfg, stat_date=args.date)
        result = {"plan": lambda: job, "scrape": lambda: scrape(cfg, job),
                  "complete": lambda: complete(cfg, job)}[args.action]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
