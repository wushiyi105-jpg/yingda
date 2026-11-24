"""SQLite：tickets（工单）与 kb（知识库段落）。

tickets 把每一步的结果都存下来（分类、草稿、升级判断），
不是最后只留一个"已处理"——出了问题要能回看模型当时是怎么想的。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL DEFAULT 'email',
    from_addr       TEXT NOT NULL DEFAULT '',
    subject         TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL,
    received_at     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
    category        TEXT,
    priority        TEXT,
    sentiment       TEXT,
    summary         TEXT,
    draft           TEXT,
    escalate        INTEGER,
    escalate_reason TEXT,
    missing_info    TEXT,
    handled_at      TEXT
);
CREATE TABLE IF NOT EXISTS kb (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT NOT NULL,
    source  TEXT NOT NULL,
    ord     INTEGER NOT NULL,
    text    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_source ON kb(source);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ---------- 工单 ----------
def add_ticket(conn, body: str, subject: str = "", from_addr: str = "", channel: str = "email") -> int:
    cur = conn.execute(
        "INSERT INTO tickets(channel, from_addr, subject, body, received_at) VALUES (?,?,?,?,?)",
        (channel, from_addr, subject, body, now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_tickets(conn, status: str | None = None, limit: int = 50) -> list[dict]:
    sql = "SELECT * FROM tickets"
    args: list = []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_ticket(conn, key: str) -> dict | None:
    if str(key).isdigit():
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (int(key),)).fetchone()
        return dict(row) if row else None
    rows = conn.execute("SELECT * FROM tickets WHERE id = ?", (-1,)).fetchall()
    return dict(rows[0]) if rows else None


def save_triage(conn, ticket_id: int, triage: dict) -> None:
    conn.execute(
        "UPDATE tickets SET category=?, priority=?, sentiment=?, summary=? WHERE id=?",
        (
            triage.get("category", ""),
            triage.get("priority", ""),
            triage.get("sentiment", ""),
            triage.get("summary", ""),
            ticket_id,
        ),
    )
    conn.commit()


def save_draft(conn, ticket_id: int, draft: str) -> None:
    conn.execute("UPDATE tickets SET draft=? WHERE id=?", (draft, ticket_id))
    conn.commit()


def save_decision(conn, ticket_id: int, decision: dict) -> None:
    conn.execute(
        "UPDATE tickets SET escalate=?, escalate_reason=?, missing_info=? WHERE id=?",
        (
            1 if decision.get("escalate") else 0,
            decision.get("reason", ""),
            decision.get("missing_info", ""),
            ticket_id,
        ),
    )
    conn.commit()


def set_status(conn, ticket_id: int, status: str) -> None:
    conn.execute("UPDATE tickets SET status=?, handled_at=? WHERE id=?", (status, now(), ticket_id))
    conn.commit()


def stats(conn) -> dict:
    rows = conn.execute("SELECT status, COUNT(*) n FROM tickets GROUP BY status").fetchall()
    by = {r["status"]: r["n"] for r in rows}
    # 一开始只列了 new/replied/escalated，drafted 的数直接消失了，
    # 统计页看着像丢单。其实留出来的正是"草稿已生成、等人过目"这一档。
    out = {"total": sum(by.values())}
    for st in ("new", "drafted", "replied", "escalated"):
        out[st] = by.get(st, 0)
    return out


# ---------- 知识库 ----------
def add_kb(conn, title: str, source: str, paragraphs: list[str], replace: bool = True) -> int:
    if replace:
        conn.execute("DELETE FROM kb WHERE source = ?", (source,))
    n = 0
    for i, p in enumerate(paragraphs):
        conn.execute("INSERT INTO kb(title, source, ord, text) VALUES (?,?,?,?)", (title, source, i, p))
        n += 1
    conn.commit()
    return n


def kb_chunks(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM kb ORDER BY id").fetchall()
    return [{"text": r["text"], "title": r["title"], "chunk_id": r["id"], "ord": r["ord"]} for r in rows]


def list_kb_sources(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT source, title, COUNT(*) n FROM kb GROUP BY source, title ORDER BY MIN(id)"
    ).fetchall()
    return [dict(r) for r in rows]


def remove_kb(conn, source: str) -> int:
    cur = conn.execute("DELETE FROM kb WHERE source = ?", (source,))
    conn.commit()
    return cur.rowcount


def kb_stats(conn) -> dict:
    r = conn.execute("SELECT COUNT(*) n, COUNT(DISTINCT source) s FROM kb").fetchone()
    return {"chunks": r["n"], "sources": r["s"]}
