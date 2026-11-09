"""Return a CSV shape and missing-value report without modifying the input."""
import csv
import json
from pathlib import Path
import sys

MAX_SIZE = 5 * 1024 * 1024


def profile(path):
    if path.stat().st_size > MAX_SIZE:
        raise ValueError("CSV 超过 5 MiB，请拆分后检查")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        headers = next(reader, [])
        if not headers or not any(value.strip() for value in headers):
            raise ValueError("CSV 缺少有效表头")
        if len(headers) > 200:
            raise ValueError("CSV 列数超过 200")
        blanks = [0] * len(headers)
        rows = irregular_rows = 0
        for row in reader:
            rows += 1
            irregular_rows += len(row) != len(headers)
            for index in range(len(headers)):
                if index >= len(row) or not row[index].strip():
                    blanks[index] += 1
    return {"rows": rows, "columns": headers, "irregular_rows": irregular_rows,
            "empty_by_column": [{"index": i, "name": name, "empty": count}
                                for i, (name, count) in enumerate(zip(headers, blanks), start=1)]}


if __name__ == "__main__":
    try:
        print(json.dumps(profile(Path(sys.argv[1])), ensure_ascii=False))
    except (IndexError, OSError, ValueError, csv.Error) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
