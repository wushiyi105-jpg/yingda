import os
import tempfile
import unittest

from yingda.text import DocError, paragraphs, read_document, strip_html, tokenize


class TestText(unittest.TestCase):
    def test_paragraphs_split(self):
        text = "第一段完整内容\n\n第二段完整内容"
        self.assertEqual(paragraphs(text), ["第一段完整内容", "第二段完整内容"])

    def test_long_paragraph_hard_split(self):
        text = "很长" * 500
        ps = paragraphs(text, max_len=200)
        self.assertGreater(len(ps), 1)
        for p in ps:
            self.assertLessEqual(len(p), 200)

    def test_tokenize(self):
        toks = tokenize("退款政策 2026")
        self.assertIn("退款", toks)
        self.assertIn("政策", toks)
        self.assertIn("2026", toks)

    def test_strip_html(self):
        raw = "<style>.a{}</style><p>发票</p><script>x=1</script>"
        out = strip_html(raw)
        self.assertIn("发票", out)
        self.assertNotIn("x=1", out)

    def test_read_markdown_title(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# 退款政策\n\n7 天内可全额退款。")
            path = f.name
        try:
            title, text = read_document(path)
            self.assertEqual(title, "退款政策")
            self.assertIn("7 天", text)
        finally:
            os.unlink(path)

    def test_unsupported_ext(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF")
            path = f.name
        try:
            with self.assertRaises(DocError):
                read_document(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
