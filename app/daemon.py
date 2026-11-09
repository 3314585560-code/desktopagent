"""Command-line entry for a resumable workspace check."""
import argparse
import json
from pathlib import Path

from durable import run_workflow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--pause-before", type=int, choices=range(1, 5))
    args = parser.parse_args()
    state = args.state or args.workspace / ".mini-cursor" / "workspace-check.json"

    def emit(event):
        print(json.dumps(event, ensure_ascii=False), flush=True)

    run_workflow(args.workspace, state, emit, pause_before=args.pause_before)


if __name__ == "__main__":
    main()
