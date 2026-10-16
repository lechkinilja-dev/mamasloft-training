from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "server"))

from content_store import ContentStore, ProgressStore, normalize_module, sanitize_html


def valid_module(slug: str = "tema") -> dict:
    quiz = []
    for index in range(10):
        quiz.append(
            {
                "q": f"Вопрос {index + 1}?",
                "options": ["А", "Б", "В", "Г"],
                "correct": index % 4,
                "explain": "Пояснение",
            }
        )
    return {
        "topic": "Тестовая тема",
        "slug": slug,
        "lecture_html": "<h2>Раздел</h2><p>" + ("Полезный текст. " * 8) + "</p>",
        "quiz": quiz,
        "published": True,
    }


class ContentStoreTest(unittest.TestCase):
    def test_sanitizer_removes_script_and_unsafe_attributes(self) -> None:
        cleaned = sanitize_html('<p onclick="bad()">Текст<script>alert(1)</script><a href="javascript:x">ссылка</a></p>')
        self.assertEqual(cleaned, "<p>Текст<a>ссылка</a></p>")

    def test_publish_requires_ten_questions_and_four_options(self) -> None:
        module = valid_module()
        module["quiz"] = module["quiz"][:9]
        with self.assertRaisesRegex(ValueError, "от 10 до 15"):
            normalize_module(module, strict=True)
        module = valid_module()
        module["quiz"][0]["options"].pop()
        with self.assertRaisesRegex(ValueError, "ровно 4"):
            normalize_module(module, strict=True)

    def test_versioned_mutations_and_soft_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seed = root / "seed.json"
            seed.write_text(json.dumps([valid_module()]), encoding="utf-8")
            store = ContentStore(root / "data", seed)
            payload = store.admin_payload()
            self.assertEqual(payload["meta"]["version"], 1)
            saved = store.mutate("hide", None, "tema", 1, "Илья")
            self.assertEqual(saved["meta"]["version"], 2)
            self.assertEqual(store.public_modules(), [])
            deleted = store.mutate("delete", None, "tema", 2, "Илья")
            self.assertTrue(deleted["modules"][0]["deleted"])
            self.assertEqual(len(list((root / "data" / "revisions").glob("*.json"))), 2)
            with self.assertRaisesRegex(ValueError, "другой вкладке"):
                store.mutate("restore", None, "tema", 1, "Илья")

    def test_progress_keeps_attempt_history_and_best_score(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ProgressStore(Path(temp))
            store.mark("Илья", "tema", "lecture")
            store.mark("Илья", "tema", "quiz", 60)
            store.mark("Илья", "tema", "quiz", 90)
            result = store.get("Илья")["tema"]
            self.assertTrue(result["lecture"])
            self.assertEqual(result["quiz"], 90)
            self.assertEqual(result["best"], 90)
            self.assertEqual([attempt["score"] for attempt in result["attempts"]], [60, 90])


if __name__ == "__main__":
    unittest.main()
