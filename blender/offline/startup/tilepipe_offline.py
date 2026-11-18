"""Network guard for headless Blender (SPEC 3.3 rules 4 and 8). Standard library and bpy only.

offline.py sets BLENDER_SYSTEM_SCRIPTS to `blender/offline` when TILEPIPE_OFFLINE=1, so Blender loads this startup
module before the `--python` script, also under `--factory-startup`. It checks that `--offline-mode` took effect and
ends Blender with exit 1 on any socket connection. It exits instead of raising so no script can swallow it.
"""
import os
import socket
import sys

import bpy


def _blocked(*args, **kwargs):
    sys.stderr.write("tilepipe offline: network access attempted with TILEPIPE_OFFLINE=1\n")
    sys.stderr.flush()
    os._exit(1)


if os.environ.get("TILEPIPE_OFFLINE") == "1":
    if bpy.app.online_access:
        sys.stderr.write("tilepipe offline: Blender was started without --offline-mode\n")
        sys.stderr.flush()
        os._exit(1)
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked


def register():
    pass


def unregister():
    pass
