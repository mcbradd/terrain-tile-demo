// Compiles and links every viewer shader pair in a headless WebGL2 context (WP09 test, SPEC 19.4).
// Usage: node tests/glsl_compile.mjs. Exit 0 all pass, 1 a compile or link error, 77 no headless browser.
// The page is about:blank and the sources are passed in, so the check makes no network request.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'viewer', 'src', 'shaders');
const PAIRS = [
  ['terrain.vert.glsl', 'terrain.frag.glsl'],
  ['entity.vert.glsl', 'entity.frag.glsl'],
  ['composite.vert.glsl', 'composite.frag.glsl'],
  ['terrain.vert.glsl', 'line.frag.glsl'],
  ['terrain.vert.glsl', 'overdraw_count.frag.glsl'],
  ['entity.vert.glsl', 'overdraw_count.frag.glsl'],
  ['composite.vert.glsl', 'overdraw_heat.frag.glsl'],
];
const src = Object.fromEntries(PAIRS.flat().map((f) => [f, readFileSync(join(dir, f), 'utf8')]));

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  console.log('SKIP: playwright is not installed');
  process.exit(77);
}

// Playwright's own Chromium first, then installed Chrome or Edge.
let browser = null;
for (const opts of [{}, { channel: 'chrome' }, { channel: 'msedge' }]) {
  try {
    browser = await chromium.launch({ headless: true, ...opts });
    break;
  } catch {
    // try the next browser
  }
}
if (!browser) {
  console.log('SKIP: no headless browser available to Playwright');
  process.exit(77);
}

const page = await browser.newPage();
const results = await page.evaluate(({ pairs, src }) => {
  const gl = document.createElement('canvas').getContext('webgl2');
  if (!gl) return [{ pair: 'context', ok: false, log: 'no WebGL2 context' }];
  const compile = (type, text) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, text);
    gl.compileShader(s);
    return [s, gl.getShaderParameter(s, gl.COMPILE_STATUS) ? '' : gl.getShaderInfoLog(s)];
  };
  return pairs.map(([v, f]) => {
    const [vs, vlog] = compile(gl.VERTEX_SHADER, src[v]);
    const [fs, flog] = compile(gl.FRAGMENT_SHADER, src[f]);
    let log = [vlog && `${v}: ${vlog}`, flog && `${f}: ${flog}`].filter(Boolean).join('\n');
    if (!log) {
      const p = gl.createProgram();
      gl.attachShader(p, vs);
      gl.attachShader(p, fs);
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) log = `link: ${gl.getProgramInfoLog(p)}`;
    }
    return { pair: `${v} + ${f}`, ok: !log, log };
  });
}, { pairs: PAIRS, src });
await browser.close();

let failed = 0;
for (const r of results) {
  console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.pair}${r.log ? `\n${r.log}` : ''}`);
  if (!r.ok) failed += 1;
}
process.exit(failed ? 1 : 0);
