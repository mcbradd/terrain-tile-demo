// Viewer entry point: loading, render path, entities (SPEC 13.1 to 13.4, 13.6).
// three.js supplies the window, loaders, and camera. All shading is the standalone GLSL in shaders/.
// Every URL is relative and same-origin.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { createCamera, createControls, resetView } from './camera.js';
import terrainVert from './shaders/terrain.vert.glsl';
import terrainFrag from './shaders/terrain.frag.glsl';
import entityVert from './shaders/entity.vert.glsl';
import entityFrag from './shaders/entity.frag.glsl';
import compositeVert from './shaders/composite.vert.glsl';
import compositeFrag from './shaders/composite.frag.glsl';
import lineFrag from './shaders/line.frag.glsl';

const FALLBACK_TEXT = 'This demo needs WebGL2 with float render targets. Watch the 3-minute walkthrough instead.';
const LIGHT_DIR = [-0.5, 0.70710678, -0.5]; // TL: light from the northwest, 45 degrees up (10.2)
const ACCENT = '#FF7A1A';
const GROUND_DISC = '#15181C';
const GRADIENT_TOP = '#3A3A3A';
const GRADIENT_BOTTOM = '#1E1E1E';
const TABLE_LIFT = 0.010; // table meters, 6.1
const ANISOTROPY = { mobile_ar: 4, workstation: 8 };

// ---------- small helpers ----------

export function srgbHexToLinear(hex) {
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255].map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
}
const vec3Linear = (hex) => new THREE.Vector3(...srgbHexToLinear(hex));

// The shader files start with `#version 300 es` so they compile on their own. three.js writes that line
// itself for `glslVersion: THREE.GLSL3`, so it is removed here to avoid a duplicate directive.
const glsl3 = (src) => src.replace(/^#version 300 es\r?\n/, '');

function rawMaterial(vertexShader, fragmentShader, uniforms, extra = {}) {
  return new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: glsl3(vertexShader),
    fragmentShader: glsl3(fragmentShader),
    uniforms,
    side: THREE.FrontSide,
    depthTest: true,
    depthWrite: true,
    blending: THREE.NoBlending,
    ...extra,
  });
}

let bytesLoaded = 0;
let bytesExpected = 1;
const progressBar = { el: null };

function showProgress() {
  if (!progressBar.el) {
    const outer = document.getElementById('progress') || document.body.appendChild(document.createElement('div'));
    outer.id = 'progress';
    if (!outer.firstChild) {
      outer.style.cssText = 'position:fixed;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,0.08);z-index:10';
      const bar = outer.appendChild(document.createElement('div'));
      bar.style.cssText = `height:100%;width:0;background:${ACCENT}`;
    }
    progressBar.el = outer;
  }
  progressBar.el.hidden = false;
  progressBar.el.firstChild.style.width = `${Math.min(100, (100 * bytesLoaded) / bytesExpected).toFixed(1)}%`;
}

// Fetch with byte counting for the progress bar (13.2 step 7).
async function fetchBytes(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const parts = [];
  let n = 0;
  const reader = res.body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    n += value.length;
    bytesLoaded += value.length;
    showProgress();
  }
  const out = new Uint8Array(n);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

async function fetchJson(url, optional = false) {
  try {
    return JSON.parse(new TextDecoder().decode(await fetchBytes(url)));
  } catch (e) {
    if (optional) return null;
    throw e;
  }
}

// ---------- support check and fallback (13.4 step 1, 13.10) ----------

