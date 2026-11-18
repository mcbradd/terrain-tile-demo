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


def test_OFFLINE_node_child_exits_on_network():
    """offline.offline() puts the node guard in NODE_OPTIONS; a node child that connects exits 1."""
    from tilepipe import offline
    probe = "require('net').connect(9, '127.0.0.1').on('error', () => {})"
    with offline.offline():
        r = subprocess.run(["node", "-e", probe], capture_output=True, text=True)
        quiet = subprocess.run(["node", "-e", "process.exit(0)"], capture_output=True, text=True)
    assert r.returncode == 1 and "TILEPIPE_OFFLINE" in r.stderr, r.stderr
    assert quiet.returncode == 0, quiet.stderr
    assert "offline_guard" not in os.environ.get("NODE_OPTIONS", ""), "environment restored on exit"


def test_preflight_writes_nonempty_log(tmp_path):
    """3.3 rule 7: preflight's probe subprocesses land in build/logs/preflight.log."""
    from tilepipe import cli
    cli.preflight(tmp_path)
    log = tmp_path / "build" / "logs" / "preflight.log"
    assert log.exists() and "exit " in log.read_text(encoding="utf-8")
