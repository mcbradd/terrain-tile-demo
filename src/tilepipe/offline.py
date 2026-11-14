"""Network guard: with TILEPIPE_OFFLINE=1, any socket connection attempt raises (SPEC 3.3 rule 8)."""
import os
import socket


class OfflineError(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise OfflineError("network access attempted with TILEPIPE_OFFLINE=1")


def install() -> None:
    if os.environ.get("TILEPIPE_OFFLINE") != "1":
        return
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked
