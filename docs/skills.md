# Mini Cursor v1.1 技能系统

| 课件指定技能 | 类型 | 可直接发送的任务 |
| --- | --- | --- |
| run-tests | 纯提示词 | 帮我跑一下测试 |
| review-diff | Bash 调用配套脚本 | 把这段 diff 审一遍 |
| fetch-issue | MCP | 获取 GitHub Issue：octocat/Hello-World #1 |

选工作区并填写 DeepSeek API Key。运行测试、收集 Git 差异及 CSV 检查前，在界面勾选「允许终端命令」。审查工作区差异需要 Git。GitHub Issue 技能通过内置的独立 MCP 服务读取公开 Issue，需要能访问 GitHub API。遇到公开接口限流，可通过启动应用的环境变量 MINICURSOR_GITHUB_TOKEN 提供仅用于读取 Issue 的 GitHub Token。现有 CSV 和项目检查清单仍可用。

启动任务时仅扫描各 `SKILL.md` 的头部并按名称排序。触发条件来自 `description`。模型通过已有的 `read` 工具请求 `skill:技能名`，程序才执行 `use_skill(name)`，将正文作为工具结果返回。未匹配的请求无法读取技能正文。界面会显示 `Skill / 技能名`。

## 验收命令

在项目根目录运行：

```powershell
python -m pip install -r requirements-inspect.txt
python -m app.inspect skills --out skill_report.json
python -m app.selftest
```

如果本地没有分词器，首次验收会从 DeepSeek 官方地址下载，也可指定 `--tokenizer` 使用已有的 `tokenizer.json`。报告记录实际使用的分词数据校验值。两种计数只比较技能目录与全量技能正文，触发试验用离线模型替身按实际工具协议请求正文。

设置 `$env:ENABLE_SKILLS = '0'`，再从同一终端运行 `python -m app`，即可关闭技能功能。用 `Remove-Item Env:ENABLE_SKILLS` 恢复。报告包含相同代码关闭开关后的验收结果。
