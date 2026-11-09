"""Course acceptance entry point."""
import argparse
import json
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from skills_inspect import print_report
from skills_runtime import SKILL_ROOT

TOKENIZER_URL = "https://cdn.deepseek.com/api-docs/deepseek_v4_tokenizer.zip"


def tokenizer_file():
    target = SKILL_ROOT.parent / "build" / "skill-tokenizer.json"
    if not target.is_file():
        with urlopen(TOKENIZER_URL, timeout=25) as response:
            archive = response.read(16 * 1024 * 1024 + 1)
        if len(archive) > 16 * 1024 * 1024:
            raise ValueError("官方分词器压缩包超出预期大小")
        with ZipFile(BytesIO(archive)) as zip_file:
            data = zip_file.read("deepseek_v4_tokenizer/tokenizer.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("section", choices=["skills", "custom", "daemon"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path)
    args = parser.parse_args()
    if args.section == "daemon":
        from daemon_inspect import inspect_daemon

        report = inspect_daemon()
    else:
        tokenizer = args.tokenizer or tokenizer_file()
        if args.section == "skills":
            print_report(tokenizer, args.out)
            return
        from custom_inspect import inspect_custom

        report = inspect_custom(tokenizer)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
