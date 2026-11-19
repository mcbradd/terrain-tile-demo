// P1.3, P1.5, P1.6 browser check: overdraw view and measurement, slope-class overlay, rise-in on load.
// Usage: node tests/p1_check.mjs <origin> [--overdraw-out <file>] [--shots <dir>]
//   origin         where site/ is served, e.g. http://127.0.0.1:8000 (`uv run tilepipe serve`)
//   --overdraw-out write the overdraw.json the viewer measured, e.g. build/anza_borrego_01/overdraw.json
//   --shots        write 1920 x 1080 screenshots of both views for both profiles into this directory
// Exit 0 pass, 1 fail, 77 no headless browser.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const args = process.argv.slice(2);
const ORIGIN = args[0].replace(/\/$/, '');
const opt = (k) => (args.includes(k) ? args[args.indexOf(k) + 1] : null);
const overdrawOut = opt('--overdraw-out');
const shots = opt('--shots');
const FIRST_FRAME_MS = 10000;

const fails = [];
const check = (ok, what, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${what}${detail ? `: ${detail}` : ''}`);
  if (!ok) fails.push(what);
};

async function launch(chromium) {
  for (const o of [{}, { channel: 'chrome' }, { channel: 'msedge' }]) {
    try {
      return await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...o });
    } catch {
      // try the next browser
    }
  }
  return null;
}

const frames = (page, n) => page.evaluate(async (k) => {
  for (let i = 0; i < k; i++) await new Promise((r) => requestAnimationFrame(r));
}, n);

async function shot(page, name) {
  if (!shots) return;
  await frames(page, 4);
  await page.screenshot({ path: join(shots, `${name}.png`) });
  console.log(`wrote ${join(shots, `${name}.png`)}`);
}

async function run() {
  let chromium;
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    console.log('SKIP: playwright is not installed');
    return 77;
  }
  const browser = await launch(chromium);
  if (!browser) {
    console.log('SKIP: no headless browser available to Playwright');
    return 77;
  }
  if (shots) mkdirSync(shots, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });

  // ---- P1.6 rise-in, first frame, exact transform afterwards ----
  const page = await ctx.newPage();
  page.on('pageerror', (e) => check(false, 'page error', e.message));
  await page.goto(`${ORIGIN}/?tour=0&profile=workstation`);
  const first = await page.evaluate(async () => {
    await window.tilepipe.ready;
    const riseAtReady = window.tilepipe.rise;
    await new Promise((r) => requestAnimationFrame(r));
    return { ms: performance.now(), riseAtReady };
  });
  check(first.ms < FIRST_FRAME_MS, 'interactive first frame under 10 s', `${first.ms.toFixed(0)} ms`);
  check(first.riseAtReady < 1, 'rise-in starts below full height', `${first.riseAtReady}`);
  const rose = await page.evaluate(async () => {
    const v = window.tilepipe;
    const ms = await v.risen;
    const e = v.terrainUniforms.u_tableFromTL.value.elements;
    const S = v.tile.table.scale;
    const V = v.exaggeration;
    return { ms, rise: v.rise, ok: e[5] === V / S && e[13] === -v.tile.height.min * V / S + 0.010 };
  });
  check(rose.ms >= 1200 && rose.ms < 4000, 'rise-in lasts 1.2 s', `${rose.ms.toFixed(0)} ms`);
  check(rose.rise === 1 && rose.ok, 'rise-in ends on the exact table transform');
  const probe = await ctx.newPage();
  await probe.goto(`${ORIGIN}/?probe=1&tour=0&profile=workstation`);
  const pr = await probe.evaluate(async () => { await window.tilepipe.ready; return window.tilepipe.rise; });
  check(pr === 1, 'rise-in is skipped with ?probe=1');
  await probe.close();

  // ---- P1.3 overdraw view: radio, key O, legend, live readback ----
  const st = () => page.evaluate(() => ({ debug: window.tilepipe.debug, slope: window.tilepipe.toggles.slope }));
  const legend = (id) => page.locator(`#${id}`);
  await page.keyboard.press('o');
  await frames(page, 2);
  check((await st()).debug === 'overdraw', 'key O selects the overdraw view');
  check(await legend('legend-overdraw').isVisible()
    && /per pixel/.test(await legend('legend-overdraw').innerText()), 'overdraw legend is on screen');
  await page.waitForFunction(() => window.tilepipe.overdrawLive, null, { timeout: 10000 });
  await page.waitForFunction(() => /Mean \d/.test(document.getElementById('od-mean').textContent), null,
    { timeout: 5000 });
  const live = await page.evaluate(() => window.tilepipe.overdrawLive);
  check(live.covered_px > 0 && live.mean_overdraw >= 1, 'overdraw readback counts fragments', JSON.stringify(live));
  await shot(page, 'workstation_overdraw');
  await page.keyboard.press('o');
  await frames(page, 2);
  check((await st()).debug === 'none' && !(await legend('legend').isVisible()), 'key O turns it off, legend hides');
  await page.check('#dbg-overdraw');
  check((await st()).debug === 'overdraw', 'Debug Overdraw radio');
  await page.check('#dbg-none');

  // ---- P1.5 slope classes: checkbox, key S, legend labeled illustrative ----
  await page.keyboard.press('s');
  await frames(page, 2);
  check((await st()).slope === true && await page.isChecked('#chk-slope'), 'key S turns on slope classes');
  check(await page.evaluate(() => window.tilepipe.terrainUniforms.u_slopeClasses.value) === 1, 'slope uniform is set');
  const sl = await legend('legend-slope').innerText();
  check(await legend('legend-slope').isVisible() && /illustrative/i.test(sl) && /15/.test(sl) && /30/.test(sl),
    'slope legend is on screen and says illustrative', sl.replace(/\n/g, ' | '));
  await shot(page, 'workstation_slope');
  await page.uncheck('#chk-slope');
  check((await st()).slope === false && !(await legend('legend').isVisible()), 'Slope classes checkbox turns it off');

  // ---- the other profile in its default look ----
  const mob = await ctx.newPage();
  await mob.goto(`${ORIGIN}/?tour=0&profile=mobile_ar`);
  await mob.evaluate(async () => { await window.tilepipe.ready; await window.tilepipe.risen; });
  await mob.keyboard.press('o');
  await mob.waitForFunction(() => window.tilepipe.overdrawLive, null, { timeout: 10000 });
  await shot(mob, 'mobile_ar_overdraw');
  await mob.keyboard.press('o');
  await mob.keyboard.press('s');
  check(await mob.evaluate(() => window.tilepipe.toggles.slope && window.tilepipe.look === 'additive'),
    'slope classes in the additive look');
  await shot(mob, 'mobile_ar_slope');
  await mob.close();

  // ---- P1.3 measurement: each profile at the default view, the overdraw half of bench mode ----
  const doc = await page.evaluate(() => window.tilepipe.overdrawRun());
  const okDoc = ['workstation', 'mobile_ar'].every((p) => doc.profiles[p] && doc.profiles[p].mean_overdraw >= 1
    && doc.profiles[p].covered_px > 0) && doc.camera.view === 'default' && doc.canvas.width === 1920;
  check(okDoc, 'overdraw.json per profile at the default view', JSON.stringify(doc.profiles));
  check(await page.evaluate(() => window.tilepipe.groundDiscEnabled && window.tilepipe.profile === 'workstation'),
    'overdraw run restores the view state');
  if (overdrawOut) {
    mkdirSync(dirname(overdrawOut), { recursive: true });
    writeFileSync(overdrawOut, `${JSON.stringify(doc, null, 2)}\n`);
    console.log(`wrote ${overdrawOut}`);
  }
  await browser.close();
  return fails.length ? 1 : 0;
}

process.exit(await run());