// WebGL2 plus a framebuffer-complete RGBA16F target with 4 MSAA samples, and its single-sample resolve texture.
export function supportsFloatTarget(gl) {
  if (!gl || typeof WebGL2RenderingContext === 'undefined' || !(gl instanceof WebGL2RenderingContext)) return false;
  if (!gl.getExtension('EXT_color_buffer_float')) return false;
  if (gl.getParameter(gl.MAX_SAMPLES) < 4) return false;
  const fb = gl.createFramebuffer();
  const rb = gl.createRenderbuffer();
  const tex = gl.createTexture();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.bindRenderbuffer(gl.RENDERBUFFER, rb);
  gl.renderbufferStorageMultisample(gl.RENDERBUFFER, 4, gl.RGBA16F, 4, 4);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.RENDERBUFFER, rb);
  let ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA16F, 4, 4);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  ok = ok && gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE && gl.getError() === gl.NO_ERROR;
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.bindRenderbuffer(gl.RENDERBUFFER, null);
  gl.bindTexture(gl.TEXTURE_2D, null);
  gl.deleteFramebuffer(fb);
  gl.deleteRenderbuffer(rb);
  gl.deleteTexture(tex);
  return ok;
}

async function showFallback(canvas) {
  canvas.remove();
  const box = document.createElement('div');
  box.id = 'fallback';
  box.style.cssText = 'max-width:960px;margin:40px auto;padding:0 16px;color:#E8E6E1;font:15px system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';
  const img = box.appendChild(document.createElement('img'));
  img.src = 'assets/fallback.jpg';
  img.alt = 'Still image of the terrain tile';
  img.style.cssText = 'display:block;width:100%;height:auto';
  const p = box.appendChild(document.createElement('p'));
  p.textContent = FALLBACK_TEXT;
  const cfg = await fetchJson('config.json', true);
  const url = cfg && typeof cfg.video_url === 'string' ? cfg.video_url : '';
  if (/^https?:\/\//.test(url) || /^[\w./-]+$/.test(url)) {
    const a = box.appendChild(document.createElement('a'));
    a.href = url;
    a.textContent = 'Watch the walkthrough';
    a.style.color = ACCENT;
  }
  document.body.appendChild(box);
  viewer.fallback = true;
}

// ---------- textures (13.2 steps 3 and 4) ----------

const BYTES_PER_TEXEL = { RG8_UNORM: 2, RGBA8_UNORM: 4 };
const THREE_FORMAT = { RG8_UNORM: THREE.RGFormat, RGBA8_UNORM: THREE.RGBAFormat };

function makeDataTexture(desc, bytes) {
  const bpt = BYTES_PER_TEXEL[desc.format];
  const mipmaps = [];
  let offset = 0;
  for (let i = 0; i < desc.mip_levels; i++) {
    const width = Math.max(1, desc.width >> i);
    const height = Math.max(1, desc.height >> i);
    const n = width * height * bpt;
    mipmaps.push({ data: bytes.subarray(offset, offset + n), width, height });
    offset += n;
  }
  if (offset !== bytes.length) throw new Error(`${desc.file}: ${bytes.length} bytes, levels declare ${offset}`);
  const tex = new THREE.DataTexture(mipmaps[0].data, desc.width, desc.height, THREE_FORMAT[desc.format],
    THREE.UnsignedByteType);
  tex.mipmaps = mipmaps;
  tex.colorSpace = THREE.NoColorSpace;
  tex.generateMipmaps = false;
  tex.flipY = false;
  tex.unpackAlignment = 1;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  const single = desc.mip_levels === 1;
  tex.minFilter = single ? THREE.LinearFilter : THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.anisotropy = 1;
  tex.needsUpdate = true;
  return tex;
}

// ---------- viewer state ----------

export const viewer = {
  fallback: false,
  tile: null,
  scene: null,
  validation: null,
  looks: {},
  profile: null,
  look: null,
  exaggeration: 1.5,
  toggles: { contours: true, grid: true, entities: true },
  debug: 'none', // none | wireframe | lod
  groundDiscEnabled: true,
  cpu: { height: null, nao: null }, // level 0 copies for the cursor readout
  sceneInfo: { triangles: 0, calls: 0 }, // counts after the scene pass, before the composite
  renderer: null,
  camera: null,
  controls: null,
  ready: null,
  textureBytesLoaded: 0,
  onFrame: null, // optional per-frame hook, called after the composite
};

