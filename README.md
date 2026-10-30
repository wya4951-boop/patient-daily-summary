# patient-daily-summary

用于 WorkBuddy 的病区每日情况汇总技能，生成「床号｜时间、情况与处理｜消息来源」三列交接草稿。

## 功能

- 默认统计北京时间前一日07:00（含）至当日07:00（不含）的记录。
- 按床号分点，关联情况与处理并保留各自时间及消息来源。
- 支持完成记录及失败补跑判断，默认不追补更早的积压日期。
- 首次使用须自行绑定，仓库不包含真实床位、会话绑定或患者记录。

## 安装与使用

1. 下载本仓库，将目录命名为 `patient-daily-summary`，放入用户目录 `.workbuddy/skills/`。
2. 准备 Python 3.8+ 及本机 `wx4-chat-reader` 依赖（本仓库不含该依赖），确认微信已登录、Windows 时区为 UTC+08:00。
3. 在 WorkBuddy 中要求使用此技能，按 [绑定指南](references/binding.md) 配置自己的病区、床号、微信会话和微信数据目录。
4. 个人配置自动保存到用户目录 `.workbuddy/patient-daily-summary/config.json`，与仓库内空白模板分离。请勿上传个人配置、聊天记录或生成的报告。
5. 每日自动执行需在 WorkBuddy 中另行配置，见 [调度说明](references/scheduling.md)。安装技能不会自动创建定时任务。

完整流程见 [SKILL.md](SKILL.md)，表格规则见 [汇总规则](references/summary-rules.md)。

## 验证

```powershell
python -B tests/test_daily_state.py
python -B tests/test_capture.py
```

测试使用虚构数据与模拟抓取，不代表已经验证每台机器的真实微信读取条件。汇总只整理已有记录，供医护核对，不自动提出治疗建议。
