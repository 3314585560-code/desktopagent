"""Standalone MCP service used in the offline product demo."""
import io
import os
import json
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mcp_client import VERSION


def pipe(stream, handle_id, mode):
    if stream is not None:
        return stream.buffer
    import ctypes
    import msvcrt
    get_handle = ctypes.windll.kernel32.GetStdHandle
    get_handle.restype = ctypes.c_void_p
    handle = get_handle(handle_id & 0xFFFFFFFF)
    flags = (os.O_RDONLY if mode == "rb" else os.O_WRONLY) | os.O_BINARY
    return os.fdopen(msvcrt.open_osfhandle(handle, flags), mode)


def fetch_issue(owner, repo, number):
    pattern = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}"
    if not all(isinstance(part, str) and re.fullmatch(pattern, part) for part in (owner, repo)):
        raise ValueError("请提供有效的 GitHub owner 和 repo")
    if type(number) is not int or not 1 <= number <= 2147483647:
        raise ValueError("Issue 编号必须是正整数")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "MiniCursor-MCP"})
    token = os.environ.get("MINICURSOR_GITHUB_TOKEN", "").strip()
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=7) as response:
            data = json.loads(response.read(1024 * 1024))
    except HTTPError as error:
        with error:
            if error.code == 429 or (error.code == 403 and error.headers.get("X-RateLimit-Remaining") == "0"):
                raise ValueError("GitHub API 已限流。请稍后重试，或配置仅有读取权限的 MINICURSOR_GITHUB_TOKEN。") from None
            raise
    if "pull_request" in data:
        raise ValueError("该编号指向 Pull Request，请提供 Issue 编号")
    return {
        "title": data["title"], "state": data["state"], "url": data["html_url"],
        "labels": [label["name"] for label in data.get("labels", [])],
        "body": (data.get("body") or "")[:3000],
    }


def serve():
    stdin = io.TextIOWrapper(pipe(sys.stdin, -10, "rb"), encoding="utf-8")
    stdout = io.TextIOWrapper(pipe(sys.stdout, -11, "wb"), encoding="utf-8", write_through=True)
    tool = {
        "name": "project_checklist",
        "description": "Return a short validation checklist for the supplied project.",
        "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}},
                        "required": ["project"], "additionalProperties": False},
    }
    issue_tool = {
        "name": "fetch_issue", "description": "Read a public GitHub issue by owner, repo and number.",
        "inputSchema": {"type": "object", "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"},
            "number": {"type": "integer", "minimum": 1},
        }, "required": ["owner", "repo", "number"], "additionalProperties": False},
    }
    for line in stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        method = request.get("method")
        reply = {"jsonrpc": "2.0", "id": request["id"]}
        if method == "initialize":
            reply["result"] = {"protocolVersion": VERSION, "capabilities": {"tools": {}},
                               "serverInfo": {"name": "Course Checklist", "version": "1.0"}}
        elif method == "tools/list":
            reply["result"] = {"tools": [tool, issue_tool]}
        elif method == "tools/call" and request["params"].get("name") == tool["name"]:
            project = request["params"].get("arguments", {}).get("project", "")
            reply["result"] = {"content": [{"type": "text", "text":
                f"{project}：检查改动范围，运行测试，记录失败及恢复。"}]}
        elif method == "tools/call" and request["params"].get("name") == issue_tool["name"]:
            try:
                issue = fetch_issue(**request["params"].get("arguments", {}))
                reply["result"] = {"content": [{"type": "text", "text": json.dumps(issue, ensure_ascii=False)}]}
            except (OSError, ValueError, KeyError, TypeError) as error:
                reply["result"] = {"isError": True, "content": [
                    {"type": "text", "text": f"GitHub Issue 读取失败：{error}"},
                ]}
        elif method == "ping":
            reply["result"] = {}
        else:
            reply["error"] = {"code": -32601, "message": "Method not found"}
        stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        stdout.flush()


if __name__ == "__main__":
    serve()