const U = {
  // terrain uniforms (10.2)
  u_viewProj: { value: new THREE.Matrix4() },
  u_tableFromTL: { value: new THREE.Matrix4() },
  u_height: { value: null },
  u_nao: { value: null },
  u_hMin: { value: 0 },
  u_hMax: { value: 1 },
  u_exag: { value: 1.5 },
  u_extent: { value: 10240.0 },
  u_gridOffset: { value: new THREE.Vector2() },
  u_ramp: { value: [0, 1, 2, 3].map(() => new THREE.Vector3()) },
  u_rampT: { value: [0, 0, 0, 0] },
  u_lightDir: { value: new THREE.Vector3(...LIGHT_DIR) },
  u_additive: { value: 0 },
  u_kDim: { value: 1 },
  u_aoFloor: { value: 0 },
  u_shadeBase: { value: 0 },
  u_shadeGain: { value: 0 },
  u_shadeMax: { value: 0 },
  u_lineColor: { value: new THREE.Vector3() },
  u_plinthColor: { value: new THREE.Vector3() },
  u_alphaMinor: { value: 0 },
  u_alphaIndex: { value: 0 },
  u_alphaGrid: { value: 0 },
  u_interval: { value: 20.0 },
  u_indexEvery: { value: 5.0 },
  u_wMinor: { value: 0.75 },
  u_wIndex: { value: 1.25 },
  u_wGrid: { value: 0.75 },
  u_chunkLod: { value: new Array(16).fill(0) },
  u_debugLod: { value: 0 },
};

const scene = new THREE.Scene();
const terrainGroup = new THREE.Group();
const wireGroup = new THREE.Group();
const entityGroup = new THREE.Group();
scene.add(terrainGroup, wireGroup, entityGroup);
terrainGroup.matrixAutoUpdate = false;
wireGroup.matrixAutoUpdate = false;

let terrainMat;
let wireMat;
let stemMat;
let discMesh;
let stems = null; // { mesh, items: [{ instance, x, z }] }
let instances = []; // { mesh, index, entry, yTL, scale }
let rt;
let compositeScene;
let compositeCam;
let compositeMat;
let loadToken = 0;

function entityMaterial(hex, extra = {}) {
  return rawMaterial(entityVert, entityFrag, {
    u_viewProj: U.u_viewProj,
    u_lightDir: U.u_lightDir,
    u_additive: U.u_additive,
    u_baseColor: { value: vec3Linear(hex) },
  }, extra);
}

// TL to table (6.1): Xt = (x - E/2) / S, Yt = (y - h_min) * V / S + 0.010, Zt = (z - E/2) / S.
function tableFromTL(V) {
  const S = viewer.tile.table.scale;
  const half = viewer.tile.extent_m / 2;
  const hMin = viewer.tile.height.min;
  return new THREE.Matrix4().set(
    1 / S, 0, 0, -half / S,
    0, V / S, 0, -hMin * V / S + TABLE_LIFT,
    0, 0, 1 / S, -half / S,
    0, 0, 0, 1,
  );
}

function tableY(yTL) {
  return (yTL - viewer.tile.height.min) * viewer.exaggeration / viewer.tile.table.scale + TABLE_LIFT;
}

// ---------- look, exaggeration, toggles ----------

