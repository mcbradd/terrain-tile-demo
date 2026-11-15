#version 300 es
precision highp float;

// Wireframe debug view (SPEC 13.5): batches redrawn as lines in one color at a fixed opacity.
// Paired with terrain.vert.glsl. Output is linear RGB with straight alpha.

uniform vec3 u_color;
uniform float u_alpha;

out vec4 fragColor;

void main() {
  fragColor = vec4(u_color, u_alpha);
}
