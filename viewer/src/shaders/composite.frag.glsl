#version 300 es
precision highp float;

// Composite pass (SPEC 13.4). Opaque: out = srgb_encode(scene).
// Additive: out = srgb_encode(bg * bg_gain + scene * display_gain). No tone mapping.

uniform sampler2D u_scene;
uniform sampler2D u_bg;          // room photo, decoded to linear by the sampler
uniform float u_additive;
uniform float u_hasBg;           // 1.0 when the room photo is loaded
uniform float u_bgGain;
uniform float u_displayGain;
uniform vec2 u_viewSize;         // drawing buffer size in pixels
uniform vec2 u_bgSize;           // room photo size in pixels
uniform vec3 u_gradTop;          // linear RGB
uniform vec3 u_gradBottom;       // linear RGB

in vec2 v_uv;

out vec4 fragColor;

vec3 srgb_encode(vec3 c) {
  c = clamp(c, 0.0, 1.0);
  vec3 lo = c * 12.92;
  vec3 hi = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
  return mix(lo, hi, step(vec3(0.0031308), c));
}

void main() {
  vec3 col = texture(u_scene, v_uv).rgb;
  if (u_additive > 0.5) {
    vec3 bg = mix(u_gradBottom, u_gradTop, v_uv.y);
    if (u_hasBg > 0.5) {
      // cover fit: scale the photo to fill the view, crop the overflow, keep it centered
      float s = max(u_viewSize.x / u_bgSize.x, u_viewSize.y / u_bgSize.y);
      vec2 uvBg = (v_uv - 0.5) * u_viewSize / (u_bgSize * s) + 0.5;
      bg = texture(u_bg, uvBg).rgb;
    }
    col = bg * u_bgGain + col * u_displayGain;
  }
  fragColor = vec4(srgb_encode(col), 1.0);
}