function applyUniformsFromLook() {
  const look = viewer.looks[viewer.look];
  const additive = look.mode === 'additive';
  U.u_additive.value = additive ? 1 : 0;
  look.ramp.forEach((stop, i) => {
    U.u_ramp.value[i].set(...srgbHexToLinear(stop.srgb));
    U.u_rampT.value[i] = stop.t;
  });
  U.u_kDim.value = look.k_dim;
  U.u_aoFloor.value = look.ao_floor;
  U.u_shadeBase.value = look.shade_base;
  U.u_shadeGain.value = look.shade_gain;
  U.u_shadeMax.value = look.shade_max;
  U.u_lineColor.value.set(...srgbHexToLinear(look.line_srgb));
  U.u_plinthColor.value.set(...srgbHexToLinear(look.plinth_srgb));
  const c = viewer.toggles.contours ? 1 : 0;
  U.u_alphaMinor.value = look.alpha_minor * c;
  U.u_alphaIndex.value = look.alpha_index * c;
  U.u_alphaGrid.value = look.alpha_grid * (viewer.toggles.grid ? 1 : 0);
  stemMat.uniforms.u_baseColor.value.copy(U.u_lineColor.value);
  compositeMat.uniforms.u_additive.value = additive ? 1 : 0;
  compositeMat.uniforms.u_bgGain.value = additive ? look.bg_gain : 0;
  compositeMat.uniforms.u_displayGain.value = additive ? look.display_gain : 1;
  viewer.renderer.setClearColor(new THREE.Color().setRGB(...srgbHexToLinear(look.clear_srgb),
    THREE.LinearSRGBColorSpace), 1);
  discMesh.visible = !additive && viewer.groundDiscEnabled;
  entityGroup.visible = viewer.toggles.entities;
  U.u_debugLod.value = viewer.debug === 'lod' || viewer.debug === 'both' ? 0.5 : 0; // 'both' is for the tour (13.7)
  wireGroup.visible = viewer.debug === 'wireframe' || viewer.debug === 'both';
}

export function setLook(name) {
  if (!viewer.looks[name]) throw new Error(`unknown look ${name}`);
  viewer.look = name;
  applyUniformsFromLook();
}

export function setToggles(t) {
  Object.assign(viewer.toggles, t);
  applyUniformsFromLook();
}

export function setDebug(mode) {
  viewer.debug = mode;
  applyUniformsFromLook();
}

export function setGroundDisc(on) {
  viewer.groundDiscEnabled = on;
  applyUniformsFromLook();
}

function placeInstances() {
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const S = viewer.tile.table.scale;
  const half = viewer.tile.extent_m / 2;
  const touched = new Set();
  for (const it of instances) {
    const e = it.entry;
    // yaw pi - heading points the model's +Z along the heading (13.6)
    q.setFromAxisAngle(up, Math.PI - THREE.MathUtils.degToRad(e.heading_deg));
    const p = new THREE.Vector3((e.x - half) / S, tableY(it.yTL) + e.hover_table_m, (e.z - half) / S);
    m.compose(p, q, new THREE.Vector3(it.scale, it.scale, it.scale));
    it.mesh.setMatrixAt(it.index, m);
    touched.add(it.mesh);
  }
  for (const mesh of touched) {
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }
}

export function setExaggeration(V) {
  if (!viewer.tile.table.exaggeration_allowed.includes(V)) throw new Error(`exaggeration ${V} not allowed`);
  viewer.exaggeration = V;
  U.u_exag.value = V;
  U.u_tableFromTL.value.copy(tableFromTL(V));
  for (const g of [terrainGroup, wireGroup]) {
    g.matrix.copy(U.u_tableFromTL.value);
    g.matrixWorldNeedsUpdate = true;
    g.updateMatrixWorld(true);
  }
  placeInstances();
}

// ---------- profile loading (13.2 steps 5 to 8, 13.6) ----------

const gltf = new GLTFLoader();

async function loadGeometry(url) {
  const bytes = await fetchBytes(url);
  const res = await gltf.parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
  res.scene.updateMatrixWorld(true);
  // keep the geometry only (13.2 step 5); node transforms are baked in
  let geom = null;
  res.scene.traverse((o) => {
    if (!o.isMesh) return;
    if (!geom) geom = o.geometry.applyMatrix4(o.matrixWorld);
    else o.geometry.dispose();
    [].concat(o.material).forEach((mat) => mat.dispose());
  });
  if (!geom) throw new Error(`${url}: no mesh`);
  return geom;
}

