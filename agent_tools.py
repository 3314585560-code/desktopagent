import base64
from pathlib import Path
from tempfile import NamedTemporaryFile

WORKSPACE = Path(__file__).resolve().parent


def workspace_path(path, workspace):
    root = Path(workspace).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("只能访问工作区内的文件")
    for part in target.relative_to(root).parts:
        name = part.lower()
        if name in {".git", ".venv", ".env", "__pycache__"} or (
            name.startswith(".env.") and name != ".env.example"
        ):
            raise ValueError("此文件属于本机配置或工作区内部数据")
    return target


def read_file(path, offset=1, limit=100, *, workspace=WORKSPACE):
    if type(offset) is not int or type(limit) is not int or offset < 1 or limit < 1:
        raise ValueError("起始行和读取行数都必须大于 0")

    target = workspace_path(path, workspace)
    limit = min(limit, 500)
    image_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    mime_type = image_types.get(target.suffix.lower())

    if mime_type:
        if target.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("图片大于 4 MiB，请缩小后重试")
        image_bytes = target.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return {
            "type": "image",
            "mime_type": mime_type,
            "data": encoded,
        }
    selected = []
    total_lines = 0
    last_requested = offset + limit - 1

    with target.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            total_lines = line_number
            if offset <= line_number <= last_requested:
                content = line.rstrip("\r\n")
                selected.append(f"{line_number}: {content}")

    remaining = max(0, total_lines - last_requested)
    return "\n".join(selected + [f"后面还有 {remaining} 行"])


def write_file(path, content, *, workspace=WORKSPACE):
    target = workspace_path(path, workspace)

    old_lines = None
    if target.exists():
        old_lines = len(target.read_text(encoding="utf-8").splitlines())

    target.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="",
            dir=target.parent, delete=False,
        ) as temp:
            temp_path = Path(temp.name)
            temp.write(content)

        temp_path.replace(target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    new_lines = len(content.splitlines())
    if old_lines is None:
        return f"新建成功，共 {new_lines} 行"
    return f"覆盖成功，原来 {old_lines} 行，现在 {new_lines} 行"


def edit_file(path, old, new, *, workspace=WORKSPACE):
    if not old:
        raise ValueError("要替换的旧内容不能为空")

    target = workspace_path(path, workspace)

    with target.open(encoding="utf-8", newline="") as file:
        original = file.read()

    first = original.find(old)
    if first == -1:
        raise ValueError("找不到要替换的旧内容")
    if original.find(old, first + 1) != -1:
        raise ValueError("旧内容匹配到多处，请提供更具体的内容")

    updated = original[:first] + new + original[first + len(old):]
    return write_file(path, updated, workspace=workspace)