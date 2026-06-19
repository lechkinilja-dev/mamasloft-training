"""
build_modules.py — для каждой темы из topics.json вызывает Claude и строит content.json.

Запуск после fetch_doc.py:
    python3 build_modules.py [--topic "Название темы"]  # без флага — все темы

Вывод: pipeline/output/content.json — массив модулей со схемой:
    {topic, lecture_html, mindmap:{nodes,edges}, mindmap_md,
     quiz:[{q,options,correct,explain}], sim_brief:{persona,need,objections,rubric}}

Assumptions:
  - ANTHROPIC_API_KEY задан в .env или окружении.
  - Используется модель claude-sonnet-4-6.
  - При ошибке парсинга JSON для одной темы она пропускается (остальные сохраняются).
  - Если content.json уже существует — дополняется новыми темами, не перезаписывается целиком.
"""

import argparse
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "prompts"
OUTPUT_DIR = Path(__file__).parent / "output"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


def _strip_fences(raw: str) -> str:
    """Remove ```json ... ``` wrappers if Claude adds them despite instructions."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    return raw.strip()


def build_module(client: anthropic.Anthropic, topic: dict) -> dict:
    system = _load_prompt("system")
    user = (
        _load_prompt("module")
        .replace("{{TOPIC_TITLE}}", topic["title"])
        .replace("{{TOPIC_CONTENT}}", topic["content"])
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = _strip_fences(msg.content[0].text)
    data = json.loads(raw)
    data["topic"] = topic["title"]
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="Build only one topic by exact title")
    args = parser.parse_args()

    topics_path = OUTPUT_DIR / "topics.json"
    if not topics_path.exists():
        raise FileNotFoundError("Run fetch_doc.py first to generate pipeline/output/topics.json")

    topics = json.loads(topics_path.read_text(encoding="utf-8"))
    if args.topic:
        topics = [t for t in topics if t["title"] == args.topic]
        if not topics:
            raise ValueError(f"Topic not found: {args.topic!r}")

    # Load existing modules so we can skip already-built topics
    content_path = OUTPUT_DIR / "content.json"
    existing: list[dict] = []
    if content_path.exists():
        existing = json.loads(content_path.read_text(encoding="utf-8"))
    existing_titles = {m["topic"] for m in existing}

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    modules = list(existing)

    for i, topic in enumerate(topics, 1):
        if topic["title"] in existing_titles and not args.topic:
            print(f"[{i}/{len(topics)}] Skip (already built): {topic['title']}")
            continue
        print(f"[{i}/{len(topics)}] Building: {topic['title']}...")
        try:
            module = build_module(client, topic)
            # Replace if re-building single topic
            modules = [m for m in modules if m["topic"] != topic["title"]]
            modules.append(module)
            print(f"  ✓ lecture={len(module.get('lecture_html',''))}c  "
                  f"quiz={len(module.get('quiz',[]))}q  "
                  f"nodes={len(module.get('mindmap',{}).get('nodes',[]))}")
        except json.JSONDecodeError as exc:
            print(f"  ✗ JSON parse error: {exc}")
        except Exception as exc:
            print(f"  ✗ Error: {exc}")

    content_path.write_text(
        json.dumps(modules, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nDone. {len(modules)} modules → {content_path}")


if __name__ == "__main__":
    main()
