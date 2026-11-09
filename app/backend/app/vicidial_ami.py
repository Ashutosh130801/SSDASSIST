"""Hang up a ViciDial call directly on Asterisk (AMI) — the fallback when the Agent API can't.

Why it's needed: ViciDial's Agent API `external_hangup` only sets a flag. The agent's ViciDial
browser screen picks it up on its next refresh and hangs up ONLY when it counts the customer as
"live" (the call is answered). A manual dial that is still RINGING ignores it, and a ViciDial
screen in a throttled background tab can act late. AMI ends the customer's channel at once.

The customer's channel carries the ViciDial call id (e.g. M1109123456000012345) as its caller-id
name, so only that exact channel is hung up — never the agent's own phone.
Settings (Connections → ViciDial): AMI host, port (5038), user, secret — from /etc/asterisk/manager.conf
(the "cron" user ViciDial itself uses works, or create a dedicated one limited to the RecoverIQ server IP).
"""
from __future__ import annotations

import socket

_transport = None          # tests: fn(host, port, user, secret, call_id) -> list[str] (channels hung up)


class AmiError(ValueError):
    pass


def configured(conn) -> bool:
    c = conn.capabilities or {}
    return bool(c.get("ami_host") and c.get("ami_user") and c.get("ami_secret"))


def _read_until(sock, marker: bytes, limit=2_000_000) -> bytes:
    buf = b""
    while marker not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            break
    return buf


def _blocks(raw: bytes) -> list[dict]:
    out = []
    for blk in raw.decode("utf-8", "replace").split("\r\n\r\n"):
        d = {}
        for line in blk.split("\r\n"):
            if ": " in line:
                k, v = line.split(": ", 1)
                d[k.strip()] = v.strip()
        if d:
            out.append(d)
    return out


def hangup_call(conn, call_id: str, timeout: float = 5.0) -> list[str]:
    """Hang up every Asterisk channel belonging to this ViciDial call id. Returns the channels ended."""
    call_id = (call_id or "").strip()
    if len(call_id) < 6:
        raise AmiError("No ViciDial call id to hang up.")
    c = conn.capabilities or {}
    host, port = c.get("ami_host"), int(c.get("ami_port") or 5038)
    user, secret = c.get("ami_user"), c.get("ami_secret")
    if _transport:
        return _transport(host, port, user, secret, call_id)
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        raise AmiError("Cannot reach Asterisk manager (AMI) — check AMI host/port and that the RecoverIQ server is allowed in manager.conf.")
    try:
        s.settimeout(timeout)
        _read_until(s, b"\r\n")                                   # banner
        s.sendall(f"Action: Login\r\nUsername: {user}\r\nSecret: {secret}\r\nEvents: off\r\n\r\n".encode())
        if b"Success" not in _read_until(s, b"\r\n\r\n"):
            raise AmiError("Asterisk manager (AMI) login failed — check the AMI user / secret.")
        s.sendall(b"Action: CoreShowChannels\r\nActionID: riq1\r\n\r\n")
        raw = _read_until(s, b"CoreShowChannelsComplete")
        chans = []
        for b in _blocks(raw):
            if b.get("Event") != "CoreShowChannel":
                continue
            ids = (b.get("CallerIDName", ""), b.get("ConnectedLineName", ""), b.get("AccountCode", ""))
            if call_id in ids and b.get("Channel"):
                chans.append(b["Channel"])
        done = []
        for ch in dict.fromkeys(chans):
            s.sendall(f"Action: Hangup\r\nChannel: {ch}\r\n\r\n".encode())
            if b"Success" in _read_until(s, b"\r\n\r\n"):
                done.append(ch)
        s.sendall(b"Action: Logoff\r\n\r\n")
        return done
    except socket.timeout:
        raise AmiError("Asterisk manager (AMI) did not answer in time.")
    finally:
        try:
            s.close()
        except OSError:
            pass