// Dispose the previous profile's batch and entity geometry. Textures are shared and kept (13.2 step 8).
function disposeProfile() {
  for (const g of [terrainGroup, wireGroup]) {
    for (const o of [...g.children]) {
      g.remove(o);
      if (g === terrainGroup) o.geometry.dispose();
    }
  }
  for (const o of [...entityGroup.children]) {
    if (o === discMesh) continue;
    entityGroup.remove(o);
    o.geometry.dispose();
    if (o.material !== stemMat) o.material.dispose();
    o.dispose();
  }
  instances = [];
  stems = null;
}

// One InstancedMesh per entity at the profile's entity LOD (13.2 step 6). A missing entity is skipped.
async function loadEntities(prof) {
  const n = prof.entity_lod;
  const byEntity = new Map();
  for (const entry of viewer.scene.instances) {
    if (!byEntity.has(entry.entity)) byEntity.set(entry.entity, []);
    byEntity.get(entry.entity).push(entry);
  }
  const loaded = await Promise.all(viewer.tile.entities.map(async (id) => {
    try {
      const meta = await fetchJson(`data/entities/${id}/entity.json`);
      const lod = meta.lods.find((l) => l.n === n);
      const geom = await loadGeometry(`data/entities/${id}/${lod.file}`);
      if (!geom.attributes.normal) geom.computeVertexNormals();
      return { id, meta, geom };
    } catch (e) {
      console.warn(`entity ${id} not loaded: ${e.message}`);
      return null;
    }
  }));
  const out = [];
  for (const item of loaded) {
    if (!item) continue;
    const entries = byEntity.get(item.id) || [];
    if (!entries.length) {
      item.geom.dispose();
      continue;
    }
    const mesh = new THREE.InstancedMesh(item.geom, entityMaterial(item.meta.base_color_srgb), entries.length);
    mesh.name = item.id;
    const b = item.meta.bbox_m;
    const dim = Math.max(...b.max.map((v, i) => v - b.min[i]));
    const scale = item.meta.display.table_size_m / dim; // 0.025 / max(bbox dimensions)
    entries.forEach((entry, index) => out.push({ mesh, index, entry, scale, yTL: 0 }));
  }
  return out;
}

// Ground height once per profile load: a downward ray against the loaded batches, kept in TL meters.
function findGroundHeights() {
  const ray = new THREE.Raycaster();
  const S = viewer.tile.table.scale;
  const half = viewer.tile.extent_m / 2;
  const down = new THREE.Vector3(0, -1, 0);
  for (const it of instances) {
    ray.set(new THREE.Vector3((it.entry.x - half) / S, 10, (it.entry.z - half) / S), down);
    const hit = ray.intersectObjects(terrainGroup.children, false)[0];
    const yt = hit ? hit.point.y : TABLE_LIFT;
    it.yTL = (yt - TABLE_LIFT) * S / viewer.exaggeration + viewer.tile.height.min;
  }
}

// One mesh of vertical quads, 0.6 mm wide, ground to token, turned to face the camera each frame (13.6).
function buildStems() {
  const items = instances.filter((it) => it.entry.hover_table_m > 0);
  if (!items.length) return;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(items.length * 12), 3));
  const normals = new Float32Array(items.length * 12);
  for (let i = 1; i < normals.length; i += 3) normals[i] = 1; // up: flat shading in both looks
  g.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  const idx = [];
  items.forEach((_, i) => idx.push(4 * i, 4 * i + 1, 4 * i + 2, 4 * i + 2, 4 * i + 1, 4 * i + 3));
  g.setIndex(idx);
  const mesh = new THREE.InstancedMesh(g, stemMat, 1);
  mesh.setMatrixAt(0, new THREE.Matrix4());
  mesh.frustumCulled = false;
  mesh.name = 'stems';
  entityGroup.add(mesh);
  stems = { mesh, items };
}

