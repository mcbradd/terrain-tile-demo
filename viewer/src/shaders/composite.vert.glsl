#version 300 es
precision highp float;

// Composite vertex stage (SPEC 13.4): one full-screen triangle with corners (-1,-1), (3,-1), (-1,3).

in vec3 position;

out vec2 v_uv;

void main() {
  v_uv = position.xy * 0.5 + 0.5;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
