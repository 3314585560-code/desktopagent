"""Kill a real child process, resume, and verify idempotent completion."""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import tempfile
from threading import Thread
import time

from durable import STEPS
from shell_runner import HIDDEN
from skills_runtime import SKILL_ROOT


def inspect_daemon():
    build = SKILL_ROOT.parent / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="daemon-report-", dir=build) as folder:
        work = Path(folder).resolve()
        assert work.is_relative_to(build.resolve())
        workspace = work / "project"
        workspace.mkdir()
        (workspace / "sample.py").write_text("print('audit')\n", encoding="utf-8")
        path = work / "checkpoint.json"
        result_path = path.with_suffix(".result.json")
        cmd = [sys.executable, "-B", "-m", "app.daemon", "--workspace", str(workspace), "--state", str(path)]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", ENABLE_DAEMON="1")
        cwd = SKILL_ROOT.parent

        with subprocess.Popen([*cmd, "--pause-before", "4"], cwd=cwd, env=env, text=True,
                              encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=HIDDEN) as child:
            lines = Queue()

            def drain():
                for line in child.stdout:
                    lines.put(line)
                lines.put(None)

            Thread(target=drain, daemon=True).start()
            deadline = time.monotonic() + 15
            initial_steps = []
            try:
                while time.monotonic() < deadline:
                    try:
                        line = lines.get(timeout=0.2)
                    except Empty:
                        continue
                    if line is None:
                        raise RuntimeError(child.stderr.read())
                    event = json.loads(line)
                    if event["kind"] == "step":
                        initial_steps.append(event["step"])
                    if event["kind"] == "paused":
                        break
                else:
                    raise TimeoutError("未收到第四步暂停事件")
            finally:
                child.kill()
                killed = child.wait(timeout=8)
        assert killed != 0 and initial_steps == [1, 2, 3]
        assert json.loads(path.read_text(encoding="utf-8"))["next_step"] == 4
        assert not result_path.exists()

        def run():
            proc = subprocess.run(cmd, cwd=cwd, env=env, check=True, timeout=15,
                                  capture_output=True, text=True, encoding="utf-8",
                                  creationflags=HIDDEN)
            return [json.loads(line) for line in proc.stdout.splitlines()]

        resumed = run()
        resume = next(event["step"] for event in resumed if event["kind"] == "resume")
        steps = [event["step"] for event in resumed if event["kind"] == "step"]
        notifications = [event for event in resumed if event["kind"] == "notification"]
        assert resume == 4 and steps == [4] and len(notifications) == 1
        assert json.loads(path.read_text(encoding="utf-8"))["completed"] == [1, 2, 3, 4]
        before = (path.read_bytes(), result_path.read_bytes(), result_path.stat().st_mtime_ns)
        again = run()
        after = (path.read_bytes(), result_path.read_bytes(), result_path.stat().st_mtime_ns)
        idempotent = before == after and [event["kind"] for event in again] == ["already_complete"]
        assert idempotent
        disabled = subprocess.run(cmd, cwd=cwd, env=dict(env, ENABLE_DAEMON="0"), timeout=8,
                                  capture_output=True, text=True, encoding="utf-8",
                                  creationflags=HIDDEN)
        disabled_ok = disabled.returncode != 0 and "ENABLE_DAEMON=0" in disabled.stderr
        assert disabled_ok

    return {
        "resume_from_step": resume, "resume_step": resume, "steps_total": STEPS,
        "notify_fired": bool(notifications), "idempotent": idempotent,
        "before_kill_steps": initial_steps, "after_resume_steps": steps,
        "notification_count": len(notifications), "forced_exit_code": killed,
        "disabled_trial": {"ENABLE_DAEMON": "0", "ok": disabled_ok},
        "measurement": "实际启动独立进程并强制结束，重启验证第四步与完成事件。桌面应用以原生消息框显示该事件。",
    }
