#version 300 es
precision highp float;

// Entity fragment stage (SPEC 10.6): Lambert with the terrain light. Output is linear RGB.

uniform vec3 u_baseColor;
uniform vec3 u_lightDir;
uniform float u_additive;

in vec3 v_normal;

out vec4 fragColor;

void main() {
  vec3 n = normalize(v_normal);
  float shadeRel = max(dot(n, u_lightDir), 0.0) / 0.70710678;
  vec3 col;
  if (u_additive < 0.5) {
    col = u_baseColor * (0.35 + 0.65 * min(shadeRel, 1.2));
  } else {
    col = u_baseColor * (0.60 + 0.40 * min(shadeRel, 1.0));
  }
  fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
