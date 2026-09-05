"""Build docs/demo/index.html from the real console plus a recorded timeline.

The console (aitrap/ui.html) stays the single source of truth; this only injects a
transport that replays a recorded session instead of talking to a live process.

    python scripts/build_site.py
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "aitrap" / "ui.html"
OUT = ROOT / "docs" / "demo" / "index.html"

NOTE = """
<div id="replay-note">
  <span>Recorded session, replaying in your browser. Nothing is running here &mdash; point the
    real console at your own process to see live values. <a href="../">What this is</a></span>
  <label>agent
    <select id="ds" onchange="location.search = '?ds=' + this.value"></select>
  </label>
</div>
<div id="replay-what"></div>
<style>
  #replay-note{display:flex;align-items:center;gap:18px;flex-wrap:wrap;
    padding:9px 20px;background:#1d2432;border-bottom:1px solid #28313f;
    color:#79839a;font:400 12.5px/1.5 var(--sans)}
  #replay-note a{color:#7fd1c1;text-decoration:none;border-bottom:1px solid #3a4759}
  #replay-note a:hover{border-bottom-color:#7fd1c1}
  #replay-note label{margin-left:auto;display:flex;align-items:center;gap:8px;color:#4d5768}
  #replay-note select{background:#12161f;color:#d7dde8;border:1px solid #28313f;border-radius:3px;
    padding:5px 8px;font:400 12.5px/1 var(--sans)}
  #replay-what{padding:8px 20px;background:#161c27;border-bottom:1px solid #28313f;
    color:#79839a;font:400 12.5px/1.5 var(--mono)}
  #replay-what b{color:#d7dde8;font-weight:500}
</style>
"""

SHIM = """
<script>
// Replay transport: same shapes the real server returns, fed from a recorded run.
(async function(){
  const SETS = {
    toy:                ['toy agent (plain Python)', 'timeline.json',
                         'examples/toy_agent.py &mdash; four functions trapped by dotted name, no framework'],
    langchain:          ['LangChain + LangGraph &mdash; sync', 'langchain.json',
                         'examples/langchain_agent.py under <b>--trapset langchain</b> &mdash; 9 armed, '
                         + '5 fired: invoke, generate, BaseTool.run, Pregel.invoke, LastValue.update'],
    langchain_async:    ['LangChain + LangGraph &mdash; async', 'langchain_async.json',
                         'examples/langchain_async_agent.py, same trapset &mdash; the other 4 fire here: '
                         + 'ainvoke, agenerate, BaseTool.arun, Pregel.ainvoke. Sync + async = 9/9'],
    openai_agents:      ['OpenAI Agents SDK &mdash; async', 'openai_agents.json',
                         'examples/openai_agents_agent.py under <b>--trapset openai_agents</b> &mdash; '
                         + '6 of 6 fired, including the handoff to a second agent'],
    openai_agents_sync: ['OpenAI Agents SDK &mdash; run_sync', 'openai_agents_sync.json',
                         'the same agent through <b>Runner.run_sync</b> &mdash; 5 of 6: '
                         + 'Runner.run never fires, run_sync goes straight to AgentRunner.run'],
    pydantic_ai:        ['Pydantic AI &mdash; async', 'pydantic_ai.json',
                         'examples/pydantic_ai_agent.py under <b>--trapset pydantic_ai</b> &mdash; 4 of 4 fired'],
    pydantic_ai_sync:   ['Pydantic AI &mdash; run_sync', 'pydantic_ai_sync.json',
                         'the same agent through <b>Agent.run_sync</b> &mdash; the same 4 of 4: '
                         + 'run_sync funnels through AbstractAgent.run'],
  };
  const pick = new URLSearchParams(location.search).get('ds');
  const key = SETS[pick] ? pick : 'toy';
  const sel = document.getElementById('ds');
  sel.innerHTML = Object.entries(SETS).map(([k, v]) =>
    `<option value="${k}"${k === key ? ' selected' : ''}>${v[0]}</option>`).join('');
  document.getElementById('replay-what').innerHTML = SETS[key][2];

  const data = await fetch(SETS[key][1]).then(r => r.json());
  const src = data.events, objects = data.objects;
  const T0 = src[0].ts, SPAN = (src[src.length-1].ts - T0) + 2.5;
  const started = Date.now() / 1000;
  const symbols = [...new Set(src.map(e => e.symbol))];
  let out = [], idx = 0, loop = 0, seq = 0, base = 0;

  function release(){
    const t = Date.now() / 1000 - started;
    for (let guard = 0; guard < 500; guard++){
      if (idx >= src.length){ idx = 0; loop++; }
      const due = loop * SPAN + (src[idx].ts - T0);
      if (due > t) return;
      out.push({...src[idx], ts: started + due, seq: ++seq});
      idx++;
      if (out.length > 400) out.shift();
    }
  }

  const json = body => Promise.resolve(new Response(JSON.stringify(body),
    {headers: {'Content-Type': 'application/json'}}));

  const real = window.fetch;
  window.fetch = (input, init) => {
    const url = new URL(input, location.href);
    const q = url.searchParams;
    if (url.pathname.endsWith('.json')) return real(input, init);

    if (url.pathname.endsWith('/poll')){
      release();
      const cursor = +(q.get('cursor') || 0), limit = +(q.get('limit') || 100);
      const events = out.filter(e => e.seq > cursor && e.seq > base).slice(0, limit);
      const nextCursor = events.length ? events[events.length - 1].seq : cursor;
      return json({events, nextCursor, hasMore: out.length && out[out.length-1].seq > nextCursor,
                   dropped: 0});
    }
    if (url.pathname.endsWith('/traps')){
      release();
      return json({traps: symbols.map((s, i) => ({
        trapId: i + 1, symbol: s, events: ['call','return'], when: null, capture: null,
        hits: out.filter(e => e.symbol === s && e.seq > base).length, disarmed: null}))});
    }
    if (url.pathname.endsWith('/inspect')){
      const r = objects[q.get('objectId')];
      return json(r || {error: `objectId ${q.get('objectId')} is gone: collected, or older `
        + `than the last 256 captured objects`});
    }
    if (url.pathname.endsWith('/events')){ base = seq; return json({cleared: true}); }
    return real(input, init);
  };
})();
</script>
"""


def main():
    html = UI.read_text()
    marker = "<script>\nconst WINDOW_MS"
    assert marker in html, "console layout changed; update the injection point"
    html = html.replace("<title>aitrap console</title>",
                        "<title>aitrap console — live demo</title>")
    html = html.replace("<header>", NOTE.strip() + "\n\n<header>", 1)
    html = html.replace(marker, SHIM.strip() + "\n" + marker)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
