import unittest

from yingda.bm25 import BM25Index

KB = [
    {"chunk_id": 1, "title": "退款政策", "text": "购买后 7 天内且使用不超过 1GB，可以全额退款。"},
    {"chunk_id": 2, "title": "退款政策", "text": "超过 7 天按剩余月份比例退款，另收 10 元手续费。"},
    {"chunk_id": 3, "title": "发票", "text": "电子普票 24 小时内开出，改抬头 30 天内可重开一次。"},
    {"chunk_id": 4, "title": "账号", "text": "账号被盗先冻结，核验实名后 7 个工作日内答复。"},
]


class TestBM25(unittest.TestCase):
    def test_refund_within_seven_days(self):
        hits = BM25Index(KB).search("买了三天能全额退吗")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["chunk_id"], 1)

    def test_invoice(self):
        hits = BM25Index(KB).search("发票抬头写错了能改吗")
        self.assertEqual(hits[0]["chunk_id"], 3)

    def test_account_theft(self):
        hits = BM25Index(KB).search("账号被盗了怎么办")
        self.assertEqual(hits[0]["chunk_id"], 4)

    def test_no_related(self):
        self.assertEqual(BM25Index(KB).search("你们招人吗"), [])

    def test_top_k(self):
        self.assertLessEqual(len(BM25Index(KB).search("退款", top_k=2)), 2)

    def test_empty(self):
        self.assertEqual(BM25Index([]).search("退款"), [])


if __name__ == "__main__":
    unittest.main()
