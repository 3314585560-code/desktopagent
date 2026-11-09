"""Run a command in the selected workspace and bound its output."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

OUTPUT_LIMIT = 24000
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    pass


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=HIDDEN, timeout=4, check=True,
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def command_argv(command):
    if os.name != "nt":
        return ["bash", "-lc", command]
    git = shutil.which("git")
    candidates = [Path(git).parent.parent / "bin" / "bash.exe"] if git else []
    for bash in candidates:
        if bash.is_file():
            return [str(bash), "--noprofile", "--norc", "-c", command]
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); " + command]


def run_command(command, timeout=30, *, workspace, cancel, private_key="", argv=None):
    if not isinstance(command, str) or not command.strip():
        raise ValueError("请输入终端命令")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError("timeout 必须是 1–120 秒的整数")
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in {"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "MINICURSOR_GITHUB_TOKEN"}
           and (not private_key or private_key not in value)}
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.Popen(
        argv if argv is not None else command_argv(command), cwd=workspace, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=HIDDEN, start_new_session=(os.name != "nt"),
    )
    buffers = [bytearray(), bytearray()]
    clipped = [False, False]

    def drain(pipe, index):
        with pipe:
            while chunk := pipe.read1(4096):
                remaining = OUTPUT_LIMIT - len(buffers[index])
                buffers[index].extend(chunk[:remaining])
                clipped[index] |= len(chunk) > remaining

    workers = [threading.Thread(target=drain, args=(pipe, i), daemon=True)
               for i, pipe in enumerate((process.stdout, process.stderr))]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None:
        if cancel.wait(0.05) or time.monotonic() >= deadline:
            timed_out = not cancel.is_set()
            stop_process(process)
            break
    process.wait(timeout=5)
    for worker in workers:
        worker.join(timeout=0.5)
    if cancel.is_set():
        raise Cancelled("运行已停止")

    def display(index):
        value = buffers[index].decode("utf-8", errors="replace")
        return value + ("\n[输出已截断]" if clipped[index] else "")

    return {"stdout": display(0), "stderr": display(1),
            "exit_code": process.returncode, "timed_out": timed_out}
