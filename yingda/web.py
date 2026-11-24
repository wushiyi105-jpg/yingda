"""Web 收件箱：左边工单列表，右边一张工单的全过程。

"跑管线"是同步的（分类、检索、起草、判断四次往返，十几秒）。
单用户的东西，不值得为它引入队列。
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import intake, pipeline, store
from .llm import LLMError

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>应答 · 客服工单</title>
<style>
  :root { --ink:#1b1f24; --muted:#6b7280; --line:#e6e8eb; --bg:#f6f7f9; --accent:#275d8a; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  header { background:#fff; border-bottom:1px solid var(--line); padding:15px 26px;
           display:flex; gap:12px; align-items:baseline; }
  header h1 { margin:0; font-size:19px; letter-spacing:1px; }
  header span { color:var(--muted); font-size:12px; }
  main { display:grid; grid-template-columns:360px 1fr; min-height:calc(100vh - 55px); }
  aside { background:#fff; border-right:1px solid var(--line); padding:14px; overflow:auto; }
  .filters { display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap; }
  .filters button { font-size:12px; padding:5px 10px; }
  button { font:inherit; font-size:13px; border:0; border-radius:7px; padding:7px 12px;
           background:var(--accent); color:#fff; cursor:pointer; }
  button.ghost { background:#eaf0f5; color:var(--accent); }
  button:disabled { opacity:.45; cursor:default; }
  .t { border:1px solid var(--line); border-radius:9px; padding:9px 11px; margin-bottom:7px; cursor:pointer; }
  .t:hover { background:#f4f7fa; }
  .t.on { border-color:#9dbcd6; background:#f2f7fb; }
  .t .subj { font-size:13px; font-weight:600; }
  .t .meta { color:var(--muted); font-size:11px; margin-top:3px; }
  .badge { display:inline-block; font-size:11px; padding:1px 6px; border-radius:99px; background:#eceef0; color:#555; margin-right:4px; }
  .badge.new { background:#fff2dd; color:#9a5b00; }
  .badge.drafted { background:#e7f3ec; color:#1f6b43; }
  .badge.escalated { background:#fdeaea; color:#a12b2b; }
  .badge.replied { background:#eef0f2; color:#555; }
  section { padding:18px 24px; overflow:auto; }
  .empty { color:var(--muted); font-size:14px; padding:40px 0; }
  h3 { font-size:14px; margin:18px 0 8px; }
  .box { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; font-size:14px; line-height:1.8; white-space:pre-wrap; }
  .row { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }
  .kv { font-size:13px; color:#374151; line-height:1.9; }
  .kv b { color:var(--ink); }
  .kb { background:#f8fafb; border-left:3px solid #9dbcd6; padding:8px 12px; margin-bottom:6px; font-size:13px; }
  textarea { width:100%; font:inherit; font-size:13px; padding:8px; border:1px solid var(--line); border-radius:8px; }
  #hint { color:var(--muted); font-size:12px; }
</style>
</head>
<body>
<header><h1>应答</h1><span>分类 → 查知识库 → 起草 → 判断要不要转人工</span></header>
<main>
<aside>
  <div class="filters">
    <button class="ghost" onclick="setFilter('')">全部</button>
    <button class="ghost" onclick="setFilter('new')">待处理</button>
    <button class="ghost" onclick="setFilter('drafted')">有草稿</button>
    <button class="ghost" onclick="setFilter('escalated')">已转人工</button>
  </div>
  <div id="list"></div>
  <div style="border-top:1px solid var(--line); margin-top:12px; padding-top:10px">
    <div style="font-size:12px;color:#6b7280;margin-bottom:6px">录入一张工单</div>
    <textarea id="body" rows="4" placeholder="把客户的邮件正文贴在这里…"></textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <input id="from" placeholder="发件人" style="flex:1;padding:6px;border:1px solid #e6e8eb;border-radius:7px;font-size:12px">
      <button onclick="intake()">入队</button>
    </div>
  </div>
</aside>
<section id="detail"><div class="empty">左边选一张工单。</div></section>
</main>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
let filter = '', current = null, cache = [];

async function api(path, body) {
  const r = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

async function loadList() {
  const j = await api('/api/tickets' + (filter ? '?status=' + filter : ''));
  cache = j.tickets;
  $('list').innerHTML = j.tickets.length ? j.tickets.map(t => `
    <div class="t ${current === t.id ? 'on' : ''}" onclick="openTicket(${t.id})">
      <div class="subj">${esc(t.subject || '（无标题）')}</div>
      <div class="meta">
        <span class="badge ${t.status}">${t.status}</span>
        ${t.category ? esc(t.category) + ' / ' + esc(t.priority) : '未分诊'}
        · #${t.id}
      </div>
      <div class="meta">${esc(t.received_at)} ${t.from_addr ? '· ' + esc(t.from_addr) : ''}</div>
    </div>`).join('') : '<div class="empty">没有工单。</div>';
  $('stats') && ($('stats').textContent = `共 ${j.stats.total} · 待处理 ${j.stats.new} · 有草稿 ${j.stats.drafted} · 转人工 ${j.stats.escalated}`);
}

function setFilter(f) { filter = f; loadList(); }

async function openTicket(id) {
  current = id;
  const t = await api('/api/ticket?id=' + id);
  render(t.ticket);
  loadList();
}

function render(t) {
  const dec = t.escalate === null || t.escalate === undefined ? null : !!t.escalate;
  $('detail').innerHTML = `
    <h3 style="margin-top:0">${esc(t.subject || '（无标题）')} <span class="badge ${t.status}">${t.status}</span></h3>
    <div class="kv">
      <b>发件人</b>：${esc(t.from_addr || '未知')}　<b>来件</b>：${esc(t.received_at)}<br>
      <b>分诊</b>：${esc(t.category || '-')} / ${esc(t.priority || '-')} / 情绪 ${esc(t.sentiment || '-')}<br>
      <b>一句话</b>：${esc(t.summary || '-')}
    </div>
    <div class="row">
      ${t.status === 'new' ? `<button onclick="run(${t.id}, this)">跑管线</button>` : ''}
      ${t.status === 'drafted' ? `<button onclick="setStatus(${t.id}, 'replied')">标为已回复</button>
                                  <button class="ghost" onclick="setStatus(${t.id}, 'escalated')">转人工</button>` : ''}
      ${t.status === 'escalated' ? `<button class="ghost" onclick="setStatus(${t.id}, 'replied')">人工已处理</button>` : ''}
      <span id="hint"></span>
    </div>
    <h3>客户原文</h3>
    <div class="box">${esc(t.body)}</div>
    ${t.draft ? `<h3>回复草稿</h3><div class="box">${esc(t.draft)}</div>` : ''}
    ${dec !== null ? `<h3>升级判断：${dec ? '转人工' : '可直接回复'}</h3>
      <div class="box">${esc(t.escalate_reason || '-')}${t.missing_info ? '\\n\\n需要客户补充：' + esc(t.missing_info) : ''}</div>` : ''}
    ${t.kb && t.kb.length ? '<h3>用到的知识库</h3>' + t.kb.map((k, i) =>
      `<div class="kb"><b>[${i + 1}] ${esc(k.title)}</b> · 相似度 ${k.score}<br>${esc(k.text.slice(0, 180))}…</div>`).join('') : ''}
  `;
}

async function run(id, btn) {
  btn.disabled = true; btn.textContent = '跑管线…';
  $('hint').textContent = '分类 → 检索 → 起草 → 判断，大概十几秒';
  try {
    const r = await api('/api/process', {id});
    await openTicket(id);
    alert('处理完：' + (r.status === 'escalated' ? '转人工' : '有草稿待发') + '\\n' + r.decision.reason);
  } catch (e) { alert('失败：' + e.message); btn.disabled = false; btn.textContent = '跑管线'; }
}

async function setStatus(id, status) {
  await api('/api/status', {id, status});
  await openTicket(id);
}

async function intake() {
  const body = $('body').value.trim();
  if (!body) return;
  try {
    const r = await api('/api/intake', {body, from: $('from').value.trim()});
    $('body').value = ''; $('from').value = '';
    await loadList();
    await openTicket(r.id);
  } catch (e) { alert('失败：' + e.message); }
}

loadList();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    conn = None
    lock = threading.Lock()
    server_version = "yingda/0.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if parsed.path == "/api/tickets":
            qs = urllib.parse.parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            with self.lock:
                ts = store.list_tickets(self.conn, status=status)
                st = store.stats(self.conn)
            return self._json({"tickets": ts, "stats": st})
        if parsed.path == "/api/ticket":
            qs = urllib.parse.parse_qs(parsed.query)
            tid = int(qs.get("id", [0])[0] or 0)
            with self.lock:
                t = store.get_ticket(self.conn, str(tid))
                if not t:
                    return self._json({"error": "没有这张工单"}, status=404)
                hits = pipeline.search_kb(self.conn, f"{t.get('subject','')} {t['body']}") if t.get("summary") else []
                t["kb"] = hits
            return self._json({"ticket": t})
        return self._json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._read_json()
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)

        if parsed.path == "/api/intake":
            text = (body.get("body") or "").strip()
            if not text:
                return self._json({"error": "正文是空的"}, status=400)
            t = intake.from_pasted(text, from_addr=(body.get("from") or "").strip())
            with self.lock:
                tid = store.add_ticket(self.conn, t["body"], t["subject"], t["from_addr"], t["channel"])
            return self._json({"id": tid})

        if parsed.path == "/api/process":
            tid = int(body.get("id") or 0)
            with self.lock:
                t = store.get_ticket(self.conn, str(tid))
            if not t:
                return self._json({"error": "没有这张工单"}, status=404)
            try:
                with self.lock:
                    r = pipeline.process(self.conn, t)
            except LLMError as e:
                return self._json({"error": f"模型调用失败：{e}"}, status=502)
            return self._json({"id": tid, "status": r["status"], "decision": r["decision"], "triage": r["triage"]})

        if parsed.path == "/api/status":
            tid = int(body.get("id") or 0)
            status = str(body.get("status") or "")
            if status not in {"new", "drafted", "replied", "escalated"}:
                return self._json({"error": "状态不对"}, status=400)
            with self.lock:
                if not store.get_ticket(self.conn, str(tid)):
                    return self._json({"error": "没有这张工单"}, status=404)
                store.set_status(self.conn, tid, status)
            return self._json({"ok": True})

        return self._json({"error": "not found"}, status=404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4 * 1024 * 1024:
            raise ValueError("请求太大")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}") from e

    def _json(self, obj, status: int = 200):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, payload: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(conn, host: str = "127.0.0.1", port: int = 8767) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"conn": conn, "lock": threading.Lock()})
    return ThreadingHTTPServer((host, port), handler)


def serve(conn, host: str = "127.0.0.1", port: int = 8767):
    httpd = make_server(conn, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停了。")
    finally:
        httpd.server_close()
