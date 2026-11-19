// HUD, cursor readout, probe mode, and the hook-up of tour and bench (SPEC 13.5, 13.7, 13.8, G4).
// A DOM overlay on top of the canvas. All requests are same-origin; the only fetches here are entity.json files.
import * as THREE from 'three';
import { viewer, setProfile, setLook, setExaggeration, setToggles, setDebug } from './main.js';
import { createTour, tourEnabled } from './tour.js';
import { runBench, showBench } from './bench.js';

const PROFILES = ['workstation', 'mobile_ar'];
const PROFILE_LABEL = { workstation: 'Workstation', mobile_ar: 'Mobile AR' };
const LOOK_LABEL = { opaque: 'Opaque', additive: 'Additive' };
const DEBUG_LABEL = { none: 'None', wireframe: 'Wireframe', lod: 'LOD tint', overdraw: 'Overdraw' };
const STEM_TRIS = 16;
const MIB = 1048576;
const MARCH_STEPS = 512;
const BISECTIONS = 8;
// Budget limits and class descriptions come from profiles/*.toml, which tile.json does not carry. site.py embeds
// them with an esbuild define (Deviation D-09).
// eslint-disable-next-line no-undef
const PROFILE_INFO = typeof __TILEPIPE_PROFILES__ !== 'undefined' ? __TILEPIPE_PROFILES__ : {};

// ---------- cursor data (13.5, Cursor) ----------

// Height in meters at tile-local (x, z), bilinear between cell centers of the CPU copy of the height texture.
// h = min + (R * 65280 + G * 255) / 65535 * (max - min) with R and G as bytes / 255, which is (256 R + G) / 65535.
export function heightAt(cpu, tile, x, z) {
  const n = cpu.width;
  const fx = Math.min(Math.max(x / tile.cell_m - 0.5, 0), n - 1);
  const fz = Math.min(Math.max(z / tile.cell_m - 0.5, 0), n - 1);
  const c0 = Math.min(Math.floor(fx), n - 2);
  const r0 = Math.min(Math.floor(fz), n - 2);
  const tx = fx - c0;
  const tz = fz - r0;
  const d = cpu.data;
  const texel = (r, c) => (d[(r * n + c) * 2] * 256 + d[(r * n + c) * 2 + 1]) / 65535;
  const v = (texel(r0, c0) * (1 - tx) + texel(r0, c0 + 1) * tx) * (1 - tz)
    + (texel(r0 + 1, c0) * (1 - tx) + texel(r0 + 1, c0 + 1) * tx) * tz;
  return tile.height.min + v * (tile.height.max - tile.height.min);
}

const MGRS_COLUMNS = ['ABCDEFGH', 'JKLMNPQR', 'STUVWXYZ'];
const MGRS_ROWS = 'ABCDEFGHJKLMNPQRSTUV';

// MGRS to 1 m from UTM. The band letter is the tile's; the tile spans well under one band.
export function mgrsOf(tile, easting, northing) {
  if (!tile.mgrs) return null;
  const zone = tile.crs.zone;
  const col = MGRS_COLUMNS[(zone - 1) % 3][Math.floor(easting / 100000) - 1];
  const row = MGRS_ROWS[(Math.floor(northing / 100000) + (zone % 2 === 0 ? 5 : 0)) % 20];
  const digits = (v) => String(Math.floor(v % 100000)).padStart(5, '0');
  return `${tile.mgrs.gzd}${col}${row}${digits(easting)}${digits(northing)}`;
}

// UTM, MGRS, elevation, and slope at tile-local (x, z) (6.1). UTM is E0 + x and N_top - z.
export function readoutAt(x, z) {
  const tile = viewer.tile;
  const cpu = viewer.cpu.height;
  const easting = tile.origin.E0 + x;
  const northing = tile.origin.N_top - z;
  const s = tile.cell_m;
  const dx = (heightAt(cpu, tile, x + s, z) - heightAt(cpu, tile, x - s, z)) / (2 * s);
  const dz = (heightAt(cpu, tile, x, z + s) - heightAt(cpu, tile, x, z - s)) / (2 * s);
  return { x, z, zone: tile.crs.zone, easting, northing, mgrs: mgrsOf(tile, easting, northing),
    elevation_m: heightAt(cpu, tile, x, z), slope_deg: Math.atan(Math.hypot(dx, dz)) * 180 / Math.PI };
}

