"""Collect a bounded, read-only Git diff for the selected workspace."""
import json
import subprocess
import sys

LIMIT = 5500


def git(*args):
    command = ["git", "-c", "core.fsmonitor=false", "--literal-pathspecs", *args]
    result = subprocess.run(command, capture_output=True, timeout=7)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "Git 命令失败")
    text = result.stdout.decode("utf-8", errors="replace")
    return text[:LIMIT] + ("\n[输出已截断]" if len(text) > LIMIT else "")


if __name__ == "__main__":
    scope = ["--", *sys.argv[1:]]
    try:
        print(json.dumps({
            "status": git("status", "--short", *scope),
            "unstaged": git("diff", "--no-ext-diff", "--no-textconv", *scope),
            "staged": git("diff", "--cached", "--no-ext-diff", "--no-textconv", *scope),
        }, ensure_ascii=False))
    except FileNotFoundError:
        sys.exit("未找到 Git。请安装 Git，或提供 diff 文本供审查。")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
