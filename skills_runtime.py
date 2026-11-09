"""Discover bundled Skill metadata and load only a matched workflow."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys

SKILL_ROOT = Path(__file__).resolve().parent / "skills"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TRIGGER = re.compile(r"「([^」]+)」")
BOUNDARIES = " \t\n:：,，。!！?？"
SKILL_READ_PREFIX = "skill:"
SCRIPT_COMMAND = "skill-script"
SCRIPTS = {"csv-profile": "profile_csv.py", "review-diff": "collect_diff.py"}


def skills_enabled():
    return os.environ.get("ENABLE_SKILLS", "1") != "0"


def read_header(stream):
    if stream.readline(1024).strip() != "---":
        raise ValueError("技能缺少元数据头")
    fields = {}
    for _ in range(12):
        line = stream.readline(1024)
        if line.strip() == "---":
            if set(fields) != {"name", "description"}:
                raise ValueError("技能头需要 name 和 description")
            return fields
        key, sep, value = line.partition(":")
        if not sep or key not in {"name", "description"} or key in fields or not value.strip():
            raise ValueError("技能头格式无效")
        fields[key] = value.strip()
    raise ValueError("技能头未结束")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path

    @property
    def triggers(self):
        return TRIGGER.findall(self.description)

    def load_body(self):
        with self.path.open(encoding="utf-8-sig") as stream:
            read_header(stream)
            body = stream.read(16001)
        if not body.strip() or len(body) > 16000:
            raise ValueError(f"技能正文为空或过长：{self.name}")
        return body.strip()


class SkillCatalog:
    def __init__(self, root=SKILL_ROOT):
        root = Path(root).resolve()
        self.skills = {}
        for path in sorted(root.glob("*/SKILL.md"), key=lambda item: item.parent.name):
            if not path.resolve().is_relative_to(root):
                raise ValueError("技能文件超出技能目录")
            with path.open(encoding="utf-8-sig") as stream:
                fields = read_header(stream)
            name = fields["name"]
            if not NAME.fullmatch(name) or name != path.parent.name or name in self.skills:
                raise ValueError(f"技能名无效或重复：{name}")
            self.skills[name] = Skill(name, fields["description"], path)

    def render(self):
        return "技能目录\n" + "\n".join(
            f"- {skill.name}: {skill.description}" for skill in self.skills.values()
        )

    def match(self, prompt):
        text = prompt.strip()
        if text.startswith("/skill "):
            name = text.split(maxsplit=2)[1]
            if name not in self.skills:
                raise ValueError(f"技能未找到：{name}")
            return name
        for prefix in ("请帮我", "麻烦", "请"):
            if text.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break
        for skill in self.skills.values():
            for phrase in skill.triggers:
                if text == phrase:
                    return skill.name
                if text.startswith(phrase) and text[len(phrase)] in BOUNDARIES:
                    suffix = text[len(phrase):].lstrip()
                    if suffix.startswith(("是什么", "是什么意思", "怎么用", "的原理", "指什么", "是指", "有什么区别")):
                        continue
                    return skill.name
        return None

    def use_skill(self, name):
        return f"本轮技能 {name}\n\n{self.skills[name].load_body()}"


def skill_script_path(name):
    return SKILL_ROOT / name / "scripts" / SCRIPTS[name]


def skill_script_argv(name, *arguments):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--skill-script", name, *arguments]
    return [sys.executable, "-B", str(skill_script_path(name)), *arguments]
