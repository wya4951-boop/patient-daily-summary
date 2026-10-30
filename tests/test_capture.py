import importlib.util
import json
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import subprocess

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('daily_state', root / 'scripts/daily_state.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
cfg = m.resolve_paths(m.read_json(root / 'config.json'))
cfg.update(ward='虚构', beds=[2,4], sources=[{'wxid':'a','name':'测试甲'},{'wxid':'b','name':'测试乙'}])
m.check_paths = lambda cfg: None  # Extraction is mocked; dependency validation is tested separately.
checks = []
with tempfile.TemporaryDirectory() as temp:
    cfg['paths']['reports'] = str(Path(temp) / 'reports')
    cfg['paths']['out'] = str(Path(temp) / 'raw')
    cfg['paths']['latest'] = str(Path(temp) / 'latest.md')
    now = lambda value: datetime.fromisoformat(value + '+08:00')
    before = m.plan(cfg, now('2026-10-28T06:59:59'))
    assert before['status'] == 'not_due'
    job = m.plan(cfg, now('2026-10-28T07:00:00'))
    assert job['since'] == '2026-10-27 07:00' and job['until'] == '2026-10-28 07:00'
    assert m.plan(cfg, now('2026-10-28T23:59:00'))['since'] == job['since']
    assert m.plan(cfg, now('2026-10-30T09:00:00'))['since'] == '2026-10-29 07:00'
    checks += ['07:00 boundary and same-day catch-up', 'no multi-day backlog replay']
    assert m.plan(cfg, now('2026-10-28T08:00:00'), '2026-10-20')['since'] == '2026-10-20 07:00'
    try:
        m.plan(cfg, now('2026-10-28T08:00:00'), '2026-10-28')
        raise AssertionError('future window accepted')
    except ValueError:
        pass
    checks.append('explicit historical request and future-window rejection')
    raw = Path(cfg['paths']['out']) / 'test.md'
    raw.parent.mkdir(parents=True)
    def payload(fail=False):
        return '# 抓取范围 ' + job['since'] + ' ~ ' + job['until'] + '（北京时间）\n\n## 本次读取状态\n' + '\n'.join('- ' + s['name'] + '：' + ('**读取失败**' if fail and i == 0 else '读取成功，但统计时段内无消息（未检索到相关记录）') for i,s in enumerate(cfg['sources']))
    raw.write_text(payload(), encoding='utf-8')
    completed_process = subprocess.CompletedProcess([], 0, 'OUT_FILE=' + str(raw) + '\n', '')
    with patch.object(m.subprocess, 'run', return_value=completed_process):
        result = m.scrape(cfg, job)
        assert Path(result['latest']).exists()
    assert not Path(job['receipt']).exists()
    checks.append('successful capture alone does not complete report')
    Path(job['report']).write_text(job['since'] + ' 至 ' + job['until'] + '\n| 床号 | 时间、情况与处理 | 消息来源 |\n| -- | -- | -- |\n| 2床 | 未检索到相关记录 | 来源 |', encoding='utf-8')
    m.complete(cfg, job)
    assert m.plan(cfg, now('2026-10-28T09:00:00'))['status'] == 'complete'
    Path(job['report']).write_text('corrupt', encoding='utf-8')
    assert m.plan(cfg, now('2026-10-28T09:00:00'))['status'] == 'due'
    checks.append('completion receipt and changed-report detection')
    raw.write_text(payload(True), encoding='utf-8')
    with patch.object(m.subprocess, 'run', return_value=completed_process):
        try:
            m.scrape(cfg, job)
            raise AssertionError('partial source accepted')
        except RuntimeError:
            pass
    try:
        m.complete(cfg, job)
        raise AssertionError('partial source completed')
    except RuntimeError:
        pass
    checks.append('zero exit code with partial source failure cannot complete')
    with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'failed')):
        try:
            m.scrape(cfg, job)
            raise AssertionError('failed extraction accepted')
        except RuntimeError:
            pass
    assert not Path(job['manifest']).exists()
    checks.append('failure invalidates previous capture manifest')
    raw.write_text(payload().replace(job['since'], '2026-10-26 07:00'), encoding='utf-8')
    with patch.object(m.subprocess, 'run', return_value=completed_process):
        try:
            m.scrape(cfg, job)
            raise AssertionError('stale window accepted')
        except RuntimeError:
            pass
    checks.append('stale extraction rejected')
print(json.dumps({'passed': checks}, ensure_ascii=False, indent=2))
