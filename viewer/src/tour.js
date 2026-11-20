// Guided tour (SPEC 13.7). One timeline of four 5 s steps. Any pointer or key input cancels it.
import { viewer, setProfile, setLook, setDebug } from './main.js';
import { DEFAULT_VIEW, orbitPosition } from './camera.js';
import * as THREE from 'three';

export const STEP_S = 5;
export const TOUR_S = 20;
const ORBIT_DEG = 25;
const PROFILE_LABEL = { workstation: 'Workstation', mobile_ar: 'Mobile AR' };

export function tourEnabled() {
  const q = new URLSearchParams(location.search);
  if (q.get('tour') === '0' || q.get('bench') === '1' || q.get('probe') === '1') return false;
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// hooks: { begin(), end(), caption(text | null) }. Returns { play, cancel, active }.
export function createTour(hooks) {
  let run = null;
  const events = ['pointerdown', 'keydown', 'wheel', 'touchstart'];

  function stop() {
    if (!run) return;
    const { initial } = run;
    cancelAnimationFrame(run.raf);
    for (const e of events) window.removeEventListener(e, cancel, true);
    run = null;
    delete document.body.dataset.tourStep;
    viewer.controls.enabled = true;
    // At the end the initial profile and look are restored (13.7).
    setDebug('none');
    setLook(initial.look);
    if (viewer.profile !== initial.profile) setProfile(initial.profile).then(hooks.end, hooks.end);
    else hooks.end();
    hooks.caption(null);
  }

  let lastCancel = null; // the input event that ended the tour, so a key press is not also a shortcut
  function cancel(e) {
    lastCancel = e;
    stop();
  }

  function enter(step) {
    const other = run.initial.profile === 'workstation' ? 'mobile_ar' : 'workstation';
    const tile = viewer.tile;
    if (step === 0) hooks.caption(`10.24 km of ${tile.name} from public USGS elevation data`);
    if (step === 1) {
      setDebug('both');
      hooks.caption('Geometry is chosen per hardware profile by measured error');
    }
    if (step === 2) {
      const p = tile.profiles[other];
      setProfile(other).then(hooks.sync);
      hooks.caption(`${PROFILE_LABEL[other]} budget: ${p.terrain_tris.toLocaleString('en-US')} triangles, `
        + `${p.error_px_nominal.toFixed(1)} px of terrain error`);
    }
    if (step === 3) {
      setDebug('none');
      setLook('additive');
      hooks.caption('Preview for see-through displays: black adds no light');
    }
    hooks.sync();
    document.body.dataset.tourStep = String(step); // observable step state for tests; set with the caption
  }

  function tick(now) {
    if (!run) return;
    const t = (now - run.t0) / 1000;
    if (t >= TOUR_S) {
      stop();
      return;
    }
    const step = Math.floor(t / STEP_S);
    if (step !== run.step) {
      run.step = step;
      enter(step);
    }
    const az = DEFAULT_VIEW.azimuthDeg + ORBIT_DEG * Math.min(t, STEP_S) / STEP_S;
    viewer.camera.position.copy(orbitPosition(new THREE.Vector3(...DEFAULT_VIEW.target), DEFAULT_VIEW.distance,
      DEFAULT_VIEW.elevationDeg, az));
    run.raf = requestAnimationFrame(tick);
  }

  function play() {
    if (run || !viewer.tile || viewer.fallback) return;
    run = { initial: { profile: viewer.profile, look: viewer.look }, step: -1, t0: performance.now(), raf: 0 };
    hooks.begin();
    viewer.controls.enabled = false;
    viewer.resetCamera();
    for (const e of events) window.addEventListener(e, cancel, true);
    run.raf = requestAnimationFrame(tick);
  }

  return { play, cancel, get active() { return run !== null; }, endedBy: (e) => e === lastCancel };
}
