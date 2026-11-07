"""在隔离副本验证图库、配置凭据及归档文件的读写边界。"""
import logging
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class LibraryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(__file__).resolve().parents[1] / "app"
        root = Path(cls.temp.name) / "app"
        root.mkdir()
        for module in source.glob("*.py"):
            shutil.copy2(module, root)
        for folder in ("templates", "static"):
            shutil.copytree(source / folder, root / folder)
        sys.path.insert(0, str(root))
        cls.addClassCleanup(sys.path.remove, str(root))
        cls.addClassCleanup(logging.shutdown)
        import server
        cls.server = server
        cls.client = TestClient(server.app)
        cls.addClassCleanup(cls.client.close)

    def test_clients_merge_independent_changes(self):
        start = self.client.get("/api/gallery/flags").json()
        with TestClient(self.server.app) as phone:
            for client, model in [(self.client, "MW_A"), (phone, "MW_B")]:
                response = client.patch("/api/gallery/flags", json={
                    "before": start, "after": {**start, "favorites": [model]}
                })
                self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.client.get("/api/gallery/flags").json()["favorites"]), {"MW_A", "MW_B"})

    def test_manual_archive_and_download(self):
        response = self.client.post("/api/models/manual", data={
            "title": "离线测试模型", "summary_html": '<p>说明</p><img src="pic.jpg" onerror="bad_handler()">'
        }, files={"attachments": ("guide.txt", b"sample attachment", "text/plain")})
        self.assertEqual(response.status_code, 200, response.text)
        items = self.client.get("/api/mobile/library").json()["items"]
        key = next(item["id"] for item in items if item["title"] == "离线测试模型")
        offline = self.client.get(f"/files/{key}/index.html")
        self.assertEqual(offline.status_code, 200)
        self.assertNotIn("bad_handler()", offline.text)
        download = self.client.get(f"/api/models/{key}/file/file/guide.txt")
        self.assertEqual(download.content, b"sample attachment")

    def test_plugin_archive_entry(self):
        url = "https://makerworld.com.cn/zh/models/12345-example"
        origin = {"Origin": "chrome-extension://" + "a" * 32}
        with patch.object(self.server, "_ensure_archive_worker_running"):
            response = self.client.post("/api/archive", headers=origin, json={"url": url})
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task"]["task_id"]
        self.assertEqual(self.client.get(f"/api/archive/tasks/{task_id}").status_code, 200)
        status = self.client.get("/api/archive/status/12345", headers={"Origin": "https://makerworld.com.cn"})
        self.assertEqual(status.headers["access-control-allow-origin"], "https://makerworld.com.cn")
        self.assertNotIn("access-control-allow-origin", self.client.get("/api/cookies", headers=origin).headers)

    def test_protect_and_retain_credentials(self):
        body = {"platform": "cn", "cookie": "test_cookie_value"}
        response = self.client.post("/api/cookie", json=body, headers={"Origin": "https://untrusted.invalid"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/api/cookie", json=body).status_code, 200)
        for route in ("/api/config", "/api/cookies", "/api/mobile/settings"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(body["cookie"], response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
        public = self.client.get("/api/cookies").json()["cookie_store"]
        self.assertEqual(self.client.post("/api/cookies", json={"cookie_store": public}).status_code, 200)
        self.assertEqual(self.server.load_cookie_store()["cn"][0]["value"], body["cookie"])

    def test_archive_file_and_index(self):
        import json
        import gallery_index
        root = Path(self.server.CFG["download_dir"])
        models = []
        for name in ("MW_A", "MW_B"):
            model = root / name
            model.mkdir(exist_ok=True)
            meta = {"title": name, "summary": {"html": '<img src="local.jpg" onerror="unsafe()">'}, "instances": []}
            (model / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            html = self.server.build_index_html(meta)
            self.assertIn("__OFFLINE_META__", html)
            self.assertNotIn("unsafe()", html)
            (model / "index.html").write_text(html, encoding="utf-8")
            models.append(model)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda m: gallery_index.upsert_gallery_index_entry(root, m), models))
        with patch.object(self.server, "rebuild_gallery_index", side_effect=AssertionError):
            for _ in range(2):
                payload = self.client.get("/api/mobile/library").json()
                self.assertEqual({x["id"] for x in payload["items"]}, {"MW_A", "MW_B"})
        for url in ("/v2/files/MW_A", "/files/MW_A/index.html", "/api/models/MW_A/file/meta.json"):
            self.assertEqual(self.client.get(url).status_code, 200)
        bad = "../server.py".encode().hex()
        self.assertEqual(self.client.get(f"/api/bambu/download/{bad}.3mf").status_code, 400)
