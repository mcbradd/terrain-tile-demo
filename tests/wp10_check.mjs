// WP10 browser check (SPEC 19.4): the G4 probe, every control and key of 13.5, the tour, and bench mode.
// Usage: node tests/wp10_check.mjs <origin> [--bench-out <file>] [--skip-bench]
//   origin       where site/ is served, e.g. http://127.0.0.1:8000 (`uv run tilepipe serve`)
//   --bench-out  write the bench.json the viewer produced, e.g. build/anza_borrego_01/bench.json
// Exit 0 pass, 1 fail, 77 no headless browser.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

const args = process.argv.slice(2);
const ORIGIN = args[0].replace(/\/$/, '');
const benchOut = args.includes('--bench-out') ? args[args.indexOf('--bench-out') + 1] : null;
const SKIP_BENCH = args.includes('--skip-bench');
// The AOI is whatever `tilepipe site` wrote into config.json; the pages below are loaded with no ?aoi= (17.14, D-16).
const AOI = (await (await fetch(`${ORIGIN}/config.json`)).json()).aoi;

const fails = [];
const check = (ok, what, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${what}${detail ? `: ${detail}` : ''}`);
  if (!ok) fails.push(what);
};

async function launch(chromium) {
  for (const opts of [{}, { channel: 'chrome' }, { channel: 'msedge' }]) {
    try {
      return await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...opts });
    } catch {
      // try the next browser
    }
  }
  return null;
}

const frames = (page, n) => page.evaluate(async (k) => {
  for (let i = 0; i < k; i++) await new Promise((r) => requestAnimationFrame(r));
}, n);

// Height at tile-local (x, z) read straight from the .bin file, independent of the viewer's code.
async function binHeight(tile, x, z) {
  const buf = Buffer.from(await (await fetch(`${ORIGIN}/data/${AOI}/${tile.textures[0].file}`)).arrayBuffer());
  const n = tile.textures[0].width;
  const fx = x / tile.cell_m - 0.5;
  const fz = z / tile.cell_m - 0.5;
  const c = Math.floor(fx);
  const r = Math.floor(fz);
  const texel = (rr, cc) => (buf[(rr * n + cc) * 2] * 65280 / 255 + buf[(rr * n + cc) * 2 + 1] * 255 / 255) / 65535;
  const tx = fx - c;
  const tz = fz - r;
  const v = (texel(r, c) * (1 - tx) + texel(r, c + 1) * tx) * (1 - tz)
    + (texel(r + 1, c) * (1 - tx) + texel(r + 1, c + 1) * tx) * tz;
  return tile.height.min + v * (tile.height.max - tile.height.min);
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
  const tile = await (await fetch(`${ORIGIN}/data/${AOI}/tile.json`)).json();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const offOrigin = new Set();
  page.on('request', (r) => { if (!r.url().startsWith(`${ORIGIN}/`) && !r.url().startsWith('data:') && !r.url().startsWith('blob:')) offOrigin.add(r.url()); });
  page.on('pageerror', (e) => check(false, 'page error', e.message));
  const logs = [];
  page.on('console', (m) => logs.push(m.text()));

  // ---- G4 probe ----
  await page.goto(`${ORIGIN}/?probe=1&tour=0&profile=workstation`);
  await page.evaluate(() => window.tilepipe.ready);
  await frames(page, 3);
  const line = logs.find((l) => l.startsWith('PROBE '));
  check(Boolean(line), 'probe line logged');
  const probe = JSON.parse(line.slice(6));
  console.log(`PROBE ${line.slice(6)}`);
  check(probe.easting === tile.origin.E0 + 5120, 'probe easting is E0 + 5120', `${probe.easting}`);
  check(probe.northing === tile.origin.N_top - 5120, 'probe northing is N_top - 5120', `${probe.northing}`);
  const expect = await binHeight(tile, 5120, 5120);
  check(Math.abs(probe.elevation_m - expect) < 1e-6, 'probe elevation equals the height texture', `${probe.elevation_m} vs ${expect}`);
  check(probe.mgrs === tile.mgrs.center, 'probe MGRS equals tile.mgrs.center', `${probe.mgrs}`);

  // ---- cursor march: aim the pointer at the screen position of TL (5120, 5120) ----
  const hit = await page.evaluate(async () => {
    const v = window.tilepipe;
    const THREE_V = v.camera.position.constructor;
    const p = new THREE_V(0, 0, 0);
    p.y = (v.hud.readoutAt(5120, 5120).elevation_m - v.tile.height.min) * v.exaggeration / v.tile.table.scale + 0.010;
    p.project(v.camera);
    const rect = document.getElementById('view').getBoundingClientRect();
    return { x: ((p.x + 1) / 2) * rect.width, y: ((1 - p.y) / 2) * rect.height };
  });
  await page.mouse.move(hit.x, hit.y);
  await frames(page, 4);
  const cur = await page.evaluate(() => window.tilepipe.lastReadout);
  check(cur && Math.hypot(cur.x - 5120, cur.z - 5120) < 200, 'cursor march lands near the aimed point',
    cur ? `${cur.x.toFixed(0)}, ${cur.z.toFixed(0)}` : 'no hit');
  const txt = await page.locator('#cursor').innerText();
  check(/NAVD88/.test(txt) && /MGRS 11SNS/.test(txt) && /Slope/.test(txt), 'cursor panel text', txt.replace(/\n/g, ' | '));

  // ---- every control and key of 13.5 ----
  const st = () => page.evaluate(() => {
    const v = window.tilepipe;
    return { profile: v.profile, look: v.look, exag: v.exaggeration, ...v.toggles, debug: v.debug,
      hidden: document.getElementById('hud').classList.contains('hidden') };
  });
  const key = async (k) => { await page.keyboard.press(k); await frames(page, 2); };
  await key('2');
  await page.waitForFunction(() => window.tilepipe.profile === 'mobile_ar');
  check((await st()).profile === 'mobile_ar', 'key 2 selects mobile_ar');
  await key('1');
  await page.waitForFunction(() => window.tilepipe.profile === 'workstation');
  check((await st()).profile === 'workstation', 'key 1 selects workstation');
  await key('l');
  check((await st()).look === 'additive', 'key L toggles look');
  await key('l');
  await key('e');
  check((await st()).exag === 2, 'key E steps exaggeration', `${(await st()).exag}`);
  await key('e');
  await key('e');
  await key('e');
  check((await st()).exag === 1.5, 'key E cycles back to 1.5');
  await key('c');
  check((await st()).contours === false, 'key C toggles contours');
  await key('g');
  check((await st()).grid === false, 'key G toggles grid');
  await key('w');
  check((await st()).debug === 'wireframe', 'key W toggles wireframe');
  await key('w');
  check((await st()).debug === 'none', 'key W toggles wireframe off');
  await page.evaluate(() => { window.tilepipe.camera.position.set(1, 1, 1); });
  await key('r');
  const home = await page.evaluate(() => window.tilepipe.camera.position.toArray());
  check(Math.abs(home[1] - 1.9 * Math.sin(32 * Math.PI / 180) - 0.05) < 1e-3, 'key R resets the camera');
  await key('h');
  check((await st()).hidden === true, 'key H hides the HUD');
  await key('h');
  check((await st()).hidden === false, 'key H shows the HUD');
  // buttons and checkboxes
  await page.click('#seg-profile button[data-value="mobile_ar"]');
  await page.waitForFunction(() => window.tilepipe.profile === 'mobile_ar');
  await page.click('#seg-profile button[data-value="workstation"]');
  await page.waitForFunction(() => window.tilepipe.profile === 'workstation');
  await page.click('#seg-look button[data-value="additive"]');
  check((await st()).look === 'additive', 'Look control');
  await page.click('#seg-look button[data-value="opaque"]');
  await page.click('#seg-exag button[data-value="3"]');
  check((await st()).exag === 3, 'Exaggeration control');
  await page.click('#seg-exag button[data-value="1.5"]');
  await page.uncheck('#chk-entities');
  check((await st()).entities === false, 'Entities checkbox');
  await page.check('#chk-entities');
  await page.uncheck('#chk-contours');
  check((await st()).contours === false, 'Contours checkbox');
  await page.check('#chk-contours');
  await page.uncheck('#chk-grid');
  await page.check('#chk-grid');
  await page.check('#dbg-wireframe');
  check((await st()).debug === 'wireframe', 'Debug Wireframe');
  await page.check('#dbg-lod');
  check((await st()).debug === 'lod', 'Debug LOD tint');
  await page.check('#dbg-none');
  const budget = await page.locator('#budget').innerText();
  check(/ASSUMED class:/.test(budget) && /No headset performance was measured\./.test(budget) && /budget-forced/.test(budget)
    && /MiB/.test(budget) && /Full report/.test(budget), 'Budget panel text', budget.replace(/\n/g, ' | ').slice(0, 300));
  check(/PASS|WARN|FAIL/.test(await page.locator('#budget .chip').innerText()), 'Budget chip carries its word');
  await page.click('#btn-about');
  const about = await page.locator('#about').innerText();
  check(/Report/.test(about) && /Repository/.test(about) && /Video/.test(about), 'About panel links');
  // collapse below 720 px
  await page.setViewportSize({ width: 600, height: 700 });
  check(!(await page.locator('#view-panel').isVisible()) && await page.locator('#toggles').isVisible(),
    'Budget and View collapse behind buttons under 720 px');
  await page.click('#toggles button:nth-child(2)');
  check(await page.locator('#view-panel').isVisible(), 'View button opens the View panel');
  await page.setViewportSize({ width: 1280, height: 720 });

  // ---- tour: plays, captions, cancel on input, restores profile and look ----
  const tourPage = await ctx.newPage();
  await tourPage.goto(`${ORIGIN}/?profile=workstation`);
  await tourPage.evaluate(() => window.tilepipe.ready);
  const cap = () => tourPage.locator('#caption').innerText().catch(() => '');
  await tourPage.waitForSelector('#caption:not([hidden])', { timeout: 10000 });
  check((await cap()).startsWith('10.24 km of Anza-Borrego'), 'tour caption 1', await cap());
  await tourPage.waitForFunction(() => window.tilepipe.debug === 'both', null, { timeout: 8000 });
  check((await cap()).startsWith('Geometry is chosen'), 'tour caption 2 with LOD tint and wireframe', await cap());
  check(!(await tourPage.locator('#cursor').isVisible()) && await tourPage.locator('#budget').isVisible(),
    'tour hides Cursor and View, keeps Budget');
  await tourPage.waitForFunction(() => window.tilepipe.profile === 'mobile_ar', null, { timeout: 8000 });
  check(/^Mobile AR budget: [\d,]+ triangles, [\d.]+ px of terrain error$/.test(await cap()), 'tour caption 3', await cap());
  await tourPage.waitForFunction(() => window.tilepipe.look === 'additive', null, { timeout: 8000 });
  check((await cap()).startsWith('Preview for see-through displays'), 'tour caption 4', await cap());
  await tourPage.waitForSelector('#caption[hidden]', { state: 'attached', timeout: 10000 });
  await tourPage.waitForFunction(() => window.tilepipe.profile === 'workstation' && window.tilepipe.look === 'opaque');
  check((await tourPage.evaluate(() => window.tilepipe.debug)) === 'none', 'tour ends with the initial profile and look');
  await tourPage.close();

  const cancelPage = await ctx.newPage();
  await cancelPage.goto(`${ORIGIN}/?profile=workstation`);
  await cancelPage.evaluate(() => window.tilepipe.ready);
  await cancelPage.waitForSelector('#caption:not([hidden])', { timeout: 10000 });
  await cancelPage.waitForFunction(() => window.tilepipe.debug === 'both', null, { timeout: 8000 });
  await cancelPage.mouse.move(300, 300);
  await cancelPage.mouse.down();
  await cancelPage.mouse.up();
  await cancelPage.waitForSelector('#caption[hidden]', { state: 'attached', timeout: 5000 });
  const after = await cancelPage.evaluate(() => ({ p: window.tilepipe.profile, l: window.tilepipe.look, d: window.tilepipe.debug,
    touring: document.body.classList.contains('touring') }));
  check(after.p === 'workstation' && after.l === 'opaque' && after.d === 'none' && !after.touring, 'pointer input cancels the tour', JSON.stringify(after));
  await cancelPage.evaluate(() => document.getElementById('btn-tour').click());
  await cancelPage.waitForSelector('#caption:not([hidden])', { timeout: 5000 });
  await cancelPage.keyboard.press('x');
  await cancelPage.waitForSelector('#caption[hidden]', { state: 'attached', timeout: 5000 });
  check(true, 'Play tour starts it and a key cancels it');
  await cancelPage.close();

  // ---- bench ----
  if (!SKIP_BENCH) {
    const benchPage = await ctx.newPage();
    await benchPage.setViewportSize({ width: 640, height: 360 });
    await benchPage.goto(`${ORIGIN}/?bench=1`);
    await benchPage.waitForSelector('body[data-bench="done"]', { timeout: 540000 });
    const bench = await benchPage.evaluate(() => window.tilepipe.benchResult);
    const has = (o, ks) => ks.every((k) => k in o);
    const okShape = has(bench, ['user_agent', 'gpu', 'canvas', 'pixel_ratio', 'profiles'])
      && ['workstation', 'mobile_ar'].every((p) => bench.profiles[p]
        && has(bench.profiles[p], ['live_tris', 'live_draws', 'frame_ms_p50', 'frame_ms_p95', 'frac_longer_than_1p5_median'])
        && bench.profiles[p].frames === 600);
    check(okShape, 'bench.json has the shape SCN-04 and PERF-01 read', JSON.stringify(bench.profiles));
    check(await benchPage.locator('#bench a[download="bench.json"]').count() === 1, 'bench.json is offered for download');
    const disc = await benchPage.evaluate(() => window.tilepipe.groundDiscEnabled);
    check(disc === false, 'bench disables the ground disc');
    if (benchOut) {
      mkdirSync(dirname(benchOut), { recursive: true });
      writeFileSync(benchOut, `${JSON.stringify(bench, null, 2)}\n`);
      console.log(`wrote ${benchOut}`);
    }
    await benchPage.close();
  }

  check(offOrigin.size === 0, 'same-origin requests only', [...offOrigin].join(', '));
  await browser.close();
  return fails.length ? 1 : 0;
}

process.exit(await run());