function updateStems() {
  if (!stems) return;
  const pos = stems.mesh.geometry.attributes.position;
  const cam = viewer.camera.position;
  const S = viewer.tile.table.scale;
  const half = viewer.tile.extent_m / 2;
  stems.items.forEach((it, i) => {
    const x = (it.entry.x - half) / S;
    const z = (it.entry.z - half) / S;
    const y0 = tableY(it.yTL);
    const y1 = y0 + it.entry.hover_table_m;
    let dx = cam.x - x;
    let dz = cam.z - z;
    const len = Math.hypot(dx, dz) || 1;
    dx = (dx / len) * 0.0003;
    dz = (dz / len) * 0.0003;
    // half width 0.3 mm along the horizontal perpendicular to the view direction
    pos.setXYZ(4 * i, x + dz, y0, z - dx);
    pos.setXYZ(4 * i + 1, x - dz, y0, z + dx);
    pos.setXYZ(4 * i + 2, x + dz, y1, z - dx);
    pos.setXYZ(4 * i + 3, x - dz, y1, z + dx);
  });
  pos.needsUpdate = true;
}

export async function setProfile(name) {
  const prof = viewer.tile.profiles[name];
  if (!prof) throw new Error(`unknown profile ${name}`);
  const token = ++loadToken;
  bytesLoaded = viewer.textureBytesLoaded; // textures are shared and already loaded
  bytesExpected = prof.web_payload_bytes;
  showProgress();
  const aoi = viewer.tile.tile_id;
  const [geoms, ents] = await Promise.all([
    Promise.all(prof.batches.map((b) => loadGeometry(`data/${aoi}/${b.file}`))),
    loadEntities(prof),
  ]);
  const meshes = new Set(ents.map((it) => it.mesh));
  if (token !== loadToken) { // a newer switch started: drop this one
    geoms.forEach((g) => g.dispose());
    meshes.forEach((m) => { m.geometry.dispose(); m.material.dispose(); m.dispose(); });
    return;
  }
  disposeProfile();
  instances = ents;
  meshes.forEach((m) => entityGroup.add(m));

  for (const geom of geoms) {
    const mesh = new THREE.Mesh(geom, terrainMat);
    mesh.name = 'terrain';
    terrainGroup.add(mesh);
    const wire = new THREE.Mesh(geom, wireMat);
    wire.name = 'wire';
    wireGroup.add(wire);
  }
  for (const [chunk, k] of Object.entries(prof.selection)) {
    const [, cx, cz] = chunk.match(/^c(\d+)_(\d+)$/).map(Number);
    U.u_chunkLod.value[cz * 4 + cx] = k;
  }
  const maxAniso = viewer.renderer.capabilities.getMaxAnisotropy();
  const nao = U.u_nao.value;
  const aniso = Math.min(ANISOTROPY[name] ?? 4, maxAniso);
  if (nao.anisotropy !== aniso) {
    nao.anisotropy = aniso;
    nao.needsUpdate = true;
  }
  viewer.profile = name;
  setExaggeration(viewer.exaggeration);
  findGroundHeights();
  placeInstances();
  buildStems();
  applyUniformsFromLook();
  progressBar.el.hidden = true;
}

// The [look] default of profiles/<name>.toml. tile.json does not carry it, so it is mirrored here and
// tests/test_viewer.py checks that this table equals the profile files (Deviation D-08).
export const PROFILE_LOOK = { workstation: 'opaque', mobile_ar: 'additive' };

// ---------- render path (13.4) ----------

function resize() {
  const r = viewer.renderer;
  r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  r.setSize(window.innerWidth, window.innerHeight);
  const size = r.getDrawingBufferSize(new THREE.Vector2());
  rt.setSize(size.x, size.y);
  compositeMat.uniforms.u_viewSize.value.copy(size);
  viewer.camera.aspect = window.innerWidth / Math.max(1, window.innerHeight);
  viewer.camera.updateProjectionMatrix();
}

