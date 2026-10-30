# 首次绑定

共享包内 config.json 是空白模板，禁止写入真实配置。默认个人配置位于用户目录 `.workbuddy/patient-daily-summary/config.json`；首次 bind 自动创建。未绑定时 plan、scrape、complete 均停止，不抓取任何来源。

向用户收集病区、关注床号、目标群或私聊，并让用户确认匹配的会话。禁止使用示例、历史报告或底层抓取程序的默认来源代替绑定。床号当前仅支持正整数；字母床号需要先扩展实现，不擅自转换。

会话 ID 可用 wx4-chat-reader 的 wx_find.py 在已有明文库中查询；明文库尚未准备时先按该依赖的说明初始化，不运行其内置默认群聊抓取。需要用户选择目标会话后再绑定，不能仅凭近似群名决定。

## 首次写入

在 PowerShell 中使用以下模板，替换尖括号内容（床号 2、4、6 仅为虚构演示）：

```powershell
& "<Python解释器路径>" "<技能目录>\scripts\daily_state.py" bind --ward "<病区>" --beds "2 4 6" --add-source "<会话ID>|<显示名>" --data-root "<本机微信数据目录>"
```

多来源重复使用 --add-source。显示名必须唯一，不能含换行或竖线；会话 ID 不能含空白。病区、床号、来源可分步绑定，但无效或重复来源不会写入配置。直接使用 Python 调用可避免 Windows PowerShell 5.1 对空字符串参数的兼容问题。

PowerShell 入口支持 -Action bind、-Ward、-Beds、-AddSource、-RemoveSource、-DataRoot、-Python。无参数 bind 查看状态；--remove-source 删除一个来源；--exclude-note 更新排除说明；--start-hour 修改起始小时（调度任务需要另行同步）。

## 检查

1. 无参数 bind 确认 bound，核对与用户刚提供的信息一致；不要求用户重复确认已确认内容。
2. plan 验证窗口和输出位置。bound 只表示绑定齐全，不表示依赖、微信登录或数据同步已检查成功。
3. 核对本地配置 paths，尤其 data_root、wx_daily、py。输出目录不必提前存在；缺少 wx4-chat-reader 或其 Python 依赖时先安装依赖，不能声称可直接抓取。
4. 用户授权汇总后运行 scrape，真实抓取才验证微信读取条件。

分享时仅打包技能目录，不打包用户目录的配置、cache、output 或历史报告。换病区时更改 ward 并替换 beds 和 sources；这些变化会使日报重新到期，旧报告可能被当前配置的报告覆盖，若需保留应先另存。
