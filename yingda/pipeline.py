"""工单处理管线：分诊 → 检索 → 起草 → 决定是否升级。

三次独立的模型调用，各管一件事：
  分诊管"这是什么问题、多急"，起草管"怎么回"，决定管"该不该我自己回"。
第一版我把分诊和起草塞进同一次调用，结果模型一边分类一边写回复，
分类被措辞带跑（明明是投诉，判成了"产品使用"）。拆开之后各自都稳了。

另一个刻意的设计：模型调用失败就默认转人工，绝不默认"已回复"。
"""

from __future__ import annotations

from . import llm, store
from .bm25 import BM25Index

CATEGORIES = ["退款退货", "物流", "账号", "产品使用", "发票", "投诉", "其他"]
PRIORITIES = ["P0", "P1", "P2", "P3"]

TRIAGE_SYSTEM = """你是客服工单分诊员。读一条工单，判断它是什么问题、有多急、客户情绪如何。

优先级定义：
- P0：资金已经损失、账号被盗、涉及法律或监管、客户扬言曝光/起诉
- P1：明确要求退款、赔偿、取消订单，或服务已中断
- P2：功能故障影响正常使用，但还能等
- P3：一般咨询、建议、发票等事务

只输出 JSON：
{"category": "退款退货|物流|账号|产品使用|发票|投诉|其他",
 "priority": "P0|P1|P2|P3",
 "sentiment": "angry|worried|neutral|friendly",
 "summary": "客户到底要什么，不超过 40 字",
 "key_facts": "从工单里摘出的关键事实（订单号、金额、时间），没有就空字符串"}"""

DRAFT_SYSTEM = """你是客服，要在不惹麻烦的前提下把问题回清楚。

规则：
1. 只能使用【知识库片段】里写明的政策。时限、金额、补偿比例一律不许自己编。
2. 知识库没覆盖到的点，不要猜，写"这一点我需要核实后回复你"。
3. 先回应情绪，再给事实，最后给下一步动作。
4. 不用 Markdown，不用表情符号，不超过 200 字，称呼用"你"，结尾署名"青梧客服"。
5. 不要在回复里出现"知识库""片段""模型"这类内部词。

只输出 JSON：
{"reply": "给客户的回复正文",
 "used_kb": [1, 2],
 "uncovered": "哪些点知识库没覆盖，没有就空字符串"}"""

DECIDE_SYSTEM = """你是客服主管，判断这条工单能不能让 AI 直接回，还是要转人工。

判断草稿有没有越权，只能以【知识库片段】为准：
- 草稿里的时限、金额、比例，如果在片段里能找到（包括同义表述），就算有依据，不要判越权
- 找不到依据，或者草稿把"需要核实"写成了确定结论，才算越权
- 不要因为"提到了具体数字"就转人工，客服本来就要说清时限

必须转人工的情况：
- 涉及退款金额争议、赔偿、法律或监管问题
- 账号安全（被盗、异常登录、实名信息）
- 客户明确要求人工客服
- 知识库完全没有覆盖，而回答会影响客户的决策
- 草稿里出现了知识库没有的政策或承诺（这最危险）
- 情绪已经升级为投诉、威胁曝光

只输出 JSON：
{"escalate": true/false,
 "reason": "转或不转的具体理由，必须提到工单里的证据",
 "missing_info": "还需要客户补充什么信息，没有就空字符串",
 "owner": "退款组|技术组|法务|主管|无需"}"""


def triage(ticket: dict, config: dict | None = None) -> dict:
    user = (
        f"渠道：{ticket.get('channel')}\n"
        f"发件人：{ticket.get('from_addr') or '未知'}\n"
        f"标题：{ticket.get('subject') or '（无）'}\n"
        f"正文：\n{ticket.get('body')}"
    )
    raw = llm.chat(
        [{"role": "system", "content": TRIAGE_SYSTEM}, {"role": "user", "content": user}],
        config=config,
        temperature=0.1,
        max_tokens=600,
    )
    try:
        data = llm.extract_json(raw)
        if not isinstance(data, dict):
            raise llm.LLMError("不是对象")
    except llm.LLMError:
        return {
            "category": "其他", "priority": "P2", "sentiment": "neutral",
            "summary": "分诊失败，需要人工看一眼", "key_facts": "", "error": True,
        }
    category = str(data.get("category") or "其他")
    if category not in CATEGORIES:
        category = "其他"
    priority = str(data.get("priority") or "P2").upper()
    if priority not in PRIORITIES:
        priority = "P2"
    return {
        "category": category,
        "priority": priority,
        "sentiment": str(data.get("sentiment") or "neutral"),
        "summary": str(data.get("summary") or "")[:80],
        "key_facts": str(data.get("key_facts") or ""),
        "error": False,
    }


