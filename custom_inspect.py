"""Exercise project rules, hooks, recovery, and reviewer through the actual Agent."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event
from unittest.mock import patch

from agent_core import Agent
from skills_runtime import SKILL_ROOT


def call(name, call_id, args):
    return {"type": "function_call", "name": name, "call_id": call_id,
            "arguments": json.dumps(args, ensure_ascii=False)}


def answer(text):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


def inspect_custom(tokenizer_path):
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(tokenizer_path))

    def tokens(text):
        return len(tokenizer.encode(text, add_special_tokens=False).ids)

    build = SKILL_ROOT.parent / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="custom-report-", dir=build) as folder:
        work = Path(folder)
        workspace = work / "repo"
        workspace.mkdir()
        (workspace / "AGENTS.md").write_text("# 项目规则\n保持修改最小。\n", encoding="utf-8")
        global_path = work / "global" / "AGENTS.md"
        global_path.parent.mkdir()
        global_path.write_text("# 全局规则\n用中文汇报。\n", encoding="utf-8")
        file = workspace / "number.py"
        file.write_text("VALUE = 1\n", encoding="utf-8")
        (workspace / "test_number.py").write_text(
            "import unittest\nfrom number import VALUE\n\n"
            "class NumberTest(unittest.TestCase):\n"
            "    def test_value(self):\n"
            "        self.assertEqual(VALUE, 1)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(workspace)], check=True)
        subprocess.run(["git", "-C", str(workspace), "add", "--", "number.py"], check=True)
        events = []
        reviewer_inputs = []
        reviewer_outputs = []
        reviewer_denials = []
        main_final = "修改已验证，测试通过。"
        main_turn = 0
        reviewer_turn = 0

        def model(payload, key, cancel):
            nonlocal main_turn, reviewer_turn
            if payload["instructions"].startswith("你是独立只读审查员"):
                assert [tool["name"] for tool in payload["tools"]] == ["read", "bash"]
                assert not any(item.get("content") == "修改数字并验证。" for item in payload["input"])
                reviewer_inputs.append(json.dumps(payload, ensure_ascii=False))
                reviewer_turn += 1
                if reviewer_turn == 1:
                    reply = {"output": [
                        call("bash", "diff", {"command": "git diff"}),
                        call("write", "blocked-review", {"path": "should-not-exist.txt", "content": "bad"}),
                        call("bash", "blocked-shell", {"command": "git status"}),
                    ]}
                else:
                    results = {item["call_id"]: item["output"] for item in payload["input"]
                               if item.get("type") == "function_call_output"}
                    assert "VALUE = 1" in results["diff"]
                    assert results["blocked-review"].startswith("拒绝")
                    assert results["blocked-shell"].startswith("拒绝")
                    reviewer_denials.extend(value for value in results.values() if value.startswith("拒绝"))
                    reply = answer("测试覆盖修复分支。未发现越界改动、依赖变化或调试残留。")
                reviewer_outputs.append(json.dumps(reply, ensure_ascii=False))
                return reply

            main_turn += 1
            if main_turn == 1:
                assert payload["instructions"].index("[global AGENTS.md]") < payload["instructions"].index("[project AGENTS.md]")
                return {"output": [
                    call("write", "deny-env", {"path": ".env", "content": "placeholder"}),
                    call("edit", "deny-pem", {"path": "a.pem", "old": "a", "new": "b"}),
                    call("bash", "deny-delete", {"command": "rm -rf build/"}),
                    call("bash", "deny-push", {"command": "git push --force"}),
                    call("bash", "deny-reset", {"command": "git reset --hard"}),
                    call("edit", "red", {"path": "number.py", "old": "VALUE = 1", "new": "VALUE = 2"}),
                ]}
            results = {item["call_id"]: item["output"] for item in payload["input"]
                       if item.get("type") == "function_call_output"}
            if main_turn == 2:
                assert all(results[name].startswith("拒绝") for name in (
                    "deny-env", "deny-pem", "deny-delete", "deny-push", "deny-reset",
                ))
                assert "用例：" in results["red"] and "期望：1" in results["red"] and "实际：2" in results["red"]
                return {"output": [
                    call("edit", "green", {"path": "number.py", "old": "VALUE = 2",
                                           "new": "# 已核对测试期望\nVALUE = 1"}),
                ]}
            assert "自动测试通过" in results["green"]
            return answer(main_final)

        flags = {"ENABLE_HOOKS": "1", "ENABLE_AGENTS_MD": "1", "ENABLE_REVIEWER": "1"}
        with patch.dict(os.environ, flags), patch.object(Agent, "connect", return_value=[]):
            agent = Agent(workspace, events.append, Event(), key="inspect-only", request=model,
                          global_rules=global_path, allow_shell=True)
            final = agent.run("修改数字并验证。")
        assert not (workspace / ".env").exists() and not (workspace / "should-not-exist.txt").exists()

        denied = [{"tool": event["name"], **{k: event["args"][k] for k in ("path", "command")
                    if k in event["args"]}, "reason": event["reason"]}
                  for event in events if event["kind"] == "denied"]
        tests = [event for event in events if event["kind"] == "autotest"]
        rules = next(event for event in events if event["kind"] == "rules")
        reviews = [event for event in events if event["kind"] == "reviewer"]
        delta = tokens(final) - tokens(main_final)
        assert 0 < delta <= 500
        assert final == main_final + reviews[0]["main_addition"]
        assert len(denied) == 5 and len(tests) == 2 and not tests[0]["passed"] and tests[1]["passed"]

        disabled_events = []
        with patch.dict(os.environ, {"ENABLE_HOOKS": "0"}):
            agent = Agent(workspace, disabled_events.append, Event(), allow_shell=True)
            assert "成功" in agent.tool("write", {"path": "fixture.pem", "content": "fake fixture"})
        disabled_ok = (workspace / "fixture.pem").is_file() and not any(
            event["kind"] in {"denied", "autotest"} for event in disabled_events
        )
        assert disabled_ok

    return {
        "agents_md": {"found": True, "bytes": rules["bytes"], "layers": rules["layers"]},
        "denied": denied,
        "autotest": {"runs": len(tests), "red": sum(not item["passed"] for item in tests),
                     "green": sum(item["passed"] for item in tests),
                     "red_to_green": sum(not a["passed"] and b["passed"] for a, b in zip(tests, tests[1:])),
                     "injected_lines": max(item["lines"] for item in tests)},
        "reviewer": {"runs": len(reviews), "issues_found": sum(line.startswith("- ") for event in reviews for line in event["text"].splitlines()), "main_context_delta": delta,
                     "subagent_tokens": sum(tokens(value) for value in reviewer_inputs + reviewer_outputs),
                     "blocked_attempts": len(reviewer_denials)},
        "disabled_trial": {"ENABLE_HOOKS": "0", "ok": disabled_ok},
        "measurement": "模型回复为受控替身。规则、工具拦截、Git diff 和本机测试实际执行。token 用同一离线分词器计算。",
    }
