# Demo video pipeline

`../../docs/aitrap-demo.mp4` is rendered from these, not edited by hand. Regenerate it when the
verified counts or framework versions in `scene.html` go stale.

`scene.html` is a deterministic player: `window.seek(t)` renders the exact state at time `t`, so
every frame is reproducible rather than dependent on animation timing. `checkout.json` is the same
recording the phone demo uses — real captures from `examples/checkout_app/backend.py` run under
aitrap, so both the phone screen and the frames beside it are genuine, not mock-ups.

```bash
npm i puppeteer-core
python3 -m http.server 8912 &          # scene.html fetches frames.json, so file:// won't do
node render.js                          # 3090 PNGs at 2560x1440
ffmpeg -framerate 30 -i frames/%05d.png -vf scale=1920:1080:flags=lanczos \
       -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart \
       ../../docs/aitrap-demo.mp4
```

`render.js` points at `/Applications/Google Chrome.app`; change `CHROME` elsewhere.
