// WP09 render check (SPEC 19.4): bundle the viewer, serve it on 127.0.0.1, and load it headless.
// Usage: node tests/viewer_check.mjs [--serve]
//   default  build site/, load both profiles in both looks, check the fallback, write build/wp09/*.png
//   --serve  build site/ and keep serving it on 127.0.0.1:8000
// Exit 0 pass, 1 fail, 77 no headless browser.
// ponytail: stands in for `tilepipe site` / `tilepipe serve` while site.py is a WP10 stub. It writes the 13.9
// layout without index.html styling, styles.css, the report, or assets; WP10's site.py replaces it.
import { build } from 'esbuild';
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const site = join(root, 'site');
const shots = join(root, 'build', 'wp09');
const SERVE = process.argv.includes('--serve');
let ORIGIN = 'http://127.0.0.1'; // set once listening: port 8000 with --serve, else a free port

// AOI ids in aois.toml order; the first one with a dist/ tile is the default, as in the CLI.
const AOIS = [...readFileSync(join(root, 'aois.toml'), 'utf8').matchAll(/^\[([a-z0-9_]+)\]/gm)].map((m) => m[1]);
const DEFAULT_AOI = AOIS.find((a) => existsSync(join(root, 'dist', a, 'tile.json')));

// 17.14: no AOI id from aois.toml may appear literally anywhere under viewer/src.
function aoiLiterals(dir = join(root, 'viewer', 'src')) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return aoiLiterals(p);
    const src = readFileSync(p, 'utf8');
    return AOIS.filter((a) => src.includes(a)).map((a) => `${p.slice(root.length + 1)}: ${a}`);
  });
}

// ---------- site/ (13.9 layout, viewer parts only) ----------

async function buildSite() {
  rmSync(site, { recursive: true, force: true });
  mkdirSync(site, { recursive: true });
  await build({
    entryPoints: [join(root, 'viewer', 'src', 'main.js')],
    bundle: true,
    format: 'iife',
    target: 'es2020',
    minify: true,
    sourcemap: true,
    loader: { '.glsl': 'text' },
    outfile: join(site, 'app.js'),
    logLevel: 'warning',
  });
  writeFileSync(join(site, 'index.html'), `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Terrain Tile Pipeline Demo</title></head>
<body style="margin:0;background:#0E1013"><canvas id="view"></canvas><script src="app.js"></script></body></html>
`);
  writeFileSync(join(site, 'config.json'), `${JSON.stringify({ aoi: DEFAULT_AOI, video_url: '' })}\n`);
  writeFileSync(join(site, '.nojekyll'), '');
  cpSync(join(root, 'look'), join(site, 'look'), { recursive: true });
  const dist = join(root, 'dist');
  for (const aoi of readdirSync(dist)) {
    const d = join(dist, aoi);
    if (aoi === 'entities' || !existsSync(join(d, 'tile.json'))) continue;
    const tile = JSON.parse(readFileSync(join(d, 'tile.json'), 'utf8'));
    const files = ['tile.json', 'scene.json', 'validation.json', ...tile.textures.map((t) => t.file),
      ...Object.values(tile.profiles).flatMap((p) => p.batches.map((b) => b.file))];
    mkdirSync(join(site, 'data', aoi), { recursive: true });
    for (const f of files) if (existsSync(join(d, f))) cpSync(join(d, f), join(site, 'data', aoi, f));
  }
  if (existsSync(join(dist, 'entities'))) cpSync(join(dist, 'entities'), join(site, 'data', 'entities'), { recursive: true });
}

// ---------- static server (13.9 MIME types) ----------

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.map': 'application/json', '.json': 'application/json',
  '.css': 'text/css', '.jpg': 'image/jpeg', '.glb': 'model/gltf-binary', '.bin': 'application/octet-stream' };

function serve() {
  const server = createServer((req, res) => {
    const rel = normalize(decodeURIComponent(new URL(req.url, ORIGIN).pathname)).replace(/^[\\/]+/, '');
    let file = join(site, rel);
    if (!file.startsWith(site + sep) && file !== site) { res.writeHead(403).end(); return; }
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
    if (!existsSync(file)) { res.writeHead(404).end(); return; }
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' });
    res.end(readFileSync(file));
  });
  return new Promise((ok) => server.listen(SERVE ? 8000 : 0, '127.0.0.1', () => {
    ORIGIN = `http://127.0.0.1:${server.address().port}`;
    ok(server);
  }));
}

// ---------- checks ----------

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

