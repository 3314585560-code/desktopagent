"""A resumable workspace audit with atomic checkpoints and a completion event."""
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from threading import Event

from shell_runner import Cancelled, HIDDEN

STEPS = 4
SKIP = {".git", ".venv", ".mini-cursor", "__pycache__", "build", "dist", "release"}


def daemon_enabled():
    return os.environ.get("ENABLE_DAEMON", "1") != "0"


def save_json(path, value):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


@contextmanager
def exclusive(path):
    with path.open("a+b") as file:
        if not file.tell():
            file.write(b"\0")
            file.flush()
        file.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError("同一工作区已有检查流程在运行") from error
        else:
            import fcntl

            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("同一工作区已有检查流程在运行") from error
        # The OS releases the lock when the file closes or the process dies.
        yield


def scan(workspace):
    files = []
    for folder, directories, names in os.walk(workspace):
        directories[:] = sorted(name for name in directories
                                if name not in SKIP and not name.startswith("."))
        for name in sorted(names):
            if name.startswith(".") or name.lower().endswith((".pem", ".key")):
                continue
            files.append((Path(folder) / name).relative_to(workspace).as_posix())
            if len(files) == 500:
                return {"files": files, "truncated": True}
    return {"files": files, "truncated": False}


def git_status(workspace):
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "status", "--porcelain", "--untracked-files=no"],
            cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=HIDDEN, timeout=8, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}
    return {"available": result.returncode == 0,
            "changed": len(result.stdout.splitlines()) if result.returncode == 0 else None}


def run_workflow(workspace, state_path, emit, cancel=None, pause_before=None):
    if not daemon_enabled():
        raise ValueError("续跑功能已通过 ENABLE_DAEMON=0 关闭")
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("请选择工作区目录")
    path = Path(state_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    result_path = path.with_suffix(".result.json")
    signal = cancel or Event()
    with exclusive(path.with_suffix(".lock")):
        if path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("workspace") != str(workspace) or state.get("schema") != 1:
                raise ValueError("检查点版本或工作区不匹配")
        else:
            state = {"schema": 1, "workspace": str(workspace), "completed": [],
                     "next_step": 1, "data": {}, "done": False, "notification": None}
            save_json(path, state)

        if state["done"]:
            emit({"kind": "already_complete", "text": f"检查已完成，报告：{result_path}"})
            return state

        emit({"kind": "resume", "step": state["next_step"],
              "text": f"从第 {state['next_step']} 步开始"})
        for number in range(state["next_step"], STEPS + 1):
            if signal.is_set():
                raise Cancelled("检查已停止，可以从断点继续")
            if pause_before == number:
                emit({"kind": "paused", "step": number, "text": f"已保存，等待第 {number} 步"})
                signal.wait()
                raise Cancelled("检查已停止，可以从断点继续")
            data = state["data"]
            if number == 1:
                data["scan"] = scan(workspace)
            elif number == 2:
                data["file_types"] = dict(sorted(Counter(
                    Path(name).suffix.lower() or "(无扩展名)" for name in data["scan"]["files"]
                ).items()))
            elif number == 3:
                data["git"] = git_status(workspace)
            else:
                save_json(result_path, {
                    "files_checked": len(data["scan"]["files"]),
                    "truncated": data["scan"]["truncated"],
                    "file_types": data["file_types"], "git": data["git"],
                })
                state["done"] = True
                state["notification"] = {
                    "kind": "notification",
                    "text": f"工作区检查完成。报告：{result_path}",
                }
            state["completed"].append(number)
            state["next_step"] = number + 1
            save_json(path, state)
            emit({"kind": "step", "step": number, "text": f"第 {number} 步完成，检查点已保存"})
        emit(state["notification"])
        return state
