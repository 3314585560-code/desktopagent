"""Measure the actual Skill catalog and exercise the Agent trigger path."""
import hashlib
import json
from pathlib import Path
import re
from threading import Event
from unittest.mock import patch

from agent_core import Agent, TOOLS
from skills_runtime import SKILL_ROOT, Skill, SkillCatalog

TRIALS = (
    ("帮我跑一下测试", "run-tests"),
    ("测一下：只跑单元测试", "run-tests"),
    ("把这段 diff 审一遍", "review-diff"),
    ("请审查代码改动：只看 README.md", "review-diff"),
    ("获取 GitHub Issue：octocat/Hello-World #1", "fetch-issue"),
    ("帮我看一下 Issue：octocat/Hello-World #1", "fetch-issue"),
    ("今天天气怎么样", None),
    ("不要跑测试，只解释测试覆盖率是什么", None),
)


def inspect_skills(tokenizer_path):
    from tokenizers import Tokenizer

    tokenizer_path = Path(tokenizer_path)
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    digest = hashlib.sha256(tokenizer_path.read_bytes()).hexdigest()
    source = ("DeepSeek 官方 V4 离线分词器" if digest ==
              "89085f12ef79460ac5f66d1119325ddfc694b4ab209d80bbd81d35f081dc9614"
              else "自定义 tokenizer.json")
    catalog = SkillCatalog()
    loaded = []
    original_loader = Skill.load_body

    def tracked_load(skill):
        loaded.append(skill.name)
        return original_loader(skill)

    def trial(query, expected, enabled):
        loaded.clear()
        events = []
        requests = []

        def reply(payload, key, cancel):
            requests.append({**payload, "input": list(payload["input"])})
            if len(requests) == 1:
                assert not loaded, "首次模型请求之前加载了技能正文"
                assert all(item.get("role") != "system" for item in payload["input"])
                candidate = re.search(r"本次请求按描述匹配：([a-z0-9-]+)。", payload["instructions"])
                if candidate:
                    return {"output": [{
                        "type": "function_call", "name": "read", "call_id": "skill_load",
                        "arguments": json.dumps({"path": "skill:" + candidate[1]}),
                    }]}
            else:
                outputs = [item for item in payload["input"] if item.get("type") == "function_call_output"]
                assert outputs and outputs[-1]["call_id"] == "skill_load"
                assert loaded and outputs[-1]["output"].startswith("本轮技能 " + loaded[-1])
            return {"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "验收替身回复"},
            ]}]}

        agent = Agent(SKILL_ROOT.parent, events.append, Event(), key="inspect-only", request=reply)
        with patch.dict("os.environ", {"ENABLE_SKILLS": "1" if enabled else "0"}):
            with patch.object(Agent, "connect", return_value=[]):
                agent.run(query)
        payload = requests[0]
        hits = [item["name"] for item in events if item["kind"] == "skill"]
        hit = hits[0] if hits else None
        assert hits == loaded and len(hits) <= 1
        assert payload["input"][-1]["content"] == query and payload["tools"] == TOOLS
        assert (catalog.render() in payload["instructions"]) == enabled
        return {"query": query, "expected": expected, "hit": hit, "ok": hit == expected,
                "body_loads": len(loaded), "model_requests": len(requests)}

    with patch.object(Skill, "load_body", tracked_load):
        assert SkillCatalog().render() == catalog.render() and not loaded
        trials = [trial(query, expected, True) for query, expected in TRIALS]
        disabled = trial(TRIALS[0][0], None, False)

    def tokens(text):
        return len(tokenizer.encode(text, add_special_tokens=False).ids)

    catalog_text = catalog.render()
    bodies = {name: catalog.use_skill(name) for name in catalog.skills}
    skills = [{
        "name": name,
        "has_scripts": any((skill.path.parent / "scripts").glob("*.py")),
        "uses_mcp": "mcp__" in bodies[name],
    } for name, skill in catalog.skills.items()]
    full_text = "\n\n".join([catalog_text, *bodies.values()])
    catalog_tokens, full_tokens = tokens(catalog_text), tokens(full_text)
    ratio = full_tokens / catalog_tokens
    false_positive = sum(item["expected"] is None and item["hit"] is not None for item in trials)
    return {
        "skills": skills, "catalog_tokens": catalog_tokens, "full_tokens": full_tokens,
        "disclosure_ratio": round(ratio, 4), "trials": trials, "false_positive": false_positive,
        "disabled_trial": disabled, "tokenizer": {"source": source, "sha256": digest},
        "measurement": "计数仅包含技能目录与正文。触发验收以离线模型替身请求现有 read 工具，实跑生产路径。",
    }


def print_report(tokenizer_path, out=None):
    data = inspect_skills(tokenizer_path)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    if out is not None:
        out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
