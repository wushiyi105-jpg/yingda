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
<title>应答 · 这单该谁接</title>
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

:root{--maxw:1080px;--bg:#f4f5f3;--card:#ffffff;--ink:#1b2024;--text:#1b2024;--dim:#6b7378;--line:#d7dcda;--accent:#2f5d7c;--muted:#6b7378}
.wrap{max-width:1080px}
body{background:#f4f5f3;color:#1b2024;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
h1{color:#1b2024}
header{max-width:1080px;margin:0 auto}
input,textarea,select{background:#fff;color:#1b2024;border-color:#d7dcda;border-radius:2px}
button:not(.ghost):not(.tab){background:#2f5d7c;color:#fff;border-radius:2px}
button.ghost{background:transparent!important;color:#2f5d7c!important;border:1px solid #d7dcda!important}
h2,h3{color:#2f5d7c}
pre{background:#fafaf6;color:#1b2024;border-color:#d7dcda}
.item,.card{border-color:#d7dcda;background:#ffffff}
.k,.empty,.hint{color:#6b7378}

h1{font-size:clamp(31px,5vw,39px);line-height:1.26}
.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede,.sub{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:16px auto 20px;border:1px solid var(--line);background:var(--line);max-width:var(--maxw)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
pre{white-space:pre-wrap}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

body{background:#f4f5f3;color:#1b2024}
header{display:block!important;max-width:1080px;margin:0 auto;padding:24px 20px 0;background:transparent;border:0}
header h1{color:#1b2024;font-size:38px;line-height:1.24;letter-spacing:-.02em}
header span{display:block;color:#6b7378;font-size:14px;margin-top:6px}
main{max-width:1080px;margin:0 auto;background:#fff;border-left:1px solid #d7dcda;border-right:1px solid #d7dcda;grid-template-columns:360px 1fr;min-height:calc(100vh - 150px)}
aside{background:#f9faf8;border-right:1px solid #d7dcda}
section{background:#fff}
input,textarea,select{background:#fff;color:#1b2024;border-color:#d3d9d7;border-radius:2px}
input:focus,textarea:focus,select:focus{border-color:#2f5d7c;box-shadow:0 0 0 2px #dbe4ea}
button{background:#2f5d7c;color:#fff;border-radius:2px}
button:hover{background:#254b64}
.item,.card{border-color:#d7dcda;background:#fff}
.amber,.warn{border-left:3px solid #d08a2f}
h2{color:#2f5d7c}
.k,.empty{color:#6b7378}


/* mobile-32 */
input[type=text],input[type=number],input[type=email]{background:#fff;color:#1b2024;border-color:#d7dcda}

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #d7dcda;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}

/* mobile-sticky-cta */
.mobile-cta{display:none}
@media(max-width:760px){
  body{padding-bottom:88px}
  .route{grid-template-columns:repeat(3,minmax(0,1fr))!important}
  .route span{padding:8px 8px!important;font-size:11px!important;line-height:1.35!important}
  .route b{font-size:9px!important;margin-bottom:1px!important}
  .mobile-cta{position:fixed;left:12px;right:12px;bottom:12px;z-index:80;display:flex;
    padding:8px;border:1px solid rgba(0,0,0,.08);border-radius:12px;
    background:rgba(255,255,255,.94);backdrop-filter:blur(10px);
    box-shadow:0 10px 28px rgba(16,24,40,.18)}
  .mobile-cta button{width:100%;min-height:52px;margin:0!important;font-size:15px}
}
</style>
</head>
<body>
<header><h1><span class="prod">应答</span>这单，该谁接</h1><span>分类 → 查知识库 → 起草 → 判断要不要转人工</span>
    <p class="lede">给小客服团队的可交接分诊台：按紧迫度、业务线和待办分队列，草稿逐条引用知识库；退款承诺、权限或缺失依据自动转人工。</p>
  </header>
  <div class="route" aria-label="任务步骤"><span><b>01</b>工单入队</span><span><b>02</b>查库起草</span><span><b>03</b>转人工交接</span></div>

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

<script>
(function(){
  var want = "入队";
  function norm(t){ return String(t||'').replace(/\s+/g,''); }
  var all=[].slice.call(document.querySelectorAll('button'));
  var src=null, fallback=null;
  for(var i=0;i<all.length;i++){
    var b=all[i];
    if(b.offsetParent===null||b.disabled) continue;
    if(!fallback) fallback=b;
    if(norm(b.textContent).indexOf(norm(want))>=0){ src=b; break; }
  }
  if(!src) src=fallback;
  if(!src) return;
  var bar=document.createElement('div'); bar.className='mobile-cta';
  var btn=src.cloneNode(true); btn.removeAttribute('id'); btn.type='button';
  btn.addEventListener('click',function(e){e.preventDefault(); src.click();});
  bar.appendChild(btn); document.body.appendChild(bar);
})();
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
