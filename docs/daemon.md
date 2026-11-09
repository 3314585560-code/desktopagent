# v1.3 断点续跑与完成通知

在桌面版选定工作区，点击「续跑检查」。流程依次扫描文件、统计文件类型、读取 Git 状态、生成报告。每一步完成后写入检查点。再次打开应用并检查同一工作区时，会接着运行未完成的步骤。完成后弹出系统消息框，并在右侧记录通知。检查流程可离线运行。

默认检查点为工作区内的 `.mini-cursor/workspace-check.json`，报告为同目录的 `workspace-check.result.json`。同一工作区的已完成检查再次执行时会显示已有报告。要重新检查，可为命令行指定新的 `--state` 路径。

验收命令会实际启动子进程，在第 3 步落盘后强制结束进程，再重启验证从第 4 步续跑、发出一次通知，且重复执行时报告字节和修改时间保持一致。

```powershell
python -m app.inspect daemon --out daemon_report.json
```

手动演示可在项目目录执行以下命令。等终端显示第 3 步完成并暂停后，在另一终端结束该进程，再省略 `--pause-before 4` 执行同一条命令。

```powershell
python -m app.daemon --workspace . --pause-before 4
```

设置 `ENABLE_DAEMON=0` 可关闭续跑功能。检查点只用于这个四步工作区流程。
