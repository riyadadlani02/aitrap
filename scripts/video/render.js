const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const FPS = 30;
const OUT = path.join(__dirname, 'frames');

(async () => {
  fs.rmSync(OUT, {recursive: true, force: true});
  fs.mkdirSync(OUT, {recursive: true});

  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--force-device-scale-factor=2', '--hide-scrollbars', '--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({width: 1280, height: 720, deviceScaleFactor: 2});
  await page.goto('http://127.0.0.1:8912/scene.html', {waitUntil: 'networkidle0'});
  await page.evaluate(() => window.ready);
  await page.evaluate(() => document.fonts.ready);

  const duration = await page.evaluate(() => window.DURATION);
  const total = Math.round(duration * FPS);
  console.log(`rendering ${total} frames (${duration}s @ ${FPS}fps) at 2560x1440`);

  for (let i = 0; i < total; i++) {
    await page.evaluate(t => window.seek(t), i / FPS);
    await page.screenshot({path: path.join(OUT, String(i).padStart(5, '0') + '.png')});
    if (i % 150 === 0) console.log(`  ${i}/${total}`);
  }
  await browser.close();
  console.log('done');
})();
