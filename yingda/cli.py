"""命令行：python -m yingda <子命令>。"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, intake, pipeline, store
from .llm import LLMError

DEFAULT_DB = os.path.join("data", "yingda.db")


def _conn(args):
    return store.connect(args.db)


# ---------- 知识库 ----------
def cmd_kb(args) -> int:
    conn = _conn(args)
    if args.kb_cmd == "add":
        from .text import DocError, paragraphs, read_document

        for path in args.paths:
            try:
                title, text = read_document(path)
                ps = paragraphs(text)
                n = store.add_kb(conn, title, os.path.abspath(path), ps)
                print(f"✓ {title} —— {n} 段入库")
            except (DocError, ValueError) as e:
                print(f"✗ {path}：{e}", file=sys.stderr)
        print("知识库：", store.kb_stats(conn))
    elif args.kb_cmd == "list":
        srcs = store.list_kb_sources(conn)
        if not srcs:
            print("知识库是空的。用 kb add 导入。")
        for s in srcs:
            print(f"  {s['title']}  {s['n']} 段  {s['source']}")
        print("  ", store.kb_stats(conn))
    elif args.kb_cmd == "rm":
        n = store.remove_kb(conn, args.source)
        print(f"删了 {n} 段。" if n else "没找到这个来源。")
    return 0


# ---------- 工单 ----------
def cmd_intake(args) -> int:
    conn = _conn(args)
    try:
        if args.file:
            if args.file.lower().endswith(".eml"):
                t = intake.read_eml(args.file)
            else:
                t = intake.read_text_ticket(args.file, subject=args.subject, from_addr=args.from_addr)
        else:
            t = intake.from_pasted(args.text, subject=args.subject, from_addr=args.from_addr)
    except intake.IntakeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    tid = store.add_ticket(conn, t["body"], t["subject"], t["from_addr"], t["channel"])
    print(f"✓ 工单 [{tid}] 已入队：{t['subject'] or '（无标题）'}")
    print("   跑管线：python -m yingda process --id " + str(tid))
    return 0


def cmd_process(args) -> int:
    conn = _conn(args)
    if args.id:
        t = store.get_ticket(conn, str(args.id))
        if not t:
            print("没有这张工单。", file=sys.stderr)
            return 1
        tickets = [t]
    else:
        tickets = store.list_tickets(conn, status="new", limit=args.limit)
    if not tickets:
        print("没有待处理的工单。")
        return 0

    failed = 0
    for t in tickets:
        try:
            r = pipeline.process(conn, t)
        except LLMError as e:
            print(f"✗ [{t['id']}] 模型调用失败：{e}", file=sys.stderr)
            failed += 1
            continue
        _print_result(r)
    print()
    print("工单统计：", store.stats(conn))
    return 1 if failed else 0


def _print_result(r: dict) -> None:
    t, d, dec = r["triage"], r["draft"], r["decision"]
    print(f"\n=== 工单 [{r['ticket_id']}] → {r['status']} ===")
    print(f"分诊：{t['category']} / {t['priority']} / 情绪 {t['sentiment']}")
    print(f"     {t['summary']}")
    print(f"知识库命中 {len(r['kb_hits'])} 段：")
    for i, h in enumerate(r["kb_hits"], 1):
        print(f"     [{i}] {h['title']}（{h['score']}）{h['text'][:60].replace(chr(10), ' ')}…")
    print("草稿：")
    for line in (d["reply"] or "").split("\n"):
        print("     " + line)
    flag = "转人工" if dec["escalate"] else "可直接回"
    print(f"判断：{flag}（{dec['owner']}）— {dec['reason']}")
    if dec["missing_info"]:
        print(f"     还需客户补：{dec['missing_info']}")


def cmd_list(args) -> int:
    conn = _conn(args)
    ts = store.list_tickets(conn, status=args.status, limit=args.limit)
    if not ts:
        print("没有工单。")
        return 0
    for t in ts:
        tag = f"{t['category'] or '未分诊'}/{t['priority'] or '-'}"
        print(f"[{t['id']}] {t['status']:<9} {tag:<14} {t['subject'][:40] or '（无标题）'}")
        print(f"     {t['received_at']}  {t['from_addr'] or '未知发件人'}")
    print("  ", store.stats(conn))
    return 0


def cmd_show(args) -> int:
    conn = _conn(args)
    t = store.get_ticket(conn, str(args.id))
    if not t:
        print("没有这张工单。", file=sys.stderr)
        return 1
    print(f"[{t['id']}] {t['subject'] or '（无标题）'}")
    print(f"状态：{t['status']}   来件：{t['received_at']}   发件人：{t['from_addr'] or '未知'}")
    print(f"分诊：{t['category'] or '-'} / {t['priority'] or '-'} / {t['sentiment'] or '-'}")
    print(f"摘要：{t['summary'] or '-'}")
    print("\n原文：")
    print(t["body"])
    if t["draft"]:
        print("\n草稿：")
        print(t["draft"])
    if t["escalate"] is not None:
        print(f"\n升级判断：{'转人工' if t['escalate'] else '可自动回复'}")
        print(f"理由：{t['escalate_reason'] or '-'}")
        if t["missing_info"]:
            print(f"待补信息：{t['missing_info']}")
    return 0


def cmd_set_status(args) -> int:
    conn = _conn(args)
    t = store.get_ticket(conn, str(args.id))
    if not t:
        print("没有这张工单。", file=sys.stderr)
        return 1
    store.set_status(conn, t["id"], args.status_name)
    print(f"[{t['id']}] → {args.status_name}")
    return 0


def cmd_stats(args) -> int:
    conn = _conn(args)
    print("工单：", store.stats(conn))
    print("知识库：", store.kb_stats(conn))
    return 0


def cmd_serve(args) -> int:
    from .web import serve

    conn = _conn(args)
    print(f"应答 Web：http://127.0.0.1:{args.port}  （Ctrl+C 停）")
    serve(conn, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yingda", description="客服工单：分类 → 查知识库 → 起草 → 判断是否转人工。")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--version", action="version", version=f"yingda {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    kb = sub.add_parser("kb", help="知识库管理")
    kb_sub = kb.add_subparsers(dest="kb_cmd", required=True)
    kadd = kb_sub.add_parser("add", help="导入知识库文档")
    kadd.add_argument("paths", nargs="+")
    kadd.set_defaults(func=cmd_kb)
    klist = kb_sub.add_parser("list", help="看知识库")
    klist.set_defaults(func=cmd_kb)
    krm = kb_sub.add_parser("rm", help="按来源删除")
    krm.add_argument("source")
    krm.set_defaults(func=cmd_kb)

    it = sub.add_parser("intake", help="录入一张工单")
    it.add_argument("text", nargs="?", default="", help="粘贴的工单正文")
    it.add_argument("--file", help="从 .eml 或 .txt 读")
    it.add_argument("--subject", default="")
    it.add_argument("--from-addr", default="")
    it.set_defaults(func=cmd_intake)

    pr = sub.add_parser("process", help="跑管线（分类/检索/起草/判断）")
    pr.add_argument("--id", type=int)
    pr.add_argument("--limit", type=int, default=5, help="不指定 id 时最多处理几张")
    pr.set_defaults(func=cmd_process)

    ls = sub.add_parser("list", help="工单列表")
    ls.add_argument("--status", choices=["new", "drafted", "replied", "escalated"])
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="看一张工单的全文和全过程")
    sh.add_argument("id")
    sh.set_defaults(func=cmd_show)

    sd = sub.add_parser("send", help="人工确认后标记为已回复")
    sd.add_argument("id")
    sd.set_defaults(func=cmd_set_status, status_name="replied")

    es = sub.add_parser("escalate", help="手动转人工")
    es.add_argument("id")
    es.set_defaults(func=cmd_set_status, status_name="escalated")

    st = sub.add_parser("stats", help="统计")
    st.set_defaults(func=cmd_stats)

    sv = sub.add_parser("serve", help="起 Web")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8767)
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