// March a table-space ray through the CPU height copy: 512 uniform steps across the tile bounds, then 8 bisections
// on the first crossing (13.5). Returns tile-local { x, z } or null.
export function pickTerrain(origin, direction) {
  const tile = viewer.tile;
  const S = tile.table.scale;
  const V = viewer.exaggeration;
  const half = tile.extent_m / 2;
  const o = [origin.x * S + half, (origin.y - 0.010) * S / V + tile.height.min, origin.z * S + half];
  const d = [direction.x * S, direction.y * S / V, direction.z * S];
  const lo = [0, tile.height.min, 0];
  const hi = [tile.extent_m, tile.height.max, tile.extent_m];
  let t0 = 0;
  let t1 = Infinity;
  for (let a = 0; a < 3; a++) {
    if (Math.abs(d[a]) < 1e-12) {
      if (o[a] < lo[a] || o[a] > hi[a]) return null;
      continue;
    }
    const ta = (lo[a] - o[a]) / d[a];
    const tb = (hi[a] - o[a]) / d[a];
    t0 = Math.max(t0, Math.min(ta, tb));
    t1 = Math.min(t1, Math.max(ta, tb));
  }
  if (!(t1 > t0)) return null;
  const f = (t) => (o[1] + d[1] * t) - heightAt(viewer.cpu.height, tile, o[0] + d[0] * t, o[2] + d[2] * t);
  let prev = t0;
  if (f(t0) <= 0) return { x: o[0] + d[0] * t0, z: o[2] + d[2] * t0 };
  for (let i = 1; i <= MARCH_STEPS; i++) {
    const t = t0 + ((t1 - t0) * i) / MARCH_STEPS;
    if (f(t) <= 0) {
      let a = prev;
      let b = t;
      for (let k = 0; k < BISECTIONS; k++) {
        const m = (a + b) / 2;
        if (f(m) <= 0) b = m;
        else a = m;
      }
      const tm = (a + b) / 2;
      return { x: o[0] + d[0] * tm, z: o[2] + d[2] * tm };
    }
    prev = t;
  }
  return null;
}

// ---------- DOM helpers ----------

function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  kids.forEach((kid) => e.append(kid));
  return e;
}

function segmented(id, options, onPick) {
  const box = el('div', { class: 'seg', id, role: 'group' });
  for (const [value, label] of options) {
    box.append(el('button', { type: 'button', 'data-value': String(value), text: label, onclick: () => onPick(value) }));
  }
  return box;
}

function setSegmented(id, value) {
  for (const b of document.querySelectorAll(`#${id} button`)) {
    b.setAttribute('aria-pressed', String(b.dataset.value === String(value)));
  }
}

function chip(status, text = status) {
  return el('span', { class: `chip ${status.toLowerCase()}`, text });
}

const fmt = (n) => Math.round(n).toLocaleString('en-US');

// ---------- panels ----------

const ui = {};
let tour = null;
let entityTris = {}; // profile -> total entity triangles, or null when entity.json is not built

function budgetPanel() {
  const bars = ['terrain', 'frame', 'draws', 'tex'].map((k) => {
    const label = { terrain: 'Terrain triangles', frame: 'Frame triangles', draws: 'Draw calls',
      tex: 'Texture memory' }[k];
    const fill = el('i');
    const text = el('span', { class: 'num' });
    ui[`bar_${k}`] = { fill, text };
    return el('div', { class: 'row' }, el('div', { class: 'lbl' }, el('span', { text: label }), text),
      el('div', { class: 'bar' }, fill));
  });
  ui.klass = el('p', { class: 'muted' });
  ui.terr = el('p', { class: 'num' });
  ui.chip = el('div', { class: 'chiprow' });
  ui.progress = null;
  return el('section', { id: 'budget', class: 'panel collapsible' },
    el('h2', { text: 'Budget' }),
    segmented('seg-profile', PROFILES.map((p) => [p, PROFILE_LABEL[p]]), (p) => switchProfile(p)),
    ui.klass, ...bars, ui.terr, ui.chip,
    el('a', { href: 'report/index.html', text: 'Full report' }),
    el('p', { class: 'muted', text: 'Static counts. No headset performance was measured.' }));
}

