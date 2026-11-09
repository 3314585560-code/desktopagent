"""Exercise v1.0 tool and model-adapter behavior without a key."""
import base64
import json
from pathlib import Path
import tempfile
from threading import Event
from unittest.mock import patch

from agent_core import Agent, TOOLS

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X0f8AAAAASUVORK5CYII="


def main():
    build = Path(__file__).resolve().parents[1] / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="baseline-", dir=build) as folder:
        workspace = Path(folder)
        (workspace / "pixel.png").write_bytes(base64.b64decode(PNG))
        events = []

        def respond(payload, key, cancel):
            assert payload["tools"] == TOOLS
            return {"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "模型替身已响应"},
            ]}]}

        agent = Agent(workspace, events.append, Event(), key="selftest-only",
                      allow_shell=True, request=respond)
        image = agent.tool("read", {"path": "pixel.png"})
        assert image[0]["image_url"].startswith("data:image/png;base64,")
        assert "成功" in agent.tool("write", {"path": "nested/a.txt", "content": "first\n"})
        assert "成功" in agent.tool("edit", {"path": "nested/a.txt", "old": "first", "new": "second"})
        assert (workspace / "nested" / "a.txt").read_text(encoding="utf-8") == "second\n"
        output = json.loads(agent.tool("bash", {"command": "echo baseline-ok"}))
        assert output["exit_code"] == 0 and "baseline-ok" in output["stdout"]
        with patch.dict("os.environ", {"ENABLE_SKILLS": "0"}):
            with patch.object(Agent, "connect", return_value=[]):
                assert agent.run("自检") == "模型替身已响应"
        assert {event["name"] for event in events if event["kind"] == "call"} == {
            "read", "write", "edit", "bash",
        }
    print(json.dumps({"tools": ["read", "write", "edit", "bash"],
                      "mock_model": True, "tool_events": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
