# Demo video pipeline

`../../docs/aitrap-demo.mp4` is rendered from these, not edited by hand. Regenerate it when the
verified counts or framework versions in `scene.html` go stale.

`scene.html` is a deterministic player: `window.seek(t)` renders the exact state at time `t`, so
every frame is reproducible rather than dependent on animation timing. `checkout.json` is the same
recording the phone demo uses — real captures from `examples/checkout_app/backend.py` run under
aitrap, in both states: broken, and again with `CHECKOUT_FIXED=1` after the repair. `voice.json` is
the voice demo's recording, `examples/voice_agent.py` in both states (`VOICE_FIXED=1`), and drives
the call scenes. `frameworks.json` and `stories.json` are
written by `scripts/record_timeline.py` alongside the site's recordings: the adapter scene's
counts and silent symbols, and the three framework story scenes' frames, transcripts and values,
all come out of those runs in both states. Only the narration is authored. The before and after screens and frames are all genuine, not mock-ups.

```bash
npm i puppeteer-core
python3 -m http.server 8912 &          # scene.html fetches its recordings, so file:// won't do
node render.js                          # 5940 PNGs at 2560x1440
ffmpeg -framerate 30 -i frames/%05d.png -vf scale=1920:1080:flags=lanczos \
       -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart \
       ../../docs/aitrap-demo.mp4
```

`render.js` points at `/Applications/Google Chrome.app`; change `CHROME` elsewhere.
