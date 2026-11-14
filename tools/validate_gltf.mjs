// Usage: node tools/validate_gltf.mjs <file.glb>. Prints error and warning counts; exits 1 on any error.
import { readFileSync } from "node:fs";
import validator from "gltf-validator";

const file = process.argv[2];
if (!file) {
  console.error("usage: validate_gltf.mjs <file.glb>");
  process.exit(2);
}
const report = await validator.validateBytes(new Uint8Array(readFileSync(file)));
const { numErrors, numWarnings } = report.issues;
console.log(JSON.stringify({ errors: numErrors, warnings: numWarnings }));
process.exit(numErrors === 0 ? 0 : 1);
