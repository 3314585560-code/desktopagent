# 项目地图

- app/ 装配桌面窗口、验收入口及可续跑流程。
- agent_core.py 管理模型和四个内置工具的调用循环。
- agent_tools.py、shell_runner.py 负责工作区访问和终端进程。
- skills/ 保存各技能的目录头、流程和脚本。
- customization.py 负责规则注入、工具 Hook 和只读审查。

# 构建与测试

- 基线自检：python -m app.selftest。
- 技能报告：python -m app.inspect skills --out skill_report.json。
- Windows 安装包：powershell -ExecutionPolicy Bypass -File build.ps1。

# 代码风格

- 界面线程只处理显示，通过事件队列接收工具结果。
- 写入保持原子替换；新增工具参数必须在执行前校验。
- 验收报告必须由程序打印，保存实测结果。

# 坑

- 文件工具必须经过 workspace_path；工作区以用户所选目录为准。
- 普通终端命令与测试执行需要在界面授权。
- MCP 进程 stdout 只放 JSON-RPC 消息。
- 真实密钥在环境变量或应用设置中提供，不放入项目文件。
