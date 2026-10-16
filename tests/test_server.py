from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest


TEMP = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = str(Path(TEMP.name) / "data")
os.environ["SEED_PATH"] = str(Path(__file__).parents[1] / "docs" / "content.json")

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "server"))
import server


class FakeAuth:
    def authenticate(self, pin: str):
        if pin == "admin":
            return {"ok": True, "name": "Илья", "role": "admin"}
        if pin == "user":
            return {"ok": True, "name": "Сотрудник", "role": "consultant"}
        return {"ok": False, "error": "Неверный PIN"}

    def call(self, route: str, **body):
        if route == "admin_data":
            return {"ok": True, "users": [{"name": "Илья"}, {"name": "Сотрудник"}], "progress": {}}
        raise AssertionError(route)


server.AUTH = FakeAuth()


class ServerRpcTest(unittest.TestCase):
    def test_public_content_contains_eight_published_topics(self):
        result = server.rpc({"route": "content_get"})
        self.assertEqual(len(result["modules"]), 8)
        self.assertEqual(sum(module["slug"].startswith("iva-design") for module in result["modules"]), 2)

    def test_employee_progress_and_attempts(self):
        slug = server.rpc({"route": "content_get"})["modules"][0]["slug"]
        server.rpc({"route": "progress", "pin": "user", "slug": slug, "stage": "lecture"})
        server.rpc({"route": "test", "pin": "user", "slug": slug, "score": 70})
        server.rpc({"route": "test", "pin": "user", "slug": slug, "score": 90})
        progress = server.rpc({"route": "progress_get", "pin": "user"})["progress"][slug]
        self.assertTrue(progress["lecture"])
        self.assertEqual(progress["best"], 90)
        self.assertEqual(len(progress["attempts"]), 2)

    def test_admin_can_hide_and_publish_without_losing_topic(self):
        payload = server.rpc({"route": "admin_content_get", "pin": "admin"})
        slug = payload["modules"][0]["slug"]
        hidden = server.rpc({"route": "admin_mutate", "pin": "admin", "action": "hide", "slug": slug, "version": payload["meta"]["version"]})
        self.assertEqual(len(server.rpc({"route": "content_get"})["modules"]), 7)
        server.rpc({"route": "admin_mutate", "pin": "admin", "action": "publish", "slug": slug, "version": hidden["meta"]["version"]})
        self.assertEqual(len(server.rpc({"route": "content_get"})["modules"]), 8)

    def test_consultant_cannot_edit_content(self):
        with self.assertRaises(PermissionError):
            server.rpc({"route": "admin_content_get", "pin": "user"})


if __name__ == "__main__":
    unittest.main()
