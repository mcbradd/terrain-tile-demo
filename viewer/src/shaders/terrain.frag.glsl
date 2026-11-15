#version 300 es
// TEXTURE_SAMPLES: 2
precision highp float;

// Terrain fragment stage (SPEC 10.3). Standalone GLSL ES 3.00 with no engine chunks and no includes.
// Output is linear RGB. The composite pass encodes sRGB.

uniform sampler2D u_height;
uniform sampler2D u_nao;
uniform float u_hMin;
uniform float u_hMax;
uniform float u_exag;
uniform float u_extent;
uniform vec2 u_gridOffset;
uniform vec3 u_ramp[4];
uniform float u_rampT[4];
uniform vec3 u_lightDir;
uniform float u_additive;
uniform float u_kDim;
uniform float u_aoFloor;
uniform float u_shadeBase;
uniform float u_shadeGain;
uniform float u_shadeMax;
uniform vec3 u_lineColor;
uniform vec3 u_plinthColor;
uniform float u_alphaMinor;
uniform float u_alphaIndex;
uniform float u_alphaGrid;
uniform float u_interval;
uniform float u_indexEvery;
uniform float u_wMinor;
uniform float u_wIndex;
uniform float u_wGrid;
uniform float u_chunkLod[16];
uniform float u_debugLod;

in vec3 v_tl;

out vec4 fragColor;

// Piecewise linear over the 4 stops, in linear RGB.
vec3 ramp(float t) {
  vec3 c = u_ramp[0];
  for (int i = 0; i < 3; i++) {
    float a = u_rampT[i];
    float b = u_rampT[i + 1];
    if (t >= a) {
      c = mix(u_ramp[i], u_ramp[i + 1], clamp((t - a) / max(b - a, 1e-6), 0.0, 1.0));
    }
  }
  return c;
}

// LOD debug tint (SPEC 13.5), sRGB hex converted to linear RGB.
vec3 lodTint(float k) {
  int i = int(clamp(k + 0.5, 0.0, 4.0));
  if (i == 0) return vec3(0.0273, 0.2051, 0.0319);   // #2E7D32
  if (i == 1) return vec3(0.3419, 0.3372, 0.0176);   // #9E9D24
  if (i == 2) return vec3(0.9473, 0.3916, 0.0185);   // #F9A825
  if (i == 3) return vec3(0.8632, 0.1500, 0.0000);   // #EF6C00
  return vec3(0.5647, 0.0212, 0.0212);               // #C62828
}

void main() {
  vec2  uv   = clamp(v_tl.xz / u_extent, 0.5 / 1024.0, 1.0 - 0.5 / 1024.0);
  vec2  hs   = textureLod(u_height, uv, 0.0).rg;   // level 0 always: contours must not move with view angle
  float h    = u_hMin + (hs.r * 65280.0 + hs.g * 255.0) / 65535.0 * (u_hMax - u_hMin);
  vec4  nao  = texture(u_nao, uv);
  vec2  nxz  = nao.rg * 2.0 - 1.0;
  float ny   = sqrt(max(1.0 - dot(nxz, nxz), 0.0));
  vec3  n    = normalize(vec3(nxz.x * u_exag, ny, nxz.y * u_exag));
  float t    = clamp((h - u_hMin) / (u_hMax - u_hMin), 0.0, 1.0);
  vec3  base = ramp(t);
  float shadeRel = max(dot(n, u_lightDir), 0.0) / 0.70710678;   // flat ground = 1
  vec3  lit  = base * u_kDim * mix(u_aoFloor, 1.0, nao.b)
             * clamp(u_shadeBase + u_shadeGain * shadeRel, 0.0, u_shadeMax);

  // lines: distance in pixels to the nearest line, antialiased, faded when dense
  float c    = h / u_interval;
  float fwC  = fwidth(c);
  float dMin = abs(fract(c - 0.5) - 0.5) / max(fwC, 1e-6);
  float lMin = (1.0 - smoothstep(u_wMinor - 0.5, u_wMinor + 0.5, dMin))
             * (1.0 - smoothstep(0.25, 0.5, fwC));
  float ci   = c / u_indexEvery;
  float fwI  = fwidth(ci);
  float dIdx = abs(fract(ci - 0.5) - 0.5) / max(fwI, 1e-6);
  float lIdx = (1.0 - smoothstep(u_wIndex - 0.5, u_wIndex + 0.5, dIdx))
             * (1.0 - smoothstep(0.25, 0.5, fwI));
  lMin *= (1.0 - lIdx);                      // index line replaces the minor under it
  vec2  g    = (vec2(v_tl.x, -v_tl.z) + u_gridOffset) / 1000.0;
  vec2  fwG  = fwidth(g);
  vec2  dG2  = abs(fract(g - 0.5) - 0.5) / max(fwG, vec2(1e-6));
  float lGrd = (1.0 - smoothstep(u_wGrid - 0.5, u_wGrid + 0.5, min(dG2.x, dG2.y)))
             * (1.0 - smoothstep(0.25, 0.5, max(fwG.x, fwG.y)));

  vec3 col;
  if (u_additive < 0.5) {                    // opaque: lines replace the surface
    col = mix(lit, u_lineColor, u_alphaMinor * lMin);
    col = mix(col, u_lineColor, u_alphaIndex * lIdx);
    col = mix(col, u_lineColor, u_alphaGrid  * lGrd);
  } else {                                   // additive: lines add light
    col = lit + u_lineColor * (u_alphaMinor * lMin + u_alphaIndex * lIdx + u_alphaGrid * lGrd);
  }

  // skirts and plinth: a heightfield surface is never vertical, a skirt always is
  vec3 ng = normalize(cross(dFdx(v_tl), dFdy(v_tl)));
  if (abs(ng.y) < 0.02) col = u_plinthColor;

  // LOD debug view: tint each chunk by its selected LOD
  float chunk = min(floor(v_tl.x / 2560.0), 3.0) + 4.0 * min(floor(v_tl.z / 2560.0), 3.0);
  col = mix(col, lodTint(u_chunkLod[int(max(chunk, 0.0))]), u_debugLod);

  fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);   // linear; the composite pass encodes sRGB
}
