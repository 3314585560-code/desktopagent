# Windows x64 打包

在 PowerShell 进入仓库根目录，使用 Python 3.14 x64 和下列命令打包：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -Version 1.3.0
```

`build.ps1` 先把 `app.py` 打成窗口程序，再把程序内嵌进 `installer.py` 生成安装包。输出为 `release/MiniCursor-Setup-1.3.0-x64.exe`。它应作为 GitHub Release 资产上传。源码运行无需安装打包依赖。旧版终端示例需额外安装 OpenAI Python 客户端。

## 本机 SSE 后端

在仓库根目录用一个终端启动：

```powershell
python server.py --workspace .\build\sse-demo
```

在第二个终端请求离线演示，首次运行使用一个尚未存放示例文件的专用目录：

```powershell
'{"demo":true}' | curl.exe -N -H "Content-Type: application/json" --data-binary "@-" http://127.0.0.1:8765/run
```

首个事件给出会话 ID。用 `POST /cancel/<id>` 中断。日常模型模式使用 `{"prompt":"..."}` 并在启动服务器前配置 `DEEPSEEK_API_KEY`。处理真实项目时传入其目录，只有显式指定 `--allow-shell` 才允许执行命令。

## MCP 配置

`mcp.json` 默认启用演示服务。通过界面的「MCP 配置」选择可信 JSON 文件，或向后端传入 `--mcp-config`。自定义配置示例：

```json
{
  "demo": false,
  "servers": {
    "example": {
      "command": "python",
      "args": ["path/to/server.py"]
    }
  }
}
```

`command` 应可从 PATH 找到，参数的相对路径以选中的工作区为准。
