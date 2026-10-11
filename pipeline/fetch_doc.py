"""Build training topics from the guides currently deployed on mamasloft.ru.

The production commit is read from the same verified pointer that is used by the
website release workflow. Source files are loaded with ``git show`` so the
canonical website checkout does not have to be on that commit.

Output: ``pipeline/output/topics.json``. Each topic contains the complete
lecture HTML plus a plain-text copy for audit/search purposes.
"""

from __future__ import annotations

import ast
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess


SITE_REPO = Path(
    os.environ.get(
        "MAMASLOFT_SITE_REPO",
        "/Users/ilyadom/Claude-projects/Website_Mamasloft",
    )
)
PRODUCTION_STATE = Path(
    os.environ.get(
        "MAMASLOFT_PRODUCTION_STATE",
        "/Users/ilyadom/.agents/state/mamasloft-production.json",
    )
)
OUTPUT_DIR = Path(__file__).parent / "output"

EDITORIAL_CONTENT = "src/lib/guides/editorial-content.json"
EDITORIAL_PRESENTATION = "src/lib/guides/editorial-presentation.json"
AUTUMN_CONTENT = "src/lib/guides/autumn-guide-content.ts"
WARDROBE_ARTICLE = "public/assets/wardrobe-guide/article.html"

EDITORIAL_ORDER = [
    "kupanie-novorozhdennogo",
    "kak-stirat-detskie-veshchi",
    "chto-podarit-novorozhdennomu",
    "pervyj-prikorm-malysha",
]


class _TextExtractor(HTMLParser):
    BLOCKS = {"h1", "h2", "h3", "p", "li", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def _production_commit() -> str:
    if override := os.environ.get("MAMASLOFT_PRODUCTION_COMMIT"):
        return override.strip()
    state = json.loads(PRODUCTION_STATE.read_text(encoding="utf-8"))
    commit = str(state.get("commit", "")).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"Invalid production commit in {PRODUCTION_STATE}")
    return commit


def _git_show(commit: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(SITE_REPO), "show", f"{commit}:{relative_path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _p(text: str) -> str:
    return f"<p>{html.escape(text)}</p>"


def _list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(cell)}</th>" for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _editorial_topic(
    slug: str,
    article: dict,
    presentation: dict,
    commit: str,
) -> dict:
    chunks = [f"<p><strong>{html.escape(article['subtitle'])}</strong></p>"]
    chunks.extend(_p(text) for text in article.get("intro", []))
    if presentation.get("introNote"):
        chunks.append(_p(presentation["introNote"]))

    for section in article.get("sections", []):
        chunks.append(f"<h2>{html.escape(section['title'])}</h2>")
        for block in section.get("blocks", []):
            kind = block.get("kind")
            lead = block.get("lead")
            if lead:
                chunks.append(f"<h3>{html.escape(lead)}</h3>")
            if kind == "idea":
                label = f"{block.get('number', '')}. {block.get('title', '')}".strip()
                chunks.append(f"<h3>{html.escape(label)}</h3>")
            if block.get("text"):
                text = block["text"]
                if kind == "note":
                    chunks.append(f"<p><strong>Важно:</strong> {html.escape(text)}</p>")
                else:
                    chunks.append(_p(text))
            if block.get("items"):
                chunks.append(_list(block["items"]))
            if block.get("caption"):
                chunks.append(f"<h3>{html.escape(block['caption'])}</h3>")
            if block.get("headers") or block.get("rows"):
                chunks.append(_table(block.get("headers", []), block.get("rows", [])))

    if presentation.get("closingTitle"):
        chunks.append(f"<h2>{html.escape(presentation['closingTitle'])}</h2>")
    if presentation.get("closingText"):
        chunks.append(_p(presentation["closingText"]))
    sources = presentation.get("sources", [])
    if sources:
        chunks.append("<h2>Источники и дополнительное чтение</h2>")
        chunks.append(_list([f"{source['title']} — {source['href']}" for source in sources]))

    lecture_html = "".join(chunks)
    return {
        "title": article["title"],
        "slug": slug,
        "source_url": f"https://mamasloft.ru/guides/{slug}",
        "source_commit": commit,
        "content": _plain_text(lecture_html),
        "lecture_html": lecture_html,
    }


def _js_string(raw: str) -> str:
    return ast.literal_eval('"' + raw.replace('"', '\\"') + '"')


