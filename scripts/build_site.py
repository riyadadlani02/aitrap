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
<div id="replay-note">Recorded session, replaying in your browser. Nothing is running here —
  point the real console at your own process to see live values.
  <a href="../">What this is</a></div>
<style>
  #replay-note{padding:9px 20px;background:#1d2432;border-bottom:1px solid #28313f;
    color:#79839a;font:400 12.5px/1.5 var(--sans)}
  #replay-note a{color:#7fd1c1;text-decoration:none;border-bottom:1px solid #3a4759}
  #replay-note a:hover{border-bottom-color:#7fd1c1}
</style>
"""

SHIM = """
<script>
// Replay transport: same shapes the real server returns, fed from a recorded run.
(async function(){
  const data = await fetch('timeline.json').then(r => r.json());
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
    if (url.pathname.endsWith('timeline.json')) return real(input, init);

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
