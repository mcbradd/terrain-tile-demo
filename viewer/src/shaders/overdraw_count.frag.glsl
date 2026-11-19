#version 300 es
precision highp float;

// Overdraw count pass (P1.3). Paired with terrain.vert.glsl or entity.vert.glsl. Depth test off and additive
// blending into an 8-bit target, so each rasterized fragment adds exactly 1 / 255 to red: one count per fragment.

out vec4 fragColor;

void main() {
  fragColor = vec4(1.0 / 255.0, 0.0, 0.0, 0.0);
}