def _autumn_topic(source: str, commit: str) -> dict:
    pattern = re.compile(
        r"\{\s*id:\s*\"(?P<id>[^\"]+)\",\s*"
        r"temperature:\s*\"(?P<temperature>[^\"]+)\",\s*"
        r"caption:\s*\"(?P<caption>[^\"]+)\",\s*"
        r"note:\s*\"(?P<note>[^\"]+)\",\s*"
        r"layers:\s*\[(?P<layers>.*?)\],\s*\}",
        re.S,
    )
    regimes = []
    for match in pattern.finditer(source):
        layers = re.findall(r'\"((?:\\.|[^\"\\])*)\"', match.group("layers"))
        regimes.append(
            {
                "temperature": match.group("temperature"),
                "caption": match.group("caption"),
                "note": match.group("note"),
                "layers": [_js_string(value) for value in layers],
            }
        )
    if len(regimes) != 5:
        raise ValueError(f"Expected 5 temperature regimes, found {len(regimes)}")

    chunks = [
        "<p><strong>Подробная инструкция по подбору слоёв одежды на разные температурные режимы.</strong></p>",
        "<h2>Как пользоваться памяткой</h2>",
        _p("Сначала выберите температуру на улице, затем соберите комплект по слоям. Учитывайте ветер, длительность пребывания на улице, активность и комфорт малыша."),
    ]
    for regime in regimes:
        chunks.append(
            f"<h2>{html.escape(regime['temperature'])}: {html.escape(regime['caption'])}</h2>"
        )
        chunks.append(_p(regime["note"]))
        chunks.append(_list(regime["layers"]))
    chunks.extend(
        [
            "<h2>Зимний конверт или комбинезон</h2>",
            "<h3>Малыш родится в ноябре–декабре</h3>",
            _p("В качестве верхнего слоя для новорождённого рекомендуем зимний конверт."),
            "<h3>К началу зимы малышу будет 5–6 месяцев</h3>",
            _p("В качестве верхнего слоя рекомендуем зимний комбинезон."),
            _p("Утепление выбирайте по температурному режиму выше."),
            "<h2>Важное ограничение</h2>",
            _p("Температурная схема не расширяет ограничения конкретной модели. Для конвертов Leokid в подборке указан режим до −25 °C. В морозную схему демисезонный комбинезон надевают под зимний конверт."),
        ]
    )
    lecture_html = "".join(chunks)
    title = "Как одеть малыша осенью/зимой"
    return {
        "title": title,
        "slug": "osennyaya-vypiska-novorozhdennogo",
        "source_url": "https://mamasloft.ru/guides/osennyaya-vypiska-novorozhdennogo",
        "source_commit": commit,
        "content": _plain_text(lecture_html),
        "lecture_html": lecture_html,
    }


def _wardrobe_topic(source: str, commit: str) -> dict:
    match = re.search(r"const D=(\{.*?\}), V=1, KEY=", source, re.S)
    if not match:
        raise ValueError("Wardrobe checklist data was not found")
    data = json.loads(match.group(1))
    seasons = {
        "spring": "весна",
        "summer": "лето",
        "autumn": "осень",
        "winter": "зима",
    }
    groups: dict[str, list[dict]] = {}
    for category in data["categories"]:
        groups.setdefault(category["group"], []).append(category)

    chunks = [
        "<p><strong>Чеклист первого гардероба малыша к рождению.</strong></p>",
        "<h2>Как пользоваться чеклистом</h2>",
        _list(
            [
                "Выберите сезон рождения малыша: весна, лето, осень или зима.",
                "Отмечайте уже купленные категории и при необходимости подбирайте модели из каталога.",
                "Размеры 56 и 62 показаны отдельно, универсальные позиции отмечены как «Любой».",
                "Список можно сохранить в PDF или распечатать.",
            ]
        ),
        "<h2>Сезонность</h2>",
        _p("Нательная одежда и базовый текстиль нужны круглый год. Летняя группа показывается только для лета, а верхний прогулочный слой зависит от сезона."),
    ]
    for group, categories in groups.items():
        chunks.append(f"<h2>{html.escape(group)}</h2>")
        rows = []
        for category in categories:
            season_text = ", ".join(seasons[item] for item in category["seasons"])
            size = str(category["size"])
            detail = category.get("sourceDetail", "")
            if detail:
                size = f"{size}; {detail}"
            rows.append(
                [
                    category["name"],
                    category.get("quantityLabel") or f"{category['qty']} шт.",
                    size,
                    season_text,
                ]
            )
        chunks.append(_table(["Категория", "Количество", "Размер", "Сезон"], rows))
    chunks.extend(
        [
            "<h2>Количество и размеры</h2>",
            _p("Количество в чеклисте — практический ориентир, а не жёсткая норма. Его можно менять под ритм стирки, образ жизни семьи, сезон и уже купленные вещи."),
        ]
    )
    lecture_html = "".join(chunks)
    title = "Гардероб малыша — чеклист к рождению"
    return {
        "title": title,
        "slug": "garderob-malysha",
        "source_url": "https://mamasloft.ru/guides/garderob-malysha",
        "source_commit": commit,
        "content": _plain_text(lecture_html),
        "lecture_html": lecture_html,
    }


def main() -> None:
    commit = _production_commit()
    editorial = json.loads(_git_show(commit, EDITORIAL_CONTENT))
    presentation = json.loads(_git_show(commit, EDITORIAL_PRESENTATION))

    topics = [
        _editorial_topic(slug, editorial[slug], presentation[slug], commit)
        for slug in EDITORIAL_ORDER
    ]
    topics.append(_autumn_topic(_git_show(commit, AUTUMN_CONTENT), commit))
    topics.append(_wardrobe_topic(_git_show(commit, WARDROBE_ARTICLE), commit))

    OUTPUT_DIR.mkdir(exist_ok=True)
    output = OUTPUT_DIR / "topics.json"
    output.write_text(
        json.dumps(topics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Production source: {commit}")
    for topic in topics:
        print(f"  • {topic['title']} ({len(topic['lecture_html'])} chars)")
    print(f"Saved {len(topics)} site-guide topics → {output}")


if __name__ == "__main__":
    main()
