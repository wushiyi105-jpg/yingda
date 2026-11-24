import os
import tempfile
import unittest

from yingda import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_add_and_get_ticket(self):
        tid = store.add_ticket(self.conn, "我要退款", subject="退款", from_addr="a@b.c")
        t = store.get_ticket(self.conn, str(tid))
        self.assertEqual(t["status"], "new")
        self.assertEqual(t["subject"], "退款")
        self.assertEqual(t["from_addr"], "a@b.c")

    def test_triage_and_status(self):
        tid = store.add_ticket(self.conn, "我要退款")
        store.save_triage(self.conn, tid, {"category": "退款退货", "priority": "P1", "sentiment": "angry", "summary": "要退款"})
        t = store.get_ticket(self.conn, str(tid))
        self.assertEqual(t["category"], "退款退货")
        self.assertEqual(t["priority"], "P1")

        store.save_draft(self.conn, tid, "草稿正文")
        store.save_decision(self.conn, tid, {"escalate": True, "reason": "涉及金额", "missing_info": "订单号"})
        store.set_status(self.conn, tid, "escalated")
        t = store.get_ticket(self.conn, str(tid))
        self.assertEqual(t["draft"], "草稿正文")
        self.assertEqual(t["escalate"], 1)
        self.assertEqual(t["missing_info"], "订单号")
        self.assertEqual(t["status"], "escalated")
        self.assertTrue(t["handled_at"])

    def test_list_by_status(self):
        a = store.add_ticket(self.conn, "A")
        b = store.add_ticket(self.conn, "B")
        store.set_status(self.conn, b, "replied")
        self.assertEqual([t["id"] for t in store.list_tickets(self.conn, status="new")], [a])
        self.assertEqual([t["id"] for t in store.list_tickets(self.conn, status="replied")], [b])

    def test_kb_add_and_replace(self):
        n = store.add_kb(self.conn, "退款政策", "refund.md", ["段落一", "段落二"])
        self.assertEqual(n, 2)
        store.add_kb(self.conn, "退款政策", "refund.md", ["新段落"])
        chunks = store.kb_chunks(self.conn)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "新段落")

    def test_kb_sources_and_remove(self):
        store.add_kb(self.conn, "退款政策", "refund.md", ["a", "b"])
        store.add_kb(self.conn, "发票", "invoice.md", ["c"])
        srcs = store.list_kb_sources(self.conn)
        self.assertEqual(len(srcs), 2)
        self.assertEqual(store.remove_kb(self.conn, "refund.md"), 2)
        self.assertEqual(store.kb_stats(self.conn)["sources"], 1)

    def test_stats(self):
        store.add_ticket(self.conn, "A")
        t2 = store.add_ticket(self.conn, "B")
        store.set_status(self.conn, t2, "escalated")
        st = store.stats(self.conn)
        self.assertEqual(st["total"], 2)
        self.assertEqual(st["new"], 1)
        self.assertEqual(st["escalated"], 1)


if __name__ == "__main__":
    unittest.main()
