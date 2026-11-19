#version 300 es
precision highp float;

// Overdraw debug view (P1.3). Paired with composite.vert.glsl. Reads the count target and writes a heat ramp.
// The stop colors are sRGB and written as is; the HUD legend uses the same hex values.

uniform sampler2D u_count;   // red = fragments / 255, nearest filter

in vec2 v_uv;

out vec4 fragColor;

const float STOP_N[6] = float[6](1.0, 2.0, 3.0, 4.0, 6.0, 8.0);
const vec3 STOP_C[6] = vec3[6](
  vec3(0.1412, 0.2510, 0.5412),   // 1   #24408A
  vec3(0.1647, 0.6157, 0.5608),   // 2   #2A9D8F
  vec3(0.5412, 0.6941, 0.4902),   // 3   #8AB17D
  vec3(0.9137, 0.7686, 0.4157),   // 4   #E9C46A
  vec3(0.9059, 0.4353, 0.3176),   // 6   #E76F51
  vec3(1.0, 1.0, 1.0));           // 8+  #FFFFFF

void main() {
  float n = floor(texture(u_count, v_uv).r * 255.0 + 0.5);
  vec3 col = vec3(0.0549, 0.0627, 0.0745);   // 0: nothing drawn, #0E1013
  if (n >= 1.0) {
    col = STOP_C[0];
    for (int i = 0; i < 5; i++) {
      if (n >= STOP_N[i]) col = mix(STOP_C[i], STOP_C[i + 1], clamp((n - STOP_N[i]) / (STOP_N[i + 1] - STOP_N[i]), 0.0, 1.0));
    }
  }
  fragColor = vec4(col, 1.0);
}
