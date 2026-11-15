#version 300 es
precision highp float;

// Entity vertex stage (SPEC 10.6, 13.6). One instance matrix per token: table position, yaw, uniform scale.

uniform mat4 u_viewProj;

in vec3 position;
in vec3 normal;
in mat4 instanceMatrix;

out vec3 v_normal;

void main() {
  v_normal = mat3(instanceMatrix) * normal;   // uniform scale, so no inverse transpose is needed
  gl_Position = u_viewProj * instanceMatrix * vec4(position, 1.0);
}
