"""A stdio MCP client for configured, user-approved local servers."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

from shell_runner import Cancelled, HIDDEN, stop_process

VERSION = "2025-11-25"


class MCPClient:
    def __init__(self, argv, workspace, cancel, env=None):
        self.cancel = cancel
        self.inbox = queue.Queue()
        self.serial = 0
        self.process = subprocess.Popen(
            argv, cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, encoding="utf-8", bufsize=1,
            creationflags=HIDDEN, env=env,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.inbox.put(json.loads(line))
        except (ValueError, OSError) as error:
            self.inbox.put(error)
        finally:
            self.inbox.put(EOFError("MCP 服务已关闭连接"))

    def _send(self, message):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.serial += 1
        self._send({"id": self.serial, "method": method, "params": params})
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.cancel.is_set():
                raise Cancelled("MCP 调用已停止")
            try:
                reply = self.inbox.get(timeout=0.1)
            except queue.Empty:
                continue
            if isinstance(reply, Exception):
                raise reply
            if reply.get("id") != self.serial:
                continue
            if "error" in reply:
                raise RuntimeError(reply["error"].get("message", "MCP 请求失败"))
            return reply["result"]
        raise TimeoutError(f"MCP 请求超时：{method}")

    def tools(self):
        self.request("initialize", {"protocolVersion": VERSION, "capabilities": {},
                                    "clientInfo": {"name": "Mini Cursor", "version": "1.0"}})
        self._send({"method": "notifications/initialized"})
        tools = []
        params = {}
        for _ in range(10):
            page = self.request("tools/list", params)
            tools.extend(page.get("tools", []))
            if not page.get("nextCursor"):
                return tools
            params = {"cursor": page["nextCursor"]}
        raise ValueError("MCP 工具列表超过 10 页")

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=0.4)
        except (OSError, subprocess.TimeoutExpired):
            stop_process(self.process)
            self.process.wait(timeout=5)
        self.process.stdout.close()


def load_servers(config_path, demo_argv):
    path = Path(config_path)
    if not path.is_file():
        return {"demo": demo_argv}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("servers", {}), dict):
        raise ValueError("MCP 配置需要包含 servers 对象")
    servers = {"demo": demo_argv} if data.get("demo", True) else {}
    for name, spec in data.get("servers", {}).items():
        argv = [spec["command"], *spec.get("args", [])]
        if not all(isinstance(item, str) and item for item in argv):
            raise ValueError(f"MCP 服务 {name} 的命令或参数无效")
        servers[name] = argv
    return servers
