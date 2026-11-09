"""Project instruction layers, tool hooks, and the isolated reviewer."""
import json
import os
from pathlib import Path
import re
import sys

from agent_tools import read_file, workspace_path
from shell_runner import Cancelled, run_command

INSTRUCTION_LIMIT = 12000
REVIEW_LIMIT = 380


def enabled(name):
    return os.environ.get(name, "1") != "0"


def project_rules(workspace, global_path=None):
    global_path = Path(global_path) if global_path else Path.home() / "AGENTS.md"
    project = next((folder / "AGENTS.md" for folder in (workspace, *workspace.parents)
                    if (folder / "AGENTS.md").is_file()), None)
    sections, layers = [], []
    for label, path in (("global", global_path), ("project", project)):
        if not path or not path.is_file() or (label == "project" and path.resolve() == global_path.resolve()):
            continue
        with path.open("rb") as file:
            data = file.read(INSTRUCTION_LIMIT + 1)
        text = data.decode("utf-8-sig", errors="ignore").strip()
        if text:
            sections.append(f"[{label} AGENTS.md]\n{text}")
            layers.append(label)
    body = "\n\n".join(sections).encode("utf-8")[:INSTRUCTION_LIMIT].decode("utf-8", errors="ignore")
    return body, layers


def sensitive_path(path):
    name = Path(path.replace("\\", "/")).name.lower()
    return (name == ".env" or (name.startswith(".env.") and name != ".env.example")
            or name.endswith((".pem", ".key")))


def before_tool(name, args):
    path = args.get("path")
    if name in {"write", "edit"} and isinstance(path, str) and sensitive_path(path):
        return "密钥不入库，用环境变量。可写入不含真实值的 .env.example。"
    command = args.get("command")
    if name != "bash" or not isinstance(command, str):
        return None
    for segment in re.split(r"[;&|\r\n]+", command.lower().replace('"', "").replace("'", "")):
        rm = re.search(r"\brm(?:\.exe)?\s+(.+)", segment)
        if rm:
            flags = rm[1].split()
            letters = "".join(arg[1:] for arg in flags if arg.startswith("-") and not arg.startswith("--"))
            if ("r" in letters or "--recursive" in flags) and ("f" in letters or "--force" in flags):
                return "拒绝递归强制删除。可先用 git clean -nd 预览，确认后逐个处理。"
        if re.search(r"\b(?:git|git\.exe)\b.*?\bpush\b.*?(?:\s-f\b|\s--force(?:-with-lease)?\b)", segment):
            return "拒绝强制推送。可用 git revert 创建反向提交，再正常 git push。"
        if re.search(r"\b(?:git|git\.exe)\b.*?\breset\b.*?\s--hard\b", segment):
            return "拒绝硬重置。先用 git diff 核对，再按具体文件用 git restore。"
    return None


def autotest(workspace, cancel, key):
    config = workspace / "pyproject.toml"
    pyproject = ""
    if config.is_file():
        with config.open(encoding="utf-8", errors="replace") as file:
            pyproject = file.read(65536)
    pytest = (workspace / "pytest.ini").is_file() or "[tool.pytest" in pyproject
    if getattr(sys, "frozen", False):
        argv = None if pytest else [sys.executable, "--demo-tests"]
    else:
        argv = [sys.executable, "-m", "pytest", "-q", "--tb=short"] if pytest else [
            sys.executable, "-m", "unittest", "discover", "-q",
        ]
    command = "python -m pytest -q --tb=short" if pytest else "python -m unittest discover -q"
    result = run_command(command, 30, workspace=workspace, cancel=cancel, private_key=key, argv=argv)
    output = result["stdout"] + "\n" + result["stderr"]
    count = re.search(r"Ran (\d+) tests?", output)
    passed = result["exit_code"] == 0 and not result["timed_out"] and not (
        (count and count[1] == "0") or "no tests ran" in output.lower()
    )
    if passed:
        return True, "自动测试通过" + (f"（{count[1]} 项）" if count else "") + "。"
    case = re.search(r"^(?:FAIL: |ERROR: |FAILED )(.+)", output, re.M)
    assertion = re.search(r"^AssertionError: (.+)", output, re.M)
    actual, expected = "见测试命令的失败状态", "测试通过"
    if assertion:
        actual = assertion[1]
        if " != " in actual:
            actual, expected = actual.split(" != ", 1)
    elif result["timed_out"]:
        actual = "自动测试超时"
    elif count and count[1] == "0":
        actual = "未发现测试"
    else:
        detail = next((line.strip() for line in reversed(output.splitlines()) if
                       "Error:" in line or line.strip().startswith("FAILED")), None)
        if detail:
            actual = detail
    return False, "\n".join((f"用例：{case[1][:140] if case else '测试入口或用例集'}",
                             f"期望：{expected[:140]}", f"实际：{actual[:160]}"))


REVIEW_INSTRUCTIONS = (
    "你是独立只读审查员。先用 git diff 检查差异，必要时 read 相关文件。"
    "只核对：1. 越界文件；2. 新依赖；3. except: pass；4. 新分支测试覆盖；"
    "5. diff 中的调试 print 或 TODO。只返回有依据的精简最终问题列表。"
)


def review(workspace, touched, request, key, model, cancel, tools):
    items = [{"role": "user", "content": "核对本轮修改的文件：" + "、".join(sorted(touched))}]
    readonly = [dict(item) for item in tools if item["name"] in {"read", "bash"}]
    for item in readonly:
        if item["name"] == "bash":
            item["description"] = "仅支持 git diff、git diff --stat 或 git diff --cached。"
    usage = 0
    for _ in range(4):
        if cancel.is_set():
            raise Cancelled("审查已停止")
        reply = request({
            "model": model, "instructions": REVIEW_INSTRUCTIONS, "input": items,
            "tools": readonly, "max_output_tokens": 200, "reasoning": {"effort": "none"},
        }, key, cancel)
        tokens = reply.get("usage") or {}
        usage += tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
        output = reply.get("output", [])
        calls = [item for item in output if item.get("type") == "function_call"]
        if not calls:
            answer = "\n".join(part["text"] for item in output if item.get("type") == "message"
                               for part in item.get("content", []) if part.get("type") == "output_text").strip()
            if not answer:
                raise ValueError("只读审查未返回结论")
            return answer.encode("utf-8")[:REVIEW_LIMIT].decode("utf-8", errors="ignore"), usage
        items.extend(output)
        for call in calls:
            try:
                args = json.loads(call["arguments"])
                if call["name"] == "read" and not sensitive_path(args["path"]):
                    result = read_file(args["path"], args.get("offset", 1), min(args.get("limit", 80), 80),
                                       workspace=workspace)
                    result = result[:8000] if isinstance(result, str) else "审查只读取文本"
                elif call["name"] == "bash" and args.get("command") in {
                    "git diff", "git diff --stat", "git diff --cached",
                }:
                    argv = ["git", "diff", "--no-ext-diff", "--no-textconv", *args["command"].split()[2:]]
                    command_result = run_command(args["command"], 12, workspace=workspace,
                                                 cancel=cancel, private_key=key, argv=argv)
                    result = (command_result["stdout"] or command_result["stderr"])[:10000]
                else:
                    result = "拒绝：审查员仅可读取文本或执行指定的 git diff 命令。"
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                result = f"审查读取失败：{error}"
            items.append({"type": "function_call_output", "call_id": call["call_id"], "output": result})
    raise ValueError("只读审查达到调用上限")