def search_kb(conn, query: str, top_k: int = 4) -> list[dict]:
    chunks = store.kb_chunks(conn)
    if not chunks:
        return []
    return BM25Index(chunks).search(query, top_k=top_k)


def draft_reply(ticket: dict, triage_result: dict, hits: list[dict], config: dict | None = None) -> dict:
    blocks = [f"[{i}] {h['title']}\n{h['text']}" for i, h in enumerate(hits, 1)]
    kb_text = "\n\n".join(blocks) if blocks else "（知识库里没有检索到相关内容）"
    user = (
        f"【工单】\n标题：{ticket.get('subject') or '（无）'}\n{ticket.get('body')}\n\n"
        f"【分诊结果】类型 {triage_result['category']}，优先级 {triage_result['priority']}，"
        f"情绪 {triage_result['sentiment']}\n\n"
        f"【知识库片段】\n{kb_text}\n\n按要求输出 JSON。"
    )
    raw = llm.chat(
        [{"role": "system", "content": DRAFT_SYSTEM}, {"role": "user", "content": user}],
        config=config,
        temperature=0.3,
        max_tokens=1200,
    )
    try:
        data = llm.extract_json(raw)
        if isinstance(data, dict) and data.get("reply"):
            used = [int(x) for x in (data.get("used_kb") or []) if str(x).isdigit()]
            return {
                "reply": str(data["reply"]).strip(),
                "used_kb": [n for n in used if 1 <= n <= len(hits)],
                "uncovered": str(data.get("uncovered") or ""),
                "error": False,
            }
    except (llm.LLMError, ValueError):
        pass
    # 模型没按格式来：把原文当草稿，标记错误，交给升级判断去处理
    return {"reply": raw.strip(), "used_kb": [], "uncovered": "模型没有按格式输出", "error": True}


def decide(ticket: dict, triage_result: dict, hits: list[dict], draft: dict,
           config: dict | None = None) -> dict:
    # 把知识库片段一起给主管：不给的话它没法判断草稿是不是越权，
    # 只要看到具体时限就一律转人工——第一版就是这么把正常工单全拦下来的。
    kb_text = "\n\n".join(f"[{i}] {h['title']}\n{h['text']}" for i, h in enumerate(hits, 1)) or "（知识库没有命中任何内容）"
    user = (
        f"【工单】\n{ticket.get('body')}\n\n"
        f"【分诊】{triage_result['category']} / {triage_result['priority']} / {triage_result['sentiment']}\n\n"
        f"【知识库片段】\n{kb_text}\n\n"
        f"【草稿】\n{draft['reply']}\n"
        f"草稿自己说没覆盖到的点：{draft.get('uncovered') or '无'}\n\n"
        "按要求输出 JSON。"
    )
    raw = llm.chat(
        [{"role": "system", "content": DECIDE_SYSTEM}, {"role": "user", "content": user}],
        config=config,
        temperature=0.1,
        max_tokens=1200,
    )
    try:
        data = llm.extract_json(raw)
        if not isinstance(data, dict):
            raise llm.LLMError("不是对象")
    except llm.LLMError:
        return {"escalate": True, "reason": "升级判断失败，按保守策略转人工", "missing_info": "", "owner": "主管", "error": True}
    return {
        "escalate": bool(data.get("escalate")),
        "reason": str(data.get("reason") or ""),
        "missing_info": str(data.get("missing_info") or ""),
        "owner": str(data.get("owner") or ("主管" if data.get("escalate") else "无需")),
        "error": False,
    }


def process(conn, ticket: dict, config: dict | None = None) -> dict:
    """跑完整条链路，把每一步写库，返回结果。"""
    t = triage(ticket, config=config)
    store.save_triage(conn, ticket["id"], t)

    query = f"{ticket.get('subject', '')} {ticket.get('body', '')} {t['summary']}"
    hits = search_kb(conn, query)

    d = draft_reply(ticket, t, hits, config=config)
    store.save_draft(conn, ticket["id"], d["reply"])

    decision = decide(ticket, t, hits, d, config=config)
    # 起草失败 / 草稿自称覆盖不了 → 强制转人工，别让不合格的草稿直接发出去
    if d.get("error"):
        decision["escalate"] = True
        decision["reason"] = (decision.get("reason") or "") + "（草稿格式异常，按保守策略转人工）"
    store.save_decision(conn, ticket["id"], decision)
    store.set_status(conn, ticket["id"], "escalated" if decision["escalate"] else "drafted")

    return {
        "ticket_id": ticket["id"],
        "triage": t,
        "kb_hits": hits,
        "draft": d,
        "decision": decision,
        "status": "escalated" if decision["escalate"] else "drafted",
    }
