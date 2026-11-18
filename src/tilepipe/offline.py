"""Network guard (SPEC 3.3 rule 8). With TILEPIPE_OFFLINE=1 any socket connection attempt in tilepipe raises.

The setting also reaches every child process through the environment: node loads `offline_guard.mjs` through
NODE_OPTIONS, and headless Blender, already started with `--offline-mode`, loads
`blender/offline/startup/tilepipe_offline.py` through BLENDER_SYSTEM_SCRIPTS. Both end the child with exit 1 on a
network attempt, so the step that ran it fails.
"""
import contextlib
import os
import socket
from pathlib import Path

NODE_GUARD = Path(__file__).resolve().with_name("offline_guard.mjs")
BLENDER_GUARD = Path(__file__).resolve().parents[2] / "blender" / "offline"
_METHODS = ("connect", "connect_ex")
_FUNCS = ("create_connection", "getaddrinfo", "gethostbyname")
_ENV = ("TILEPIPE_OFFLINE", "NODE_OPTIONS", "BLENDER_SYSTEM_SCRIPTS")


class OfflineError(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise OfflineError("network access attempted with TILEPIPE_OFFLINE=1")


def install() -> None:
    if os.environ.get("TILEPIPE_OFFLINE") != "1":
        return
    for n in _METHODS:
        setattr(socket.socket, n, _blocked)
    for n in _FUNCS:
        setattr(socket, n, _blocked)
    opt = f"--import={NODE_GUARD.as_uri()}"   # a file URL has no spaces, so NODE_OPTIONS needs no quoting
    node_options = os.environ.get("NODE_OPTIONS", "")
    if opt not in node_options:
        os.environ["NODE_OPTIONS"] = f"{node_options} {opt}".strip()
    os.environ["BLENDER_SYSTEM_SCRIPTS"] = str(BLENDER_GUARD)


@contextlib.contextmanager
def offline():
    """TILEPIPE_OFFLINE=1 and install() for the duration; sockets and environment are restored on exit."""
    saved = ({n: getattr(socket.socket, n) for n in _METHODS}, {n: getattr(socket, n) for n in _FUNCS},
             {k: os.environ.get(k) for k in _ENV})
    os.environ["TILEPIPE_OFFLINE"] = "1"
    install()
    try:
        yield
    finally:
        for n, f in saved[0].items():
            setattr(socket.socket, n, f)
        for n, f in saved[1].items():
            setattr(socket, n, f)
        for k, v in saved[2].items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
