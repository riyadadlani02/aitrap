"""Build docs/live/ — the console driven by a real aitrap running in the visitor's browser.

    python scripts/build_live.py

Pyodide is CPython 3.13 compiled to WebAssembly, and sys.monitoring came with it, so the
engine that runs on your laptop runs unmodified in a browser tab. This copies the real
package (no fork, no trimmed build) next to the page and swaps the console's HTTP calls
for direct calls into that engine. Nothing is recorded: every value on the page was
captured microseconds earlier, in the tab.
"""
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "aitrap" / "ui.html"
OUT = ROOT / "docs" / "live"
PKG = OUT / "pkg"

PY_FILES = ["__init__.py", "engine.py", "render.py", "trapsets.py"]
TRAPSETS = ["langchain.json", "livekit.json", "openai_agents.json", "pydantic_ai.json"]

NOTE = """
<div id="live-bar">
  <div class="lb-row">
    <span id="boot" class="boot">starting a real Python 3.13 in this tab…</span>
    <span id="ready" hidden>Live. This console is reading a Python process running
      <em>in your browser</em> — the same engine, unmodified. <a href="../">What this is</a></span>
  </div>
  <div class="lb-row lb-arm" hidden id="controls">
    <label>aitrap trap
      <input id="sym" value="backend.PromoCouponEngine.evaluate_promo" spellcheck="false"></label>
    <label>--when
      <input id="when" placeholder="base_amount &lt; coupon['min_spend']" spellcheck="false"></label>
    <button id="arm">Arm</button>
    <span id="armed-msg"></span>
  </div>
  <div class="lb-row lb-chips" hidden id="chips">
    <span>quick arm</span>
    <button data-sym="backend.CartViewModel.on_apply_tapped">on_apply_tapped</button>
    <button data-sym="backend.TierDiscountService.compute_discount">compute_discount</button>
    <button data-sym="backend.PromoCouponEngine.evaluate_promo">evaluate_promo</button>
    <button data-sym="backend.ShippingRateProvider.calculate_shipping">calculate_shipping</button>
  </div>
  <div class="lb-row lb-run" hidden id="runbar">
    <button id="run" class="go">Apply TECH15 &#9654;</button>
    <label class="chk"><input type="checkbox" id="express" checked> express delivery</label>
    <label class="chk"><input type="checkbox" id="fixed"> apply the fix</label>
    <span id="result"></span>
  </div>
</div>
<style>
  #live-bar{background:#1d2432;border-bottom:1px solid #28313f;color:#79839a;
    font:400 12.5px/1.5 var(--sans);padding:4px 20px 10px}
  .lb-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:6px 0}
  #live-bar [hidden]{display:none!important}
  #live-bar a{color:#7fd1c1;text-decoration:none;border-bottom:1px solid #3a4759}
  #live-bar em{font-style:normal;color:#d7dde8}
  .boot{color:#e0a33e}
  #live-bar label{display:flex;align-items:center;gap:7px;color:#4d5768;font:400 12px var(--mono)}
  #live-bar input[type=text],#live-bar input:not([type]){background:#12161f;color:#d7dde8;
    border:1px solid #28313f;border-radius:3px;padding:6px 9px;font:400 12.5px var(--mono);
    min-width:340px}
  #when{min-width:230px!important}
  #live-bar button{background:#232c3c;color:#d7dde8;border:1px solid #34405280;border-radius:3px;
    padding:6px 12px;font:400 12.5px var(--sans);cursor:pointer}
  #live-bar button:hover{border-color:#4d5768}
  #live-bar button.go{background:#7fd1c1;color:#0e1219;border-color:#7fd1c1;font-weight:600}
  #live-bar button.go:hover{background:#96ded0}
  .lb-chips span{color:#4d5768;font:400 11.5px var(--mono)}
  .lb-chips button{font-family:var(--mono);font-size:11.5px;padding:4px 9px}
  .chk{color:#79839a!important;font-family:var(--sans)!important}
  #armed-msg,#result{font:400 12.5px var(--mono)}
  #armed-msg.err,#result.err{color:#e0656f}
  #armed-msg.ok{color:#3fb8a0}
  #result b{color:#d7dde8;font-weight:500}
</style>
"""

