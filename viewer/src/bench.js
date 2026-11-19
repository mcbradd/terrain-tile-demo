// Bench mode, `?bench=1` (SPEC 13.8). For each profile: load, wait 60 frames, orbit 600 frames at 0.6 degrees of
// azimuth per frame from the default view. Triangles and draw calls come from main.js `sceneInfo`, which it reads
// after the scene pass and before the composite pass (renderer.info.autoReset is false).
// The result shape is the one SCN-04 and PERF-01 read (Decision D-07).
import * as THREE from 'three';
import { viewer, setProfile, setLook, setDebug, setGroundDisc, measureOverdraw, PROFILE_LOOK } from './main.js';
import { DEFAULT_VIEW, orbitPosition } from './camera.js';

export const BENCH_PROFILES = ['workstation', 'mobile_ar'];
const WAIT_FRAMES = 60;
const ORBIT_FRAMES = 600;
const DEG_PER_FRAME = 0.6;

const round = (x) => Math.round(x * 1e6) / 1e6;

function nextFrame() {
  return new Promise((resolve) => {
    viewer.onFrame = () => {
      viewer.onFrame = null;
      resolve(performance.now());
    };
  });
}

export function percentile(sorted, p) {
  const i = (sorted.length - 1) * p;
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

// Frame times in ms to the per-profile statistics of 13.8.
export function frameStats(times) {
  const sorted = [...times].sort((a, b) => a - b);
  const p50 = percentile(sorted, 0.5);
  const long = times.filter((t) => t > 1.5 * p50).length;
  return { frame_ms_p50: round(p50), frame_ms_p95: round(percentile(sorted, 0.95)),
    frac_longer_than_1p5_median: round(long / times.length), frames: times.length };
}

function gpuString() {
  const gl = viewer.renderer.getContext();
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null;
}

export async function runBench() {
  await viewer.ready;
  setGroundDisc(false);
  setDebug('none');
  viewer.controls.enabled = false;
  const target = new THREE.Vector3(...DEFAULT_VIEW.target);
  const size = viewer.renderer.getDrawingBufferSize(new THREE.Vector2());
  const result = { user_agent: navigator.userAgent, gpu: gpuString(), canvas: { width: size.x, height: size.y },
    pixel_ratio: viewer.renderer.getPixelRatio(), profiles: {} };
  const overdraw = {};
  for (const name of BENCH_PROFILES) {
    await setProfile(name);
    setLook(PROFILE_LOOK[name]);
    viewer.resetCamera();
    for (let i = 0; i < WAIT_FRAMES; i++) await nextFrame();
    overdraw[name] = measureOverdraw(); // P1.3, at the default view before the orbit
    const times = [];
    let last = await nextFrame();
    let live = null;
    for (let i = 0; i < ORBIT_FRAMES; i++) {
      viewer.camera.position.copy(orbitPosition(target, DEFAULT_VIEW.distance, DEFAULT_VIEW.elevationDeg,
        DEFAULT_VIEW.azimuthDeg + DEG_PER_FRAME * i));
      const now = await nextFrame();
      times.push(now - last);
      last = now;
      if (i === 0) live = { live_tris: viewer.sceneInfo.triangles, live_draws: viewer.sceneInfo.calls };
    }
    result.profiles[name] = { ...live, ...frameStats(times) };
  }
  viewer.controls.enabled = true;
  viewer.resetCamera();
  viewer.overdrawResult = overdrawDoc(overdraw);
  return result;
}

// ---------- overdraw (P1.3) ----------

// overdraw.json, saved next to bench.json. A separate file because bench.json's shape is fixed by D-07.
function overdrawDoc(profiles) {
  const size = viewer.renderer.getDrawingBufferSize(new THREE.Vector2());
  return {
    canvas: { width: size.x, height: size.y },
    pixel_ratio: viewer.renderer.getPixelRatio(),
    camera: { view: 'default', target_m: [...DEFAULT_VIEW.target], distance_m: DEFAULT_VIEW.distance,
      elevation_deg: DEFAULT_VIEW.elevationDeg, azimuth_deg: DEFAULT_VIEW.azimuthDeg, fov_deg: viewer.camera.fov },
    method: 'Fragments per covered pixel: terrain batches and entities, depth test off, ground disc and wireframe '
      + 'off, one count per fragment in an 8-bit target.',
    profiles,
  };
}

// The overdraw half of bench mode alone, for scripts: each profile at the default view after WAIT_FRAMES.
export async function overdrawRun() {
  await viewer.ready;
  await viewer.risen;
  const keep = { profile: viewer.profile, look: viewer.look, debug: viewer.debug, disc: viewer.groundDiscEnabled };
  setGroundDisc(false);
  setDebug('none');
  viewer.controls.enabled = false;
  const profiles = {};
  for (const name of BENCH_PROFILES) {
    await setProfile(name);
    setLook(PROFILE_LOOK[name]);
    viewer.resetCamera();
    for (let i = 0; i < WAIT_FRAMES; i++) await nextFrame();
    profiles[name] = measureOverdraw();
  }
  const doc = overdrawDoc(profiles);
  viewer.controls.enabled = true;
  await setProfile(keep.profile);
  setLook(keep.look);
  setDebug(keep.debug);
  setGroundDisc(keep.disc);
  return doc;
}
viewer.overdrawRun = overdrawRun;

// Show the result and offer it for download. Saving it to build/<aoi>/bench.json is a manual step unless a
// script reads `window.tilepipe.benchResult`.
export function showBench(result) {
  const text = `${JSON.stringify(result, null, 2)}\n`;
  const panel = document.createElement('section');
  panel.id = 'bench';
  panel.className = 'panel';
  const h = panel.appendChild(document.createElement('h2'));
  h.textContent = 'Bench result';
  const a = panel.appendChild(document.createElement('a'));
  a.textContent = 'Download bench.json';
  a.download = 'bench.json';
  a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  if (viewer.overdrawResult) {
    panel.append(' | ');
    const o = panel.appendChild(document.createElement('a'));
    o.textContent = 'Download overdraw.json';
    o.download = 'overdraw.json';
    o.href = URL.createObjectURL(new Blob([`${JSON.stringify(viewer.overdrawResult, null, 2)}\n`],
      { type: 'application/json' }));
  }
  const pre = panel.appendChild(document.createElement('pre'));
  pre.textContent = text;
  document.getElementById('hud').appendChild(panel);
}