function viewPanel() {
  const check = (key, label) => el('label', {}, el('input', { type: 'checkbox', id: `chk-${key}`,
    onchange: (e) => { setToggles({ [key]: e.target.checked }); refresh(); } }), document.createTextNode(` ${label}`));
  const radio = (v) => el('label', {}, el('input', { type: 'radio', name: 'debug', value: v, id: `dbg-${v}`,
    onchange: () => { setDebug(v); refresh(); } }), document.createTextNode(` ${DEBUG_LABEL[v]}`));
  return el('section', { id: 'view-panel', class: 'panel collapsible' },
    el('h2', { text: 'View' }),
    el('div', { class: 'row' }, el('span', { class: 'lbl', text: 'Look' }),
      segmented('seg-look', Object.entries(LOOK_LABEL), (v) => { setLook(v); refresh(); })),
    el('div', { class: 'row' }, el('span', { class: 'lbl', text: 'Exaggeration' }),
      segmented('seg-exag', viewer.tile.table.exaggeration_allowed.map((v) => [v, v.toFixed(1)]),
        (v) => { setExaggeration(v); refresh(); })),
    el('div', { class: 'row checks' }, check('contours', 'Contours'), check('grid', 'Grid'),
      check('entities', 'Entities'), check('slope', 'Slope classes')),
    el('div', { class: 'row checks' }, radio('none'), radio('wireframe'), radio('lod'), radio('overdraw')),
    el('button', { type: 'button', id: 'btn-tour', class: 'accent', text: 'Play tour', onclick: toggleTour }));
}

function titlePanel() {
  const tile = viewer.tile;
  const about = el('div', { id: 'about', class: 'panel', hidden: '' },
    el('p', { text: 'A tabletop terrain viewer drawn in real time from a data contract.' }),
    el('p', { text: 'Public USGS elevation data is cut into a 10.24 km tile and shown at 1:8000.' }),
    el('p', { text: 'The terrain mesh is chosen per hardware profile by measured error.' }),
    el('p', { text: 'Entities are generated placeholder tokens, not models of real things.' }),
    el('p', { text: 'No headset performance was measured.' }),
    ui.links = el('p', { class: 'links' }));
  ui.links.append(el('a', { href: 'report/index.html', text: 'Report' }), document.createTextNode(' | '),
    ui.repo = el('span', { class: 'muted', text: 'Repository not yet published' }), document.createTextNode(' | '),
    ui.video = el('span', { class: 'muted', text: 'Video not yet published' }));
  return el('section', { id: 'title', class: 'panel' },
    el('h1', { text: 'Terrain Tile Pipeline Demo' }),
    ui.tileName = el('p', { class: 'tile', text: tile.name }),
    el('p', { text: 'By Bradd McBrearty' }),
    el('p', { class: 'credit', text: tile.source.credit }),
    el('button', { type: 'button', id: 'btn-about', text: 'About',
      onclick: () => { about.hidden = !about.hidden; } }),
    about);
}

async function loadVideoLink() {
  try {
    const res = await fetch('config.json');
    const cfg = await res.json();
    if (typeof cfg.video_url === 'string' && /^https?:\/\//.test(cfg.video_url)) {
      ui.video.replaceWith(el('a', { href: cfg.video_url, text: 'Video' }));
    }
    if (typeof cfg.repo_url === 'string' && /^https?:\/\//.test(cfg.repo_url)) {
      ui.repo.replaceWith(el('a', { href: cfg.repo_url, text: 'Repository' }));
    }
    aoiSwitch(cfg.aois);
  } catch (e) {
    console.warn(`config.json not read: ${e.message}`);
  }
}