SHIM = """
<script src="https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js"></script>
<script>
// The console's transport, pointed at an aitrap engine in this tab instead of one over HTTP.
// Same endpoints, same shapes — the page cannot tell the difference, which is the point.
const AITRAP_LIVE = (async () => {
  const py = await loadPyodide();
  py.FS.mkdirTree('/lib/aitrap/trapsets');
  const put = async (path, url) => py.FS.writeFile(path, await (await fetch(url)).text());
  await Promise.all([
    ...PKG_FILES.map(f => put('/lib/aitrap/' + f, 'pkg/aitrap/' + f)),
    ...PKG_TRAPSETS.map(f => put('/lib/aitrap/trapsets/' + f, 'pkg/aitrap/trapsets/' + f)),
    put('/lib/backend.py', 'pkg/backend.py'),
  ]);
  py.runPython(BOOT);
  const call = name => py.globals.get(name);
  return {
    arm: (sym, when) => JSON.parse(call('arm')(sym, when || null)),
    traps: () => JSON.parse(call('traps')()),
    poll: (c, l) => JSON.parse(call('poll')(c, l)),
    inspect: oid => JSON.parse(call('inspect')(oid)),
    clear: () => JSON.parse(call('clear')()),
    disarm: id => JSON.parse(call('disarm')(id)),
    checkout: (coupon, express, fixed) => JSON.parse(call('checkout')(coupon, express, fixed)),
    version: py.runPython('import sys; sys.version.split()[0]'),
  };
})();

const real = window.fetch;
// Only the console's own endpoints wait on the engine. Everything else — pyodide's wasm,
// the package files it is still loading — goes straight through, or boot deadlocks on itself.
window.fetch = (input, init) => {
  const url = new URL(input, location.href), q = url.searchParams;
  const p = url.pathname, m = (init && init.method) || 'GET';
  const mine = ['/poll', '/traps', '/inspect'].some(e => p.endsWith(e))
    || (p.endsWith('/events') && m === 'DELETE') || (p.includes('/trap/') && m === 'DELETE');
  if (!mine) return real(input, init);
  const json = body => new Response(JSON.stringify(body),
    {headers: {'Content-Type': 'application/json'}});
  return AITRAP_LIVE.then(api => {
    if (p.endsWith('/poll')) return json(api.poll(+(q.get('cursor') || 0), +(q.get('limit') || 100)));
    if (p.endsWith('/traps')) return json(api.traps());
    if (p.endsWith('/inspect')) return json(api.inspect(+q.get('objectId')));
    if (p.endsWith('/events')) return json(api.clear());
    return json(api.disarm(+p.split('/').pop()));
  });
};

// controls
(async () => {
  const $$ = id => document.getElementById(id);
  const api = await AITRAP_LIVE;
  $$('boot').hidden = true;
  $$('ready').hidden = false;
  $$('ready').innerHTML = $$('ready').innerHTML.replace('Python 3.13',
    'Python ' + api.version);
  for (const id of ['controls', 'chips', 'runbar']) $$(id).hidden = false;

  const armMsg = $$('armed-msg');
  const doArm = (sym, when) => {
    const r = api.arm(sym, when);
    armMsg.className = r.error ? 'err' : 'ok';
    armMsg.textContent = r.error ? r.error
      : `armed #${r.armed.trapId} on ${r.armed.symbol}${r.armed.when ? ' when ' + r.armed.when : ''}`;
  };
  $$('arm').onclick = () => doArm($$('sym').value.trim(), $$('when').value.trim());
  for (const b of document.querySelectorAll('.lb-chips button'))
    b.onclick = () => { $$('sym').value = b.dataset.sym; doArm(b.dataset.sym, ''); };

  $$('run').onclick = () => {
    const out = api.checkout('TECH15', $$('express').checked, $$('fixed').checked);
    const res = $$('result');
    res.className = out.promoError ? 'err' : '';
    res.innerHTML = out.promoError
      ? `total <b>$${out.total.toFixed(2)}</b> — ${out.promoError}`
      : `total <b>$${out.total.toFixed(2)}</b> — coupon applied, −$${out.promoDiscount.toFixed(2)}`;
  };
  // arm the frame the story turns on, so the first click already shows something
  doArm('backend.PromoCouponEngine.evaluate_promo', '');
})();
</script>
"""

BOOT = '''
import json, sys
sys.path.insert(0, "/lib")
import backend
from aitrap import render
from aitrap.engine import Engine

ENGINE = Engine()


def arm(symbol, when=None):
    try:
        trap = ENGINE.arm(symbol, events=("call", "return"), when=when or None)
        return json.dumps({"armed": trap.info()})
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def traps():
    return json.dumps({"traps": [t.info() for t in ENGINE.traps.values()]})


def poll(cursor, limit):
    return json.dumps(ENGINE.buffer.poll(int(cursor), int(limit)))


def inspect(object_id):
    return json.dumps(render.expand(int(object_id)))


def clear():
    ENGINE.buffer.clear()
    return json.dumps({"cleared": True})


def disarm(trap_id):
    return json.dumps({"disarmed": ENGINE.disarm(int(trap_id))})


def checkout(coupon, express, fixed):
    # FIXED is read inside calculate_order, so the same armed traps keep firing across the
    # toggle — which is the whole trick: re-read the fix with the trap that found the bug.
    backend.FIXED = bool(fixed)
    return json.dumps(backend.VIEW_MODEL.on_apply_tapped(coupon, bool(express)))
'''


def main():
    PKG.mkdir(parents=True, exist_ok=True)
    (PKG / "aitrap" / "trapsets").mkdir(parents=True, exist_ok=True)
    for name in PY_FILES:
        shutil.copy(ROOT / "aitrap" / name, PKG / "aitrap" / name)
    for name in TRAPSETS:
        shutil.copy(ROOT / "aitrap" / "trapsets" / name, PKG / "aitrap" / "trapsets" / name)
    shutil.copy(ROOT / "examples" / "checkout_app" / "backend.py", PKG / "backend.py")

    html = UI.read_text()
    marker = "<script>\nconst WINDOW_MS"
    assert marker in html, "console layout changed; update the injection point"
    html = html.replace("<title>aitrap console</title>",
                        "<title>aitrap console — live in your browser</title>")
    html = html.replace("<header>", NOTE.strip() + "\n\n<header>", 1)
    consts = ("<script>\n"
              f"const PKG_FILES = {json.dumps(PY_FILES)};\n"
              f"const PKG_TRAPSETS = {json.dumps(TRAPSETS)};\n"
              f"const BOOT = {json.dumps(BOOT)};\n</script>\n")
    html = html.replace(marker, consts + SHIM.strip() + "\n" + marker)
    (OUT / "index.html").write_text(html)
    print(f"wrote {(OUT / 'index.html').relative_to(ROOT)} ({len(html):,} bytes) "
          f"+ {len(PY_FILES) + len(TRAPSETS) + 1} package files")


if __name__ == "__main__":
    main()
