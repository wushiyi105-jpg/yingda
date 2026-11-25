"""把一封邮件 / 一段粘贴的文本变成工单。

.eml 用标准库 email 解析，优先取 text/plain，没有就抽 HTML 正文。
"""

from __future__ import annotations

import email
import os
import re
from email import policy

from .text import clean_text, strip_html


class IntakeError(Exception):
    """读不进来。"""


def _part_text(part) -> str:
    """取一个 MIME 部分的正文。

    不用 part.get_content()：没有声明 charset 的邮件（很多手工导出的 .eml 就是这样）
    会被按 ascii 解一次，中文全变成乱码。这里自己拿字节，再按 utf-8 兜底。
    """
    payload = None
    try:
        payload = part.get_payload(decode=True)
    except Exception:  # noqa: BLE001
        payload = None
    if payload is None:
        return str(part.get_payload() or "")
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def read_eml(path: str) -> dict:
    if not os.path.isfile(path):
        raise IntakeError(f"文件不存在：{path}")
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not body:
                body = _part_text(part)
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body = strip_html(_part_text(part))
                    break
    else:
        raw = _part_text(msg)
        body = strip_html(raw) if msg.get_content_type() == "text/html" else raw

    body = clean_text(str(body or ""))
    if not body:
        raise IntakeError("邮件里没有可读的正文")

    return {
        "subject": str(msg.get("subject") or "").strip(),
        "from_addr": str(msg.get("from") or "").strip(),
        "body": body,
        "channel": "email",
    }


def read_text_ticket(path: str, subject: str = "", from_addr: str = "") -> dict:
    if not os.path.isfile(path):
        raise IntakeError(f"文件不存在：{path}")
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    body = clean_text(raw)
    if not body:
        raise IntakeError("文件是空的")
    return {"subject": subject or os.path.basename(path), "from_addr": from_addr, "body": body, "channel": "file"}


def from_pasted(text: str, subject: str = "", from_addr: str = "") -> dict:
    body = clean_text(text)
    if not body:
        raise IntakeError("正文是空的")
    first_line = body.split("\n")[0][:60]
    return {
        "subject": subject or (first_line if len(first_line) < 60 else first_line + "…"),
        "from_addr": from_addr,
        "body": body,
        "channel": "manual",
    }


def looks_like_email(text: str) -> bool:
    return bool(re.search(r"^Subject:", text, re.MULTILINE))
