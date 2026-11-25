import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from yingda import store
from yingda.web import make_server

TRIAGE_JSON = '{"category":"发票","priority":"P2","sentiment":"neutral","summary":"改发票抬头"}'
DRAFT_JSON = '{"reply":"30 天内可以申请重开一次。青梧客服","used_kb":[1],"uncovered":""}'
DECIDE_JSON = '{"escalate":false,"reason":"知识库有明确依据","missing_info":"","owner":"无需"}'


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.conn = store.connect(os.path.join(cls.tmp.name, "w.db"))
        store.add_kb(cls.conn, "发票", "invoice.md", ["改抬头 30 天内可申请重开一次。"])
        cls.httpd = make_server(cls.conn, port=0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.conn.close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, obj):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_page(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode("utf-8")
        self.assertIn("应答", html)

    def test_intake_and_detail(self):
        r = self.post("/api/intake", {"body": "发票抬头写错了，能改吗", "from": "a@b.c"})
        t = self.get(f"/api/ticket?id={r['id']}")["ticket"]
        self.assertEqual(t["status"], "new")
        self.assertIn("发票", t["body"])

    def test_process_and_status(self):
        r = self.post("/api/intake", {"body": "发票抬头写错了，能改吗"})
        with mock.patch("yingda.pipeline.llm.chat", side_effect=[TRIAGE_JSON, DRAFT_JSON, DECIDE_JSON]):
            p = self.post("/api/process", {"id": r["id"]})
        self.assertEqual(p["status"], "drafted")
        self.post("/api/status", {"id": r["id"], "status": "replied"})
        self.assertEqual(self.get(f"/api/ticket?id={r['id']}")["ticket"]["status"], "replied")

    def test_empty_intake(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/intake", {"body": "  "})
        self.assertEqual(ctx.exception.code, 400)

    def test_bad_status(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/status", {"id": 999, "status": "whatever"})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
