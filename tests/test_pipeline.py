import os
import tempfile
import unittest
from unittest import mock

from yingda import pipeline, store

TRIAGE_JSON = '{"category":"退款退货","priority":"P1","sentiment":"neutral","summary":"想退掉刚买一年的会员","key_facts":"订单 QW2026111800321"}'
DRAFT_JSON = '{"reply":"你 11 月 18 日买的会员在 7 天内、用量 300MB 未超 1GB，可以全额退款，原路退回 3-5 个工作日到账。青梧客服","used_kb":[1],"uncovered":""}'
DECIDE_JSON = '{"escalate":false,"reason":"知识库有明确依据，金额无争议","missing_info":"","owner":"无需"}'

ESCALATE_JSON = '{"escalate":true,"reason":"涉及账号被盗与文件丢失，且客户扬言曝光","missing_info":"身份证后四位","owner":"主管"}'


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(os.path.join(self.tmp.name, "t.db"))
        store.add_kb(self.conn, "退款政策", "refund.md", [
            "购买后 7 天内，且账号已用容量不超过 1GB 的，可以申请全额退款，原路退回，到账 3—5 个工作日。",
            "超过 7 天的订单按剩余月份比例退款，另收 10 元手续费。",
        ])

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _ticket(self, body="11 月 18 日买的会员，用了 300MB，想退"):
        tid = store.add_ticket(self.conn, body, subject="退款")
        return store.get_ticket(self.conn, str(tid))

    def test_full_path_drafted(self):
        t = self._ticket()
        with mock.patch("yingda.llm.chat", side_effect=[TRIAGE_JSON, DRAFT_JSON, DECIDE_JSON]):
            r = pipeline.process(self.conn, t)
        self.assertEqual(r["status"], "drafted")
        self.assertEqual(r["triage"]["category"], "退款退货")
        self.assertTrue(r["kb_hits"])
        self.assertIn("全额退款", r["draft"]["reply"])
        self.assertFalse(r["decision"]["escalate"])

        saved = store.get_ticket(self.conn, str(t["id"]))
        self.assertEqual(saved["status"], "drafted")
        self.assertEqual(saved["draft"], r["draft"]["reply"])
        self.assertEqual(saved["escalate"], 0)

    def test_escalation(self):
        t = self._ticket("账号被盗，文件被删，我要曝光你们")
        with mock.patch("yingda.llm.chat", side_effect=[TRIAGE_JSON, DRAFT_JSON, ESCALATE_JSON]):
            r = pipeline.process(self.conn, t)
        self.assertEqual(r["status"], "escalated")
        self.assertEqual(r["decision"]["owner"], "主管")
        self.assertEqual(store.get_ticket(self.conn, str(t["id"]))["status"], "escalated")

    def test_draft_failure_forces_escalation(self):
        t = self._ticket()
        with mock.patch("yingda.llm.chat", side_effect=[TRIAGE_JSON, "这里没有 JSON", DECIDE_JSON]):
            r = pipeline.process(self.conn, t)
        self.assertTrue(r["decision"]["escalate"])
        self.assertIn("保守策略", r["decision"]["reason"])

    def test_triage_failure_defaults(self):
        with mock.patch("yingda.llm.chat", return_value="我不会 JSON"):
            t = pipeline.triage({"body": "随便", "subject": "", "channel": "email", "from_addr": ""})
        self.assertEqual(t["category"], "其他")
        self.assertEqual(t["priority"], "P2")
        self.assertTrue(t["error"])

    def test_used_kb_out_of_range_dropped(self):
        t = self._ticket()
        bad = '{"reply":"可以退。青梧客服","used_kb":[9],"uncovered":""}'
        with mock.patch("yingda.llm.chat", side_effect=[TRIAGE_JSON, bad, DECIDE_JSON]):
            r = pipeline.process(self.conn, t)
        self.assertEqual(r["draft"]["used_kb"], [])

    def test_decide_failure_conservative(self):
        t = self._ticket()
        with mock.patch("yingda.llm.chat", side_effect=[TRIAGE_JSON, DRAFT_JSON, "不知道"]):
            r = pipeline.process(self.conn, t)
        self.assertTrue(r["decision"]["escalate"])
        self.assertEqual(r["decision"]["owner"], "主管")

    def test_empty_kb_still_runs(self):
        conn2 = store.connect(os.path.join(self.tmp.name, "empty.db"))
        tid = store.add_ticket(conn2, "问个问题")
        t = store.get_ticket(conn2, str(tid))
        with mock.patch("yingda.llm.chat", side_effect=[TRIAGE_JSON, DRAFT_JSON, DECIDE_JSON]):
            r = pipeline.process(conn2, t)
        self.assertEqual(r["kb_hits"], [])
        self.assertEqual(r["status"], "drafted")
        conn2.close()


if __name__ == "__main__":
    unittest.main()
