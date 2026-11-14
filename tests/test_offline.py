import os
import subprocess
import sys
from pathlib import Path


def test_OFFLINE_network_attempt_raises():
    code = (
        "import socket, tilepipe\n"
        "from tilepipe.offline import OfflineError\n"
        "for f in (lambda: socket.create_connection(('127.0.0.1', 9)),\n"
        "          lambda: socket.getaddrinfo('example.com', 80),\n"
        "          lambda: socket.socket().connect(('127.0.0.1', 9))):\n"
        "    try:\n"
        "        f()\n"
        "    except OfflineError:\n"
        "        continue\n"
        "    raise SystemExit('no raise')\n"
    )
    src = str(Path(__file__).resolve().parents[1] / "src")
    env = {**os.environ, "TILEPIPE_OFFLINE": "1", "PYTHONPATH": src}
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
