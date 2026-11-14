"""Rebuild the committed launcher wheel without network or build backend: python tools/launcher/build_wheel.py"""
import base64
import hashlib
import zipfile
from pathlib import Path

here = Path(__file__).parent
name, ver = "tilepipe_launcher", "0.1.0"
di = f"{name}-{ver}.dist-info"
files = {
    f"{name}/__init__.py": (here / "src" / name / "__init__.py").read_bytes(),
    f"{di}/METADATA": f"Metadata-Version: 2.1\nName: tilepipe-launcher\nVersion: {ver}\nRequires-Python: ==3.12.*\n".encode(),
    f"{di}/WHEEL": b"Wheel-Version: 1.0\nGenerator: build_wheel.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    f"{di}/entry_points.txt": b"[console_scripts]\ntilepipe = tilepipe_launcher:main\n",
}
record = "".join(
    f"{p},sha256={base64.urlsafe_b64encode(hashlib.sha256(d).digest()).rstrip(b'=').decode()},{len(d)}\n"
    for p, d in files.items()
) + f"{di}/RECORD,,\n"
files[f"{di}/RECORD"] = record.encode()
out = here / "dist" / f"{name}-{ver}-py3-none-any.whl"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p, d in files.items():
        z.writestr(zipfile.ZipInfo(p, (1980, 1, 1, 0, 0, 0)), d)
print(out)
