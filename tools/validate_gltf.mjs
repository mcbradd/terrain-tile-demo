// Usage: node tools/validate_gltf.mjs <file.glb> [more.glb ...]
// One file: prints {"errors": n, "warnings": n}; exits 1 on any error (used by preflight PF-04).
// Several files: prints {"<file>": {"errors", "warnings", "infos", "hints"}, ...}; exits 1 on any error or warning.
import { readFileSync } from "node:fs";
import validator from "gltf-validator";

const files = process.argv.slice(2);
if (files.length === 0) {
  console.error("usage: validate_gltf.mjs <file.glb> [more.glb ...]");
  process.exit(2);
}
const counts = {};
for (const file of files) {
  const { numErrors, numWarnings, numInfos, numHints } = (
    await validator.validateBytes(new Uint8Array(readFileSync(file)))
  ).issues;
  counts[file] = { errors: numErrors, warnings: numWarnings, infos: numInfos, hints: numHints };
}
if (files.length === 1) {
  const { errors, warnings } = counts[files[0]];
  console.log(JSON.stringify({ errors, warnings }));
  process.exit(errors === 0 ? 0 : 1);
}
console.log(JSON.stringify(counts));
process.exit(Object.values(counts).some((c) => c.errors || c.warnings) ? 1 : 0);
