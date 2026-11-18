// Network guard for node child processes (SPEC 3.3 rule 8). offline.py puts `--import=<this file>` in NODE_OPTIONS
// when TILEPIPE_OFFLINE=1, so every node process tilepipe starts loads it first. Any socket connect, DNS lookup,
// fetch, or WebSocket ends the process with exit 1. It exits instead of throwing so no caller can swallow it.
import dns from "node:dns";
import net from "node:net";

function blocked() {
  process.stderr.write("tilepipe offline: network access attempted with TILEPIPE_OFFLINE=1\n");
  process.exit(1);
}

net.Socket.prototype.connect = blocked;   // net.connect, http, https, tls, and fetch all reach this
for (const api of [dns, dns.promises]) {
  for (const name of ["lookup", "lookupService", "resolve", "resolve4", "resolve6", "resolveAny"]) {
    api[name] = blocked;
  }
}
globalThis.fetch = blocked;
globalThis.WebSocket = blocked;
