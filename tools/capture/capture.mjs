// Playwright capture (SPEC P1.4): the six hero screenshots (13.10), assets/fallback.jpg, and the bench run
// (13.8) that writes build/<aoi>/bench.json. It replaces the manual steps of gate G4.
//
// Usage, from the repo root, after `uv run tilepipe all --no-blender` (or `site`) has filled site/:
//   node tools/capture/capture.mjs [--only shots|bench] [--out DIR] [--aoi ID] [--headless]
// --out DIR writes everything under DIR (docs/img, assets, build/<aoi>) instead of the repository, to look at a
// run before it replaces the committed images. The bench runs in a visible window by default: one headless run
// measured 8 percent of frames over 1.5 times the median, above the 2 percent line of PERF-01. --headless hides it.
// The script serves site/ itself on a free local port and stops the server when it finishes. Nothing leaves
// 127.0.0.1.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const args = process.argv.slice(2);
const flag = (name) => args.includes(`--${name}`);
const opt = (name, dflt) => (args.includes(`--${name}`) ? args[args.indexOf(`--${name}`) + 1] : dflt);

const only = opt('only', 'all');
const out = path.resolve(opt('out', ROOT));
const aoi = opt('aoi', (fs.readFileSync(path.join(ROOT, 'aois.toml'), 'utf8').match(/^\[(\w+)\]/m) || [])[1]);
if (!['all', 'shots', 'bench'].includes(only) || !aoi) throw new Error('usage: see the header of tools/capture/capture.mjs');
const dest = {
  img: path.join(out, 'docs', 'img'),
  fallback: path.join(out, 'assets', 'fallback.jpg'),
  bench: path.join(out, 'build', aoi, 'bench.json'),
};
// Software GL is slow and its frame times mean nothing, so ask Chrome for the real GPU path.
const GPU = ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Serve site/ with the project's own handler (MIME types of 13.9) on a port the OS picks.
async function startServer() {
  const code = 'from pathlib import Path; from tilepipe.site import make_server; s = make_server(Path("."), 0); '
    + 'print(s.server_address[1], flush=True); s.serve_forever()';
  const child = spawn('uv', ['run', 'python', '-c', code], {
    cwd: ROOT, env: { ...process.env, PYTHONPATH: path.join(ROOT, 'src') }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr.pipe(process.stderr);
  const port = await new Promise((resolve, reject) => {
    child.on('exit', (c) => reject(new Error(`server exited with ${c}; run \`uv run tilepipe site\` first`)));
    child.stdout.once('data', (d) => resolve(Number(String(d).trim())));
  });
  return { base: `http://127.0.0.1:${port}/`, stop: () => spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' }) };
}

async function launch(headless) {
  try { return await chromium.launch({ channel: 'chrome', headless, args: GPU }); } catch (e) {
    console.log(`Chrome not available (${e.message.split('\n')[0]}); using Playwright Chromium`);
    return chromium.launch({ headless, args: GPU });
  }
}

async function open(browser, base, query) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => { throw e; });
  await page.goto(base + query);
  await page.waitForFunction(() => window.tilepipe && window.tilepipe.profile && document.getElementById('budget')
    && (!document.getElementById('progress') || document.getElementById('progress').hidden), null, { timeout: 60000 });
  await sleep(1500);
  return { ctx, page };
}

// Camera: target [x,y,z] in tile units, distance, elevation and azimuth in degrees (azimuth clockwise from north).
const place = (page, t, d, el, az) => page.evaluate(([t, d, el, az]) => {
  const v = window.tilepipe;
  const c = v.controls;
  c.enableDamping = false;
  if (el > 85) c.minPolarAngle = 0;
  const r = Math.PI / 180;
  c.target.set(...t);
  v.camera.position.set(t[0] + d * Math.cos(el * r) * Math.sin(az * r), t[1] + d * Math.sin(el * r),
    t[2] - d * Math.cos(el * r) * Math.cos(az * r));
  v.camera.lookAt(...t);
  c.update();
}, [t, d, el, az]);

// Centroid of the first three entity instances, on the drawn surface, for the 0.4 m close view (H5).
const entityCentroid = (page) => page.evaluate(() => {
  const v = window.tilepipe;
  const ins = v.scene.instances.slice(0, 3);
  const S = v.tile.table.scale; const half = v.tile.extent_m / 2;
  const x = ins.reduce((a, e) => a + (e.x - half) / S, 0) / ins.length;
  const z = ins.reduce((a, e) => a + (e.z - half) / S, 0) / ins.length;
  const h = v.hud.readoutAt(x * S + half, z * S + half).elevation_m;
  return [x, (h - v.tile.height.min) * v.exaggeration / S + 0.010, z];
});

async function shots(base) {
  fs.mkdirSync(dest.img, { recursive: true });
  fs.mkdirSync(path.dirname(dest.fallback), { recursive: true });
  const browser = await launch(true);
  const take = async (query, file, setup, jpeg) => {
    const { ctx, page } = await open(browser, base, query);
    if (setup) await setup(page);
    await sleep(1200);
    await page.screenshot({ path: path.join(dest.img, file) });
    if (jpeg) await page.screenshot({ path: dest.fallback, type: 'jpeg', quality: 90 });  // the fallback page picture is H1 as JPEG
    console.log('wrote', file);
    await ctx.close();
  };
  const ws = '?tour=0&profile=workstation';
  const ar = '?tour=0&profile=mobile_ar';
  await take(ws, 'h1_workstation_opaque.png', null, true);
  await take(ar, 'h2_mobile_ar_additive.png', (p) => p.evaluate(() => { window.tilepipe.setLook('additive'); window.tilepipe.hud.refresh(); }));
  await take(ws, 'h3_workstation_lod_wireframe.png', async (p) => {  // close enough that the triangles show
    await p.evaluate(() => { window.tilepipe.setDebug('both'); window.tilepipe.hud.refresh(); });
    await place(p, [0.15, 0.03, 0.2], 0.75, 38, 150);
  });
  await take(ar, 'h4_mobile_ar_lod_tint.png', (p) => p.evaluate(() => { window.tilepipe.setDebug('lod'); window.tilepipe.hud.refresh(); }));
  await take(ws, 'h5_entities_0p4m.png', async (p) => place(p, await entityCentroid(p), 0.4, 35, 200));
  await take(ws, 'h6_topdown_grid.png', async (p) => {
    await p.evaluate(() => { window.tilepipe.setToggles({ grid: true }); window.tilepipe.hud.refresh(); });
    await place(p, [0, 0.05, 0], 2.15, 89.99, 180);
  });
  console.log('wrote', path.relative(out, dest.fallback));
  await browser.close();
}

async function bench(base) {
  const browser = await launch(flag('headless'));
  const { ctx, page } = await open(browser, base, '?bench=1');
  await page.waitForFunction(() => document.body.dataset.bench === 'done', null, { timeout: 240000 });
  const r = await page.evaluate(() => window.tilepipe.benchResult);
  fs.mkdirSync(path.dirname(dest.bench), { recursive: true });
  fs.writeFileSync(dest.bench, `${JSON.stringify(r, null, 2)}\n`);
  console.log('wrote', path.relative(out, dest.bench), JSON.stringify(r.profiles));
  await ctx.close();
  await browser.close();
}

const server = await startServer();
try {
  if (only !== 'bench') await shots(server.base);
  if (only !== 'shots') await bench(server.base);
} finally {
  server.stop();
}
process.exit(0);