// AOI ids and names come from the `aois` map `tilepipe site` writes into config.json (17.14). With more than one
// hosted AOI the tile name becomes a picker that reloads the page with ?aoi=<id>.
function aoiSwitch(aois) {
  if (!aois || typeof aois !== 'object' || Object.keys(aois).length < 2) return;
  const pick = el('select', { id: 'sel-aoi', class: 'tile', 'aria-label': 'Area of interest',
    onchange: (e) => {
      const q = new URLSearchParams(location.search);
      q.set('aoi', e.target.value);
      location.search = q.toString();
    } });
  for (const [id, name] of Object.entries(aois)) {
    const o = el('option', { value: id, text: name });
    if (id === viewer.tile.tile_id) o.selected = true;
    pick.append(o);
  }
  ui.tileName.replaceWith(pick);
}

// ---------- state sync ----------

function chipStatus(name) {
  const s = viewer.validation && viewer.validation.summary && viewer.validation.summary[`profile:${name}`];
  if (!s) return null;
  const verdict = s.fail > 0 ? 'FAIL' : 'PASS';
  return { verdict, text: s.warn > 0 ? `${verdict}, ${s.warn} warning${s.warn === 1 ? '' : 's'}` : verdict };
}

function setBar(k, used, max, text) {
  const { fill, text: t } = ui[`bar_${k}`];
  fill.style.width = `${Math.min(100, max ? (100 * used) / max : 0)}%`;
  fill.classList.toggle('over', max > 0 && used > max);
  t.textContent = text;
}

export function refresh() {
  if (!viewer.tile || !viewer.profile) return;
  const name = viewer.profile;
  const p = viewer.tile.profiles[name];
  const info = PROFILE_INFO[name] || {};
  const b = info.budget || {};
  setSegmented('seg-profile', name);
  setSegmented('seg-look', viewer.look);
  setSegmented('seg-exag', viewer.exaggeration);
  ui.klass.textContent = `ASSUMED class: ${info.description || 'not available'}`;
  const of = (v, max, f = fmt) => (max ? `${f(v)} / ${f(max)}` : `${f(v)} / n/a`);
  setBar('terrain', p.terrain_tris, b.terrain_tris_max, of(p.terrain_tris, b.terrain_tris_max));
  const ent = entityTris[name];
  const frame = p.terrain_tris + (ent ?? 0) + STEM_TRIS;
  setBar('frame', frame, b.frame_tris_max, of(frame, b.frame_tris_max) + (ent == null ? ' (entities not built)' : ''));
  const draws = p.terrain_draws + viewer.tile.entities.length + 1;
  setBar('draws', draws, b.draw_calls_max, of(draws, b.draw_calls_max));
  const mib = (v) => (v / MIB).toFixed(1);
  setBar('tex', p.texture_bytes, b.texture_bytes_max, of(p.texture_bytes, b.texture_bytes_max, mib) + ' MiB');
  ui.terr.textContent = `Terrain error: ${p.e_star_m.toFixed(1)} m = ${p.error_px_nominal.toFixed(1)} px at 0.75 m`
    + (p.budget_forced ? ', budget-forced' : '');
  const status = chipStatus(name);
  ui.chip.replaceChildren(el('span', { text: 'Validation ' }), status ? chip(status.verdict, status.text) : el('span', { class: 'muted',
    text: 'not run' }));
  document.getElementById('chk-contours').checked = viewer.toggles.contours;
  document.getElementById('chk-grid').checked = viewer.toggles.grid;
  document.getElementById('chk-entities').checked = viewer.toggles.entities;
  document.getElementById(`dbg-${viewer.debug === 'both' ? 'lod' : viewer.debug}`).checked = true;
  document.getElementById('btn-tour').textContent = tour && tour.active ? 'Stop tour' : 'Play tour';
  refreshLegend();
}

// ---------- legend for the slope classes (P1.5) and the overdraw view (P1.3) ----------

