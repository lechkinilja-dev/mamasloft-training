"""Build deterministic employee-training modules from site-guide topics.

The lecture is copied verbatim from ``topics.json``. Quizzes and simulation
briefs are reviewed source-controlled data, so rebuilding never silently
changes questions and never requires an external model or API key.
"""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path

from iva_modules import IVA_QUIZZES, IVA_SIM_BRIEFS, IVA_TOPICS
from site_quizzes import QUIZZES, SIM_BRIEFS


OUTPUT_DIR = Path(__file__).parent / "output"
PUBLIC_CONTENT_FILES = [
    Path(__file__).parents[1] / "docs" / "content.json",
    Path(__file__).parents[1] / "web" / "content.json",
]


class _HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current: str | None = None
        self.buffer: list[str] = []
        self.headings: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h2", "h3"}:
            self.current = tag
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.current:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.current:
            label = " ".join(html.unescape("".join(self.buffer)).split())
            if label:
                self.headings.append((tag, label))
            self.current = None
            self.buffer = []


def _knowledge_map(topic: dict) -> tuple[dict, str]:
    parser = _HeadingParser()
    parser.feed(topic["lecture_html"])

    # Prefer the article's main sections. Add selected subheads only when a
    # short guide would otherwise have fewer than eight total nodes.
    h2 = [(tag, label) for tag, label in parser.headings if tag == "h2"]
    selected = h2[:14]
    if len(selected) < 7:
        seen = {label for _, label in selected}
        for heading in parser.headings:
            if heading[1] not in seen:
                selected.append(heading)
                seen.add(heading[1])
            if len(selected) >= 7:
                break

    nodes = [{"id": "1", "label": topic["title"]}]
    edges = []
    markdown = [f"# {topic['title']}"]
    parent_id = "1"
    for index, (tag, label) in enumerate(selected, 2):
        node_id = str(index)
        nodes.append({"id": node_id, "label": label})
        if tag == "h2":
            parent_id = node_id
            edges.append({"from": "1", "to": node_id})
            markdown.append(f"## {label}")
        else:
            edges.append({"from": parent_id, "to": node_id})
            markdown.append(f"### {label}")

    if not 8 <= len(nodes) <= 15:
        raise ValueError(
            f"Knowledge map for {topic['slug']} has {len(nodes)} nodes; expected 8–15"
        )
    return {"nodes": nodes, "edges": edges}, "\n".join(markdown)


def _module(topic: dict) -> dict:
    slug = topic["slug"]
    quiz = {**QUIZZES, **IVA_QUIZZES}.get(slug)
    if quiz is None:
        raise KeyError(f"No reviewed quiz for {slug}")
    if not 10 <= len(quiz) <= 15:
        raise ValueError(f"Quiz for {slug} must contain 10–15 questions")
    knowledge_map, mindmap_md = _knowledge_map(topic)
    return {
        "topic": topic["title"],
        "slug": slug,
        "source_url": topic["source_url"],
        "source_commit": topic["source_commit"],
        "lecture_html": topic["lecture_html"],
        "mindmap": knowledge_map,
        "mindmap_md": mindmap_md,
        "quiz": quiz,
        "sim_brief": {**SIM_BRIEFS, **IVA_SIM_BRIEFS}[slug],
        "category": topic.get("category", "Статьи"),
        "published": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="Build only one topic by exact title")
    args = parser.parse_args()

    topics_path = OUTPUT_DIR / "topics.json"
    topics = json.loads(topics_path.read_text(encoding="utf-8")) + IVA_TOPICS
    if args.topic:
        topics = [topic for topic in topics if topic["title"] == args.topic]
        if not topics:
            raise ValueError(f"Topic not found: {args.topic!r}")

    modules = [_module(topic) for topic in topics]
    output = json.dumps(modules, ensure_ascii=False, indent=2) + "\n"
    content_path = OUTPUT_DIR / "content.json"
    content_path.write_text(output, encoding="utf-8")
    for public_path in PUBLIC_CONTENT_FILES:
        public_path.write_text(output, encoding="utf-8")

    for module in modules:
        print(
            f"  ✓ {module['topic']}: lecture={len(module['lecture_html'])} chars, "
            f"quiz={len(module['quiz'])}, nodes={len(module['mindmap']['nodes'])}"
        )
    print(f"Saved {len(modules)} modules → {content_path} and public copies")


if __name__ == "__main__":
    main()