// Requests that may 404 while other packages are pending: entity GLBs (WP11) and the fallback image.
// assets/room.jpg is not here: the viewer requests it only when config.json says it is shipped.
const OPTIONAL = /\/(data\/entities\/|assets\/fallback\.jpg|data\/[^/]+\/validation\.json)/;

async function check() {
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
  mkdirSync(shots, { recursive: true });
  const fails = [];
  const fail = (m) => { fails.push(m); console.log(`FAIL ${m}`); };
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const offOrigin = new Set();
  page.on('request', (r) => { if (!r.url().startsWith(`${ORIGIN}/`) && !r.url().startsWith('data:')) offOrigin.add(r.url()); });
  page.on('response', (r) => { if (r.status() >= 400 && !OPTIONAL.test(r.url())) fail(`HTTP ${r.status()} ${r.url()}`); });
  page.on('pageerror', (e) => fail(`page error: ${e.message}`));

  for (const profile of ['workstation', 'mobile_ar']) {
    await page.goto(`${ORIGIN}/?profile=${profile}&tour=0`);
    await page.evaluate(() => window.tilepipe.ready);
    for (const look of ['opaque', 'additive']) {
      const info = await page.evaluate(async (l) => {
        const v = window.tilepipe;
        v.setLook(l);
        for (let i = 0; i < 8; i++) await new Promise((r) => requestAnimationFrame(r));
        const terrain = v.tile.profiles[v.profile].terrain_tris;
        return { profile: v.profile, look: v.look, tris: v.sceneInfo.triangles, calls: v.sceneInfo.calls, terrain,
          entities: v.tile.entities.length };
      }, look);
      const ok = info.profile === profile && info.look === look && info.tris >= info.terrain;
      console.log(`${ok ? 'PASS' : 'FAIL'} ${profile} ${look}: ${info.tris} triangles (terrain ${info.terrain}), ${info.calls} draws`);
      if (!ok) fails.push(`${profile} ${look}`);
      await page.screenshot({ path: join(shots, `${profile}_${look}.png`) });
    }
  }
  // In-place switch disposes and reloads the batches (13.2 step 8).
  const switched = await page.evaluate(async () => {
    const v = window.tilepipe;
    await v.setProfile('workstation');
    for (let i = 0; i < 4; i++) await new Promise((r) => requestAnimationFrame(r));
    return v.sceneInfo.triangles >= v.tile.profiles.workstation.terrain_tris;
  });
  console.log(`${switched ? 'PASS' : 'FAIL'} profile switch mobile_ar -> workstation`);
  if (!switched) fails.push('profile switch');
  // Close-up for line and shading quality, opaque look.
  await page.evaluate(async () => {
    const v = window.tilepipe;
    v.setLook('opaque');
    v.controls.enableDamping = false;
    v.controls.target.set(-0.15, 0.08, -0.1);
    v.camera.position.set(0.05, 0.35, 0.25);
    v.controls.update();
    for (let i = 0; i < 4; i++) await new Promise((r) => requestAnimationFrame(r));
  });
  await page.screenshot({ path: join(shots, 'workstation_opaque_close.png') });

  if (offOrigin.size) fail(`off-origin requests: ${[...offOrigin].join(', ')}`);
  else console.log('PASS same-origin requests only');

  // Fallback (13.4 step 1, 13.10): hide the float color extension.
  const fb = await ctx.newPage();
  await fb.addInitScript(() => {
    const get = WebGL2RenderingContext.prototype.getExtension;
    WebGL2RenderingContext.prototype.getExtension = function (name) {
      return name === 'EXT_color_buffer_float' ? null : get.call(this, name);
    };
  });
  await fb.goto(`${ORIGIN}/?tour=0`);
  const text = await fb.locator('#fallback p').textContent({ timeout: 10000 }).catch(() => '');
  const canvasGone = (await fb.locator('canvas').count()) === 0;
  const fbOk = text.includes('This demo needs WebGL2 with float render targets.') && canvasGone;
  console.log(`${fbOk ? 'PASS' : 'FAIL'} fallback page without a float target`);
  if (!fbOk) fails.push('fallback');
  await fb.screenshot({ path: join(shots, 'fallback.png') });

  await browser.close();
  return fails.length ? 1 : 0;
}

const literals = aoiLiterals();
for (const l of literals) console.log(`FAIL AOI id literal in ${l}`);
if (!literals.length) console.log(`PASS no aois.toml id appears under viewer/src (${AOIS.length} ids)`);
if (!AOIS.length || literals.length) process.exit(1);
await buildSite();
const server = await serve();
if (SERVE) {
  console.log(`serving site/ on ${ORIGIN}/`);
} else {
  const code = await check();
  server.close();
  process.exit(code);
}