// Same hex values as slopeTint in terrain.frag.glsl and the stops of overdraw_heat.frag.glsl.
const SLOPE_KEY = [['#6FA36F', 'Under 15 deg'], ['#E0B84A', '15 to 30 deg'], ['#D0583F', 'Over 30 deg']];
const HEAT_KEY = [['#24408A', '1'], ['#2A9D8F', '2'], ['#8AB17D', '3'], ['#E9C46A', '4'], ['#E76F51', '6'],
  ['#FFFFFF', '8+']];

function legendPanel() {
  const swatch = (hex) => el('span', { class: 'sw', style: `background:${hex}` });
  ui.legendSlope = el('div', { id: 'legend-slope', hidden: '' },
    el('h2', { text: 'Slope classes (illustrative)' }),
    ...SLOPE_KEY.map(([hex, t]) => el('p', {}, swatch(hex), document.createTextNode(` ${t}`))),
    el('p', { class: 'muted', text: 'Illustrative only: true-scale slope of the 10 m grid. Key S toggles it.' }));
  ui.odMean = el('p', { class: 'num', id: 'od-mean', text: 'Measuring.' });
  ui.legendOverdraw = el('div', { id: 'legend-overdraw', hidden: '' },
    el('h2', { text: 'Overdraw' }),
    el('p', { class: 'muted', text: 'Fragments drawn per pixel, depth test off. Key O toggles it.' }),
    el('div', { class: 'heat' }, ...HEAT_KEY.map(([hex, t]) => el('span', {}, swatch(hex),
      document.createTextNode(` ${t}`)))),
    ui.odMean);
  ui.legend = el('section', { id: 'legend', class: 'panel', hidden: '' }, ui.legendSlope, ui.legendOverdraw);
  setInterval(() => {
    const o = viewer.overdrawLive;
    if (!ui.legendOverdraw.hidden && o) {
      ui.odMean.textContent = `Mean ${o.mean_overdraw.toFixed(2)} fragments per covered pixel in this view`;
    }
  }, 500);
  return ui.legend;
}

function refreshLegend() {
  if (!ui.legend) return;
  ui.legendSlope.hidden = !viewer.toggles.slope;
  ui.legendOverdraw.hidden = viewer.debug !== 'overdraw';
  ui.legend.hidden = ui.legendSlope.hidden && ui.legendOverdraw.hidden;
  document.getElementById('chk-slope').checked = viewer.toggles.slope;
}

async function loadEntityTris() {
  entityTris = {};
  for (const name of PROFILES) {
    const n = viewer.tile.profiles[name].entity_lod;
    let total = 0;
    try {
      for (const entry of viewer.scene.instances) {
        const res = await fetch(`data/entities/${entry.entity}/entity.json`);
        if (!res.ok) throw new Error(`entity.json for ${entry.entity}: HTTP ${res.status}`);
        total += (await res.json()).lods.find((l) => l.n === n).tris;
      }
      entityTris[name] = total;
    } catch (e) {
      entityTris[name] = null;
    }
  }
  refresh();
}

async function switchProfile(name) {
  if (name === viewer.profile) return;
  await setProfile(name);
  refresh();
}

function toggleTour() {
  if (tour.active) tour.cancel();
  else tour.play();
  refresh();
}

// ---------- keys and cursor ----------

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || tour.endedBy(e)) return;
  const toggle = (key) => { setToggles({ [key]: !viewer.toggles[key] }); };
  switch (e.key.toLowerCase()) {
    case '1': switchProfile('workstation'); return;
    case '2': switchProfile('mobile_ar'); return;
    case 'l': setLook(viewer.look === 'opaque' ? 'additive' : 'opaque'); break;
    case 'e': {
      const all = viewer.tile.table.exaggeration_allowed;
      setExaggeration(all[(all.indexOf(viewer.exaggeration) + 1) % all.length]);
      break;
    }
    case 'c': toggle('contours'); break;
    case 'g': toggle('grid'); break;
    case 'w': setDebug(viewer.debug === 'wireframe' ? 'none' : 'wireframe'); break;
    case 'o': setDebug(viewer.debug === 'overdraw' ? 'none' : 'overdraw'); break; // P1.3
    case 's': toggle('slope'); break; // P1.5
    case 't': toggleTour(); return;
    case 'r': viewer.resetCamera(); break;
    case 'h': document.getElementById('hud').classList.toggle('hidden'); return;
    default: return;
  }
  refresh();
}

