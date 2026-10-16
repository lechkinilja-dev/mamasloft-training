"""Versioned content and progress storage for the training platform."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import threading
from typing import Any


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_TAGS = {
    "p", "br", "h2", "h3", "h4", "strong", "b", "em", "i", "u",
    "ul", "ol", "li", "blockquote", "a", "table", "thead", "tbody",
    "tr", "th", "td", "hr",
}
VOID_TAGS = {"br", "hr"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed"}:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in ALLOWED_TAGS:
            return
        safe_attrs = ""
        if tag == "a":
            href = next((value for name, value in attrs if name.lower() == "href"), "") or ""
            if href.startswith(("https://", "http://", "mailto:")):
                safe_attrs = f' href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer"'
        self.output.append(f"<{tag}{safe_attrs}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed"}:
            if self.blocked_depth:
                self.blocked_depth -= 1
            return
        if not self.blocked_depth and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.output.append(escape(data))


def sanitize_html(value: str) -> str:
    parser = _Sanitizer()
    parser.feed(value)
    parser.close()
    if parser.blocked_depth:
        raise ValueError("В тексте обнаружен незакрытый небезопасный HTML-блок")
    return "".join(parser.output).strip()


class _HeadingCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tag: str | None = None
        self.buffer: list[str] = []
        self.headings: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h2", "h3"}:
            self.tag = tag
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.tag:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.tag:
            label = " ".join("".join(self.buffer).split())
            if label:
                self.headings.append((tag, label))
            self.tag = None


def build_mindmap(topic: str, lecture_html: str, quiz: list[dict[str, Any]]) -> tuple[dict, str]:
    parser = _HeadingCollector()
    parser.feed(lecture_html)
    labels: list[str] = []
    for _, label in parser.headings:
        if label not in labels:
            labels.append(label)
        if len(labels) == 14:
            break
    for question in quiz:
        label = " ".join(str(question.get("q", "")).split()).rstrip("?")
        if label and label not in labels and len(labels) < 7:
            labels.append(label[:90])
    while len(labels) < 7:
        labels.append(f"Ключевой блок {len(labels) + 1}")
    labels = labels[:14]
    nodes = [{"id": "1", "label": topic}]
    edges = []
    markdown = [f"# {topic}"]
    for index, label in enumerate(labels, 2):
        node_id = str(index)
        nodes.append({"id": node_id, "label": label})
        edges.append({"from": "1", "to": node_id})
        markdown.append(f"## {label}")
    return {"nodes": nodes, "edges": edges}, "\n".join(markdown)


def valid_mindmap(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    nodes, edges = value.get("nodes"), value.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not 8 <= len(nodes) <= 15:
        return False
    ids = [str(node.get("id", "")) for node in nodes if isinstance(node, dict)]
    if len(ids) != len(nodes) or len(set(ids)) != len(ids) or not all(ids):
        return False
    if len(edges) != len(nodes) - 1:
        return False
    children: dict[str, list[str]] = {node_id: [] for node_id in ids}
    has_parent: set[str] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            return False
        parent, child = str(edge.get("from", "")), str(edge.get("to", ""))
        if parent not in children or child not in children or child in has_parent:
            return False
        children[parent].append(child)
        has_parent.add(child)
    roots = [node_id for node_id in ids if node_id not in has_parent]
    if len(roots) != 1:
        return False
    seen: set[str] = set()
    stack = roots[:]
    while stack:
        current = stack.pop()
        if current in seen:
            return False
        seen.add(current)
        stack.extend(children[current])
    return len(seen) == len(ids)


def normalize_module(raw: dict[str, Any], strict: bool = False) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Тема должна быть объектом")
    module = deepcopy(raw)
    module["topic"] = str(module.get("topic", "")).strip()
    module["slug"] = str(module.get("slug", "")).strip().lower()
    module["category"] = str(module.get("category", "Статьи")).strip() or "Статьи"
    module["source_url"] = str(module.get("source_url", "")).strip()
    module["source_commit"] = str(module.get("source_commit", "admin")).strip() or "admin"
    module["published"] = bool(module.get("published", False))
    module["deleted"] = bool(module.get("deleted", False))
    module["lecture_html"] = sanitize_html(str(module.get("lecture_html", "")))
    module["quiz"] = module.get("quiz", [])
    if not module["topic"]:
        raise ValueError("Укажите название темы")
    if not SLUG_RE.fullmatch(module["slug"]):
        raise ValueError("Системное имя должно содержать латинские буквы, цифры и дефисы")
    if not isinstance(module["quiz"], list):
        raise ValueError("Вопросы должны быть списком")

    cleaned_quiz = []
    for number, raw_question in enumerate(module["quiz"], 1):
        if not isinstance(raw_question, dict):
            raise ValueError(f"Вопрос {number} заполнен некорректно")
        options = raw_question.get("options", [])
        if not isinstance(options, list):
            raise ValueError(f"Варианты ответа в вопросе {number} заполнены некорректно")
        question = {
            "q": str(raw_question.get("q", "")).strip(),
            "options": [str(option).strip() for option in options],
            "correct": raw_question.get("correct", 0),
            "explain": str(raw_question.get("explain", "")).strip(),
        }
        try:
            question["correct"] = int(question["correct"])
        except (TypeError, ValueError):
            question["correct"] = -1
        cleaned_quiz.append(question)
    module["quiz"] = cleaned_quiz

    if strict:
        if len(module["lecture_html"]) < 80:
            raise ValueError("Перед публикацией заполните текст темы")
        if not 10 <= len(cleaned_quiz) <= 15:
            raise ValueError("Для публикации нужно от 10 до 15 вопросов")
        for number, question in enumerate(cleaned_quiz, 1):
            if not question["q"] or not question["explain"]:
                raise ValueError(f"Заполните вопрос и пояснение №{number}")
            if len(question["options"]) != 4 or any(not option for option in question["options"]):
                raise ValueError(f"В вопросе №{number} должно быть ровно 4 заполненных варианта")
            if question["correct"] not in range(4):
                raise ValueError(f"Выберите правильный ответ в вопросе №{number}")

    if valid_mindmap(module.get("mindmap")) and str(module.get("mindmap_md", "")).strip():
        module["mindmap"] = deepcopy(module["mindmap"])
        module["mindmap_md"] = str(module["mindmap_md"]).strip()
    else:
        mindmap, mindmap_md = build_mindmap(module["topic"], module["lecture_html"], cleaned_quiz)
        module["mindmap"] = mindmap
        module["mindmap_md"] = mindmap_md
    module.setdefault("sim_brief", {"persona": "", "need": "", "objections": [], "rubric": []})
    return module


class ContentStore:
    def __init__(self, data_dir: Path, seed_path: Path) -> None:
        self.data_dir = data_dir
        self.content_path = data_dir / "content.json"
        self.meta_path = data_dir / "content.meta.json"
        self.revisions_dir = data_dir / "revisions"
        self.audit_path = data_dir / "content.audit.jsonl"
        self.lock = threading.RLock()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.revisions_dir.mkdir(parents=True, exist_ok=True)
        if not self.content_path.exists():
            payload = json.loads(seed_path.read_text(encoding="utf-8"))
            atomic_json(self.content_path, [normalize_module(item, strict=True) for item in payload])
            atomic_json(self.meta_path, {"version": 1, "updated_at": utc_now(), "updated_by": "seed"})

    def _meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {"version": 1, "updated_at": utc_now(), "updated_by": "unknown"}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def _modules(self) -> list[dict[str, Any]]:
        return json.loads(self.content_path.read_text(encoding="utf-8"))

    def public_modules(self) -> list[dict[str, Any]]:
        with self.lock:
            return [item for item in self._modules() if item.get("published") and not item.get("deleted")]

    def admin_payload(self) -> dict[str, Any]:
        with self.lock:
            return {"modules": self._modules(), "meta": self._meta()}

    def mutate(
        self,
        action: str,
        raw_module: dict[str, Any] | None,
        slug: str,
        expected_version: int,
        actor: str,
    ) -> dict[str, Any]:
        with self.lock:
            modules = self._modules()
            meta = self._meta()
            if int(expected_version) != int(meta["version"]):
                raise ValueError("Контент уже изменён в другой вкладке. Обновите данные и повторите.")
            index = next((i for i, item in enumerate(modules) if item.get("slug") == slug), -1)
            if action == "save":
                if raw_module is None:
                    raise ValueError("Нет данных темы")
                candidate = deepcopy(raw_module)
                candidate["lecture_html"] = sanitize_html(str(candidate.get("lecture_html", "")))
                if index >= 0 and candidate["lecture_html"] != str(modules[index].get("lecture_html", "")):
                    candidate.pop("mindmap", None)
                    candidate.pop("mindmap_md", None)
                normalized = normalize_module(candidate, strict=bool(candidate.get("published")))
                duplicate = next(
                    (item for i, item in enumerate(modules) if i != index and item.get("slug") == normalized["slug"]),
                    None,
                )
                if duplicate:
                    raise ValueError("Тема с таким системным именем уже существует")
                if index >= 0:
                    modules[index] = normalized
                else:
                    modules.append(normalized)
            elif action in {"publish", "hide", "delete", "restore"}:
                if index < 0:
                    raise ValueError("Тема не найдена")
                if action == "publish":
                    modules[index]["published"] = True
                    modules[index]["deleted"] = False
                    modules[index] = normalize_module(modules[index], strict=True)
                elif action == "hide":
                    modules[index]["published"] = False
                elif action == "delete":
                    modules[index]["published"] = False
                    modules[index]["deleted"] = True
                else:
                    modules[index]["deleted"] = False
            else:
                raise ValueError("Неизвестное действие")

            old_version = int(meta["version"])
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            atomic_json(self.revisions_dir / f"content-v{old_version}-{stamp}.json", self._modules())
            new_meta = {"version": old_version + 1, "updated_at": utc_now(), "updated_by": actor}
            atomic_json(self.content_path, modules)
            atomic_json(self.meta_path, new_meta)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": new_meta["updated_at"], "actor": actor, "action": action, "slug": slug}, ensure_ascii=False) + "\n")
            return {"modules": modules, "meta": new_meta}


class ProgressStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "progress.json"
        self.lock = threading.RLock()
        if not self.path.exists():
            atomic_json(self.path, {"users": {}, "updated_at": utc_now()})

    def _payload(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, user: str) -> dict[str, Any]:
        with self.lock:
            return deepcopy(self._payload().get("users", {}).get(user, {}))

    def all(self) -> dict[str, Any]:
        with self.lock:
            return deepcopy(self._payload().get("users", {}))

    def mark(self, user: str, slug: str, stage: str, score: int | None = None) -> dict[str, Any]:
        with self.lock:
            payload = self._payload()
            progress = payload.setdefault("users", {}).setdefault(user, {}).setdefault(slug, {})
            if stage in {"lecture", "mindmap"}:
                progress[stage] = True
            elif stage == "quiz" and score is not None:
                score = max(0, min(100, int(score)))
                progress["quiz"] = score
                progress["best"] = max(score, int(progress.get("best", 0)))
                progress.setdefault("attempts", []).append({"score": score, "at": utc_now()})
            else:
                raise ValueError("Неизвестный этап")
            payload["updated_at"] = utc_now()
            atomic_json(self.path, payload)
            return deepcopy(progress)

    def import_legacy(self, legacy: dict[str, Any], title_to_slug: dict[str, str]) -> None:
        with self.lock:
            payload = self._payload()
            if payload.get("users"):
                return
            users: dict[str, Any] = {}
            for user, topics in legacy.items():
                converted = {}
                for title, progress in topics.items():
                    slug = title_to_slug.get(title)
                    if slug:
                        converted[slug] = deepcopy(progress)
                users[user] = converted
            payload["users"] = users
            payload["updated_at"] = utc_now()
            payload["migrated_from"] = "google-sheets"
            atomic_json(self.path, payload)
