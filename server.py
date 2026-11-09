"""Local server for running and inspecting the agent without the desktop."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import uuid

from agent_core import Agent, demo_fixture
from shell_runner import Cancelled


def serve(workspace, port, allow_shell, config=None):
    sessions = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.headers.get("Origin"):
                self.send_json(403, {"error": "请通过本机命令行访问"})
                return
            if self.path.startswith("/cancel/"):
                with lock:
                    signal = sessions.get(self.path.rsplit("/", 1)[-1])
                if signal:
                    signal.set()
                self.send_json(200 if signal else 404, {"cancelled": bool(signal)})
                return
            if self.path != "/run":
                self.send_json(404, {"error": "使用 POST /run"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("请求体应为 1 到 65536 字节")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("请求体必须是 JSON 对象")
                demo = payload.get("demo") is True
                prompt = payload.get("prompt", "")
                if not demo and (not isinstance(prompt, str) or not prompt.strip()):
                    raise ValueError("prompt 不能为空")
            except (ValueError, TypeError) as error:
                self.send_json(400, {"error": str(error)})
                return

            signal = threading.Event()
            with lock:
                busy = bool(sessions)
                job = uuid.uuid4().hex
                if not busy:
                    sessions[job] = signal
            if busy:
                self.send_json(409, {"error": "当前工作区已有任务运行中"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            key = os.environ.get("DEEPSEEK_API_KEY", "")

            def emit(event):
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(f"event: {event['kind']}\ndata: {data}\n\n".encode("utf-8"))
                self.wfile.flush()

            try:
                emit({"kind": "session", "id": job})
                if demo:
                    demo_fixture(workspace)
                Agent(workspace, emit, signal, key=key,
                      allow_shell=allow_shell or demo, config=config).run(prompt, demo=demo)
                emit({"kind": "done", "text": "已完成"})
            except Cancelled:
                emit({"kind": "done", "text": "已停止"})
            except (ConnectionError, BrokenPipeError):
                signal.set()
            except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
                detail = str(error).replace(key, "[密钥已隐藏]") if key else str(error)
                emit({"kind": "error", "text": detail})
            finally:
                with lock:
                    sessions.pop(job, None)

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"本机事件流：http://127.0.0.1:{port}/run", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-shell", action="store_true")
    parser.add_argument("--mcp-config", type=Path)
    args = parser.parse_args()
    serve(args.workspace, args.port, args.allow_shell, args.mcp_config)
