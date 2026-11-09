# v1.2 定制层

启动任务时，应用先读用户主目录下的 AGENTS.md，再从工作区向上查找最近的项目 AGENTS.md。合并后上限为 12,000 字节。应用会在事件区标明已注入的层。

- 写入或编辑 .env、.pem、.key，以及强制删除、强制推送和硬重置会在工具执行前被拒绝，并收到可替代操作。
- 在已勾选「允许终端命令」的任务中，write 或 edit 成功后自动跑项目测试。失败只回注用例、期望和实际三行。检测到 pytest 配置时使用 pytest，否则使用 unittest。
- 完成修改后，已获终端授权的任务进入独立只读审查。审查工具为 read 和限定参数的 git diff，主对话只收到最后结论。

`ENABLE_AGENTS_MD=0`、`ENABLE_HOOKS=0`、`ENABLE_REVIEWER=0` 可分别关闭。设置环境变量后，从同一终端重新启动应用。

```powershell
python -m app.inspect custom --out custom_report.json
python -m app.selftest
powershell -ExecutionPolicy Bypass -File build.ps1 -Version 1.2.0
```

验收采用受控模型替身。拦截、测试红灯与修复、Git 差异和权限隔离走实际代码，报告不包含未经验证的线上模型表现。
