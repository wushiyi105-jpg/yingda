"""读入与切块：把知识库文档变成能被检索的段落，并给出中文分词。

零第三方依赖，所以分词是"中文单字 + 二元组"。
客服知识库一般一段就是一个完整答案，按段落切比按字数切更合理。
"""

from __future__ import annotations

import html
import os
import re

TEXT_EXTS = {".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".log"}

_CJK = r"\u4e00-\u9fff"
_TOKEN_RE = re.compile(rf"[{_CJK}]+|[a-zA-Z][a-zA-Z0-9_+#.-]*|\d+[.,]?\d*")


class DocError(Exception):
    """文档读不进来。"""


def read_document(path: str) -> tuple[str, str]:
    """读一个文件，返回 (标题, 正文)。"""
    if not os.path.isfile(path):
        raise DocError(f"文件不存在：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTS:
        raise DocError(f"暂不支持 {ext or '无扩展名'} 文件，先转成 .txt 或 .md：{path}")

    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()

    if ext in {".html", ".htm"}:
        raw = strip_html(raw)

    title = os.path.basename(path)
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            title = s.lstrip("#").strip() or title
        break

    return title, clean_text(raw)


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


def clean_text(raw: str) -> str:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in raw.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def paragraphs(text: str, max_len: int = 700) -> list[str]:
    """按空行切段；超长段落硬切。"""
    text = clean_text(text)
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_len:
            out.append(para)
        else:
            for i in range(0, len(para), max_len):
                piece = para[i : i + max_len].strip()
                if piece:
                    out.append(piece)
    return out


def tokenize(s: str) -> list[str]:
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(s or ""):
        piece = m.group(0)
        if re.fullmatch(rf"[{_CJK}]+", piece):
            if len(piece) == 1:
                tokens.append(piece)
            else:
                tokens.extend(piece)
                tokens.extend(piece[i : i + 2] for i in range(len(piece) - 1))
        else:
            tokens.append(piece.lower())
    return tokens


def token_set(s: str) -> set[str]:
    return set(tokenize(s))