function frame() {
  const r = viewer.renderer;
  const cam = viewer.camera;
  viewer.controls.update();
  cam.updateMatrixWorld();
  U.u_viewProj.value.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
  updateStems();
  r.info.reset();
  r.setRenderTarget(rt);
  r.clear(true, true, false);
  r.render(scene, cam);
  viewer.sceneInfo = { triangles: r.info.render.triangles, calls: r.info.render.calls };
  r.setRenderTarget(null);
  r.render(compositeScene, compositeCam);
  if (viewer.onFrame) viewer.onFrame();
}

async function loadRoom() {
  try {
    const res = await fetch('assets/room.jpg');
    if (!res.ok) return;
    const bmp = await createImageBitmap(await res.blob(), { imageOrientation: 'flipY' });
    const tex = new THREE.Texture(bmp);
    tex.colorSpace = THREE.SRGBColorSpace; // decoded to linear by the sampler
    tex.flipY = false;
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    compositeMat.uniforms.u_bg.value = tex;
    compositeMat.uniforms.u_bgSize.value.set(bmp.width, bmp.height);
    compositeMat.uniforms.u_hasBg.value = 1;
  } catch (e) {
    console.warn(`room.jpg not used: ${e.message}`);
  }
}

function buildPasses() {
  const ok = viewer.renderer.getDrawingBufferSize(new THREE.Vector2());
  rt = new THREE.WebGLRenderTarget(ok.x, ok.y, {
    type: THREE.HalfFloatType,
    format: THREE.RGBAFormat,
    samples: 4,
    depthBuffer: true,
    stencilBuffer: false,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    generateMipmaps: false,
  });
  rt.texture.colorSpace = THREE.LinearSRGBColorSpace;

  const tri = new THREE.BufferGeometry();
  tri.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
  compositeMat = rawMaterial(compositeVert, compositeFrag, {
    u_scene: { value: rt.texture },
    u_bg: { value: null },
    u_additive: { value: 0 },
    u_hasBg: { value: 0 },
    u_bgGain: { value: 0 },
    u_displayGain: { value: 1 },
    u_viewSize: { value: new THREE.Vector2(1, 1) },
    u_bgSize: { value: new THREE.Vector2(1, 1) },
    u_gradTop: { value: vec3Linear(GRADIENT_TOP) },
    u_gradBottom: { value: vec3Linear(GRADIENT_BOTTOM) },
  }, { depthTest: false, depthWrite: false });
  const quad = new THREE.Mesh(tri, compositeMat);
  quad.frustumCulled = false;
  compositeScene = new THREE.Scene();
  compositeScene.add(quad);
  compositeCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  // polygon offset pushes the surface back so the wireframe lines win the depth test
  terrainMat = rawMaterial(terrainVert, terrainFrag, U, {
    polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
  });
  wireMat = rawMaterial(terrainVert, lineFrag, {
    u_viewProj: U.u_viewProj,
    u_tableFromTL: U.u_tableFromTL,
    u_color: { value: vec3Linear(ACCENT) },
    u_alpha: { value: 0.35 },
  }, { wireframe: true, transparent: true, blending: THREE.NormalBlending, depthWrite: false });
  stemMat = entityMaterial('#000000', { side: THREE.DoubleSide });

  // Ground disc, opaque look only (13.3): flat, normal up, so the entity shader returns its color unchanged.
  const disc = new THREE.CircleGeometry(1.5, 96).rotateX(-Math.PI / 2);
  discMesh = new THREE.InstancedMesh(disc, entityMaterial(GROUND_DISC), 1);
  discMesh.setMatrixAt(0, new THREE.Matrix4());
  discMesh.name = 'ground_disc';
  discMesh.frustumCulled = false;
  discMesh.renderOrder = -1;
  scene.add(discMesh);
}

// ---------- boot (13.2) ----------

function chooseProfile(profiles) {
  const asked = new URLSearchParams(location.search).get('profile');
  if (asked && profiles[asked]) return asked;
  const fine = window.matchMedia('(pointer: fine)').matches && window.innerWidth >= 1024;
  return fine ? 'workstation' : 'mobile_ar';
}