function cursorPanel() {
  ui.cursor = el('div', { class: 'num' }, el('p', { class: 'muted', text: 'Move the pointer over the terrain.' }));
  return el('section', { id: 'cursor', class: 'panel' }, el('h2', { text: 'Cursor' }), ui.cursor);
}

function showReadout(r) {
  if (!r) {
    ui.cursor.replaceChildren(el('p', { class: 'muted', text: 'Pointer is not over the tile.' }));
    return;
  }
  const rows = [`UTM zone ${r.zone}N`, `E ${r.easting.toFixed(1)} m  N ${r.northing.toFixed(1)} m`];
  if (r.mgrs) rows.push(`MGRS ${r.mgrs}`);
  rows.push(`Elevation ${r.elevation_m.toFixed(1)} m (NAVD88)`, `Slope ${r.slope_deg.toFixed(1)} deg`);
  ui.cursor.replaceChildren(...rows.map((t) => el('p', { text: t })));
}

function trackPointer(canvas) {
  const ray = new THREE.Raycaster();
  let last = null;
  let scheduled = false;
  canvas.addEventListener('pointermove', (e) => {
    last = e;
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      if (!viewer.cpu.height) return;
      const rect = canvas.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((last.clientX - rect.left) / rect.width) * 2 - 1,
        -(((last.clientY - rect.top) / rect.height) * 2 - 1)), viewer.camera);
      const hit = pickTerrain(ray.ray.origin, ray.ray.direction);
      viewer.lastReadout = hit ? readoutAt(hit.x, hit.z) : null;
      showReadout(viewer.lastReadout);
    });
  });
}

// ---------- start ----------

export async function initHud() {
  const q = new URLSearchParams(location.search);
  const hud = document.getElementById('hud') || document.body.appendChild(el('div', { id: 'hud' }));
  await viewer.ready.catch(() => null);
  if (viewer.fallback || !viewer.tile) return; // the fallback page of 13.10 has no HUD
  const caption = el('div', { id: 'caption', hidden: '' });
  tour = createTour({
    begin: () => { document.body.classList.add('touring'); },
    end: () => { document.body.classList.remove('touring'); refresh(); },
    caption: (text) => { caption.hidden = !text; caption.textContent = text || ''; },
    sync: refresh,
  });
  const budget = budgetPanel();
  const view = viewPanel();
  const tb = el('div', { id: 'toggles' },
    ...[['Budget', budget], ['View', view]].map(([text, panel]) => el('button', {
      type: 'button', text, 'aria-controls': panel.id, 'aria-expanded': 'false',
      onclick: (e) => e.currentTarget.setAttribute('aria-expanded', panel.classList.toggle('open')),
    })));
  hud.append(titlePanel(), tb, budget, cursorPanel(), view, caption);
  hud.append(legendPanel());
  window.addEventListener('keydown', onKey);
  trackPointer(document.getElementById('view'));
  loadVideoLink();
  refresh();
  loadEntityTris();

  viewer.hud = { heightAt, readoutAt, pickTerrain, mgrsOf, refresh };
  if (q.get('probe') === '1') {
    // G4: the readout for TL point (5120, 5120).
    viewer.probe = readoutAt(5120, 5120);
    console.log(`PROBE ${JSON.stringify(viewer.probe)}`);
  }
  if (q.get('bench') === '1') {
    document.body.classList.add('bench');
    setDebug('none');
    viewer.benchResult = await runBench();
    refresh();
    showBench(viewer.benchResult);
    console.log(`BENCH ${JSON.stringify(viewer.benchResult)}`);
    document.body.dataset.bench = 'done';
  } else if (tourEnabled()) {
    tour.play();
  }
}

initHud();
