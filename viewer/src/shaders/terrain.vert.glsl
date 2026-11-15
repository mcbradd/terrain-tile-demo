#version 300 es
precision highp float;

// Terrain vertex stage (SPEC 10.2). Input positions are tile-local (TL) meters.

uniform mat4 u_viewProj;
uniform mat4 u_tableFromTL;

in vec3 position;

out vec3 v_tl;

void main() {
  v_tl = position;
  gl_Position = u_viewProj * u_tableFromTL * vec4(position, 1.0);
}