async function boot() {
  const canvas = document.getElementById('view') || document.body.appendChild(document.createElement('canvas'));
  canvas.id = 'view';
  canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;display:block';
  const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, depth: true, stencil: false,
    powerPreference: 'high-performance' });
  if (!supportsFloatTarget(gl)) {
    await showFallback(canvas);
    return;
  }
  const renderer = new THREE.WebGLRenderer({ canvas, context: gl });
  // Every shader here is raw and writes linear color; sRGB encoding is the composite pass alone (13.4).
  // A linear output space also keeps three.js from encoding the clear color.
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.autoClear = false;
  renderer.info.autoReset = false;
  viewer.renderer = renderer;
  viewer.camera = createCamera(window.innerWidth / Math.max(1, window.innerHeight));
  viewer.controls = createControls(viewer.camera, canvas);
  buildPasses();
  resize();
  window.addEventListener('resize', resize);

  // The AOI comes from data only (17.14): `?aoi=`, else the `aoi` key of the site's config.json.
  const cfg = await fetchJson('config.json', true);
  const aoi = new URLSearchParams(location.search).get('aoi') || cfg?.aoi;
  if (!aoi) throw new Error('no AOI: add ?aoi=<id> to the URL or "aoi" to config.json');
  if (!/^[a-z0-9_]+$/.test(aoi)) throw new Error(`bad aoi ${aoi}`);
  const [tile, sceneDoc, validation, opaque, additive] = await Promise.all([
    fetchJson(`data/${aoi}/tile.json`),
    fetchJson(`data/${aoi}/scene.json`),
    fetchJson(`data/${aoi}/validation.json`, true),
    fetchJson('look/opaque.json'),
    fetchJson('look/additive.json'),
  ]);
  Object.assign(viewer, { tile, scene: sceneDoc, validation, looks: { opaque, additive } });
  viewer.exaggeration = tile.table.exaggeration_default;

  const name = chooseProfile(tile.profiles);
  bytesExpected = tile.profiles[name].web_payload_bytes;
  const tex = {};
  await Promise.all(tile.textures.map(async (desc) => {
    const bytes = await fetchBytes(`data/${aoi}/${desc.file}`);
    tex[desc.id] = makeDataTexture(desc, bytes);
    viewer.cpu[desc.id] = { data: bytes.subarray(0, desc.width * desc.height * BYTES_PER_TEXEL[desc.format]),
      width: desc.width, height: desc.height };
  }));
  viewer.textureBytesLoaded = bytesLoaded;
  U.u_height.value = tex.height;
  U.u_nao.value = tex.nao;
  U.u_hMin.value = tile.height.min;
  U.u_hMax.value = tile.height.max;
  U.u_extent.value = tile.extent_m;
  U.u_gridOffset.value.set(tile.origin.E0 % 1000, tile.origin.N_top % 1000);
  if (cfg?.room) loadRoom(); // `tilepipe site` sets `room` only when it shipped assets/room.jpg, so no 404

  viewer.look = viewer.looks[PROFILE_LOOK[name]] ? PROFILE_LOOK[name] : 'opaque'; // 13.2 step 2
  renderer.setAnimationLoop(frame);
  await setProfile(name);
}

Object.assign(viewer, { setProfile, setLook, setExaggeration, setToggles, setDebug, setGroundDisc,
  resetCamera: () => resetView(viewer.camera, viewer.controls) });
window.tilepipe = viewer;
viewer.ready = boot().catch((e) => {
  console.error(e);
  const p = document.body.appendChild(document.createElement('p'));
  p.id = 'load-error';
  p.style.cssText = 'position:fixed;top:40%;width:100%;text-align:center;color:#FF6B6B;font:15px system-ui,sans-serif';
  p.textContent = `Load failed: ${e.message}`;
  throw e;
});
