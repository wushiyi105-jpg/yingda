import os
import tempfile
import unittest

from yingda.intake import (
    IntakeError,
    from_pasted,
    looks_like_email,
    read_eml,
    read_text_ticket,
)

EML = """From: 林小雨 <linxy@example.com>
To: support@example.com
Subject: 发票抬头写错了
Date: 2026-11-20 10:12:00

你好，发票抬头应该是"青梧科技（上海）有限公司"，现在还能改吗？
"""


class TestIntake(unittest.TestCase):
    def test_read_eml(self):
        with tempfile.NamedTemporaryFile("w", suffix=".eml", delete=False, encoding="utf-8") as f:
            f.write(EML)
            path = f.name
        try:
            t = read_eml(path)
            self.assertEqual(t["subject"], "发票抬头写错了")
            self.assertIn("林小雨", t["from_addr"])
            self.assertIn("青梧科技", t["body"])
            self.assertEqual(t["channel"], "email")
        finally:
            os.unlink(path)

    def test_read_text_ticket(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("  我要退款  \n\n订单号 123")
            path = f.name
        try:
            t = read_text_ticket(path, subject="退款", from_addr="x@y.z")
            self.assertEqual(t["subject"], "退款")
            self.assertEqual(t["body"], "我要退款\n\n订单号 123")
        finally:
            os.unlink(path)

    def test_from_pasted_takes_first_line_as_subject(self):
        t = from_pasted("发票抬头错了\n税号是对的", from_addr="a@b.c")
        self.assertEqual(t["subject"], "发票抬头错了")
        self.assertEqual(t["channel"], "manual")

    def test_empty(self):
        with self.assertRaises(IntakeError):
            from_pasted("   ")

    def test_missing_file(self):
        with self.assertRaises(IntakeError):
            read_eml("不存在.eml")

    def test_looks_like_email(self):
        self.assertTrue(looks_like_email("Subject: hi\ntext"))
        self.assertFalse(looks_like_email("你好，我要退款"))


if __name__ == "__main__":
    unittest.main()
