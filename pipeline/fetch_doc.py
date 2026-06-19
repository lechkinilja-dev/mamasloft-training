"""
fetch_doc.py — читает товарные карточки из Obsidian Knowledge Base и формирует topics.json.

Источник: Memory/Products/ в Obsidian Vault (нормализованные карточки).
Вывод: pipeline/output/topics.json — массив объектов {title, content}.

Карточки определяются по README.md (wikilinks [[...]]).
Сквозные справочники (objections, glossary и т.д.) добавляются как контекст к каждой карточке.
"""

import json
import re
from pathlib import Path

VAULT = Path(
    "/Users/ilya/Library/Mobile Documents/"
    "iCloud~md~obsidian/Documents/Obsidian Vault/Memory/Products"
)
OUTPUT_DIR = Path(__file__).parent / "output"

CROSS_REF_FILES = [
    "glossary.md",
    "objections.md",
    "sales-scripts.md",
    "upsell-map.md",
    "safety-and-care.md",
]

SKIP_SECTIONS = {"Источник", "Полный фрагмент источника"}


def _parse_readme() -> list[str]:
    """Extract product card names from README.md wikilinks."""
    readme = (VAULT / "README.md").read_text(encoding="utf-8")
    names = []
    for m in re.finditer(r"\[\[([^\]]+)\]\]", readme):
        name = m.group(1)
        if name == "source-google-doc-knowledge-base":
            continue
        if name in [f.replace(".md", "") for f in CROSS_REF_FILES]:
            continue
        card_path = VAULT / f"{name}.md"
        if card_path.exists():
            names.append(name)
    return names


def _extract_card_content(path: Path) -> str:
    """Read a card .md file and return its content, skipping metadata sections."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    result = []
    skip = False

    for line in lines:
        if line.startswith("## "):
            section = line[3:].strip()
            skip = section in SKIP_SECTIONS
            if skip:
                continue
        if skip:
            continue
        if line.strip() == "Не заполнено в источнике.":
            continue
        result.append(line)

    return "\n".join(result).strip()


def _load_cross_refs() -> str:
    """Load cross-reference docs as a single context block."""
    parts = []
    for fname in CROSS_REF_FILES:
        fpath = VAULT / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").strip()
            if content:
                label = fname.replace(".md", "").replace("-", " ").title()
                parts.append(f"--- {label} ---\n{content}")
    return "\n\n".join(parts)


def main() -> None:
    print(f"Reading cards from: {VAULT}")
    names = _parse_readme()
    print(f"Found {len(names)} product cards in README.md")

    cross_refs = _load_cross_refs()
    topics = []

    for name in names:
        card_path = VAULT / f"{name}.md"
        content = _extract_card_content(card_path)
        full_content = f"{content}\n\n{cross_refs}"
        topics.append({"title": name, "content": full_content})
        print(f"  • {name} ({len(content)} chars)")

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / "topics.json"
    out.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(topics)} topics → {out}")


if __name__ == "__main__":
    main()
