// Camera and orbit controls (SPEC 13.3). Scene units are table meters; north is -Z, east is +X.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const DEG = Math.PI / 180;

export const DEFAULT_VIEW = Object.freeze({
  target: [0, 0.05, 0],
  distance: 1.9,
  elevationDeg: 32,
  azimuthDeg: 150, // clockwise from north
});

const PAN_LIMIT = 0.64; // target stays within this many meters of the origin in X and Z

// Position on the orbit sphere: target + d * (cos(el) sin(az), sin(el), -cos(el) cos(az)).
export function orbitPosition(target, distance, elevationDeg, azimuthDeg) {
  const el = elevationDeg * DEG;
  const az = azimuthDeg * DEG;
  return new THREE.Vector3(
    target.x + distance * Math.cos(el) * Math.sin(az),
    target.y + distance * Math.sin(el),
    target.z - distance * Math.cos(el) * Math.cos(az),
  );
}

export function createCamera(aspect) {
  return new THREE.PerspectiveCamera(40, aspect, 0.02, 20);
}

export function createControls(camera, domElement) {
  const controls = new OrbitControls(camera, domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.3;
  controls.maxDistance = 3.0;
  // Elevation 10 to 85 degrees is polar angle 5 to 80 degrees from +Y.
  controls.minPolarAngle = (90 - 85) * DEG;
  controls.maxPolarAngle = (90 - 10) * DEG;
  controls.addEventListener('change', () => clampPan(controls));
  resetView(camera, controls);
  return controls;
}

// Keep the target over the table: move target and camera together so the view direction is kept.
function clampPan(controls) {
  const t = controls.target;
  const x = THREE.MathUtils.clamp(t.x, -PAN_LIMIT, PAN_LIMIT);
  const z = THREE.MathUtils.clamp(t.z, -PAN_LIMIT, PAN_LIMIT);
  if (x !== t.x || z !== t.z) {
    controls.object.position.x += x - t.x;
    controls.object.position.z += z - t.z;
    t.x = x;
    t.z = z;
  }
}

export function resetView(camera, controls, view = DEFAULT_VIEW) {
  const target = new THREE.Vector3(...view.target);
  camera.position.copy(orbitPosition(target, view.distance, view.elevationDeg, view.azimuthDeg));
  camera.lookAt(target);
  if (controls) {
    controls.target.copy(target);
    controls.update();
  }
}
