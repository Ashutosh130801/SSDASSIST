"""Integration layer — connect RecoverIQ to the standalone Autodialer (and later the AI-Voice
product). Two directions:

  • Admin/HO manage connections and trigger click-to-call (auth: normal JWT).
  • The dialer pulls call queues and pushes call/PTP events back (auth: X-Integration-Key,
    matched against an enabled DialerConnection.api_key).

All panels/actions on the RecoverIQ side are optional — they only light up when a dialer is
connected and healthy. Nothing here changes core behaviour when no dialer exists.
"""
from decimal import Decimal
from datetime import datetime, timezone, time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Body
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user, require_roles
from .. import audit

router = APIRouter(prefix="/api/integration", tags=["integration"])

ADMIN_ROLES = ("admin", "headoffice")
PAY_DISPOSITIONS = ("PAYMENT", "PAID")


def _mask(k: str) -> str:
    if not k:
        return ""
    return (k[:4] + "…" + k[-2:]) if len(k) > 7 else "••••"


def _conn_out(c: models.DialerConnection) -> dict:
    caps = dict(c.capabilities or {})
    # Never leak the ViciDial API / SFTP passwords; report only whether they're set.
    if "vici_pass" in caps:
        caps["vici_pass_set"] = bool(caps.pop("vici_pass"))
    if "sftp_pass" in caps:
        caps["sftp_pass_set"] = bool(caps.pop("sftp_pass"))
    return {"id": c.id, "kind": c.kind, "name": c.name, "base_url": c.base_url,
            "api_key_masked": _mask(c.api_key or ""), "branch": c.branch,
            "enabled": bool(c.enabled), "status": c.status,
            "capabilities": caps,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None}


def _dialer_auth(x_integration_key: str = Header(None), db: Session = Depends(get_db)) -> models.DialerConnection:
    """Authenticate an inbound request FROM a connected dialer via its shared key."""
    if not x_integration_key:
        raise HTTPException(status_code=401, detail="Missing X-Integration-Key")
    conn = (db.query(models.DialerConnection)
            .filter(models.DialerConnection.api_key == x_integration_key,
                    models.DialerConnection.enabled.is_(True)).first())
    if not conn:
        raise HTTPException(status_code=401, detail="Invalid integration key")
    conn.last_seen = datetime.now(timezone.utc)
    db.commit()
    return conn


# ============================================================ admin: connections
@router.get("/status")
def integration_status(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Lightweight check the frontend polls to decide whether to show dialer widgets."""
    conns = db.query(models.DialerConnection).filter(models.DialerConnection.enabled.is_(True)).all()
    dialers = [c for c in conns if c.kind == "dialer" and c.status == "ok"]
    vicis = [c for c in conns if c.kind == "vicidial"]        # enabled is enough; status set on first call/test
    # 'dialer.connected' drives the in-app Call button — true if EITHER a standalone dialer or a
    # ViciDial is connected, so callers get the button in both setups.
    return {"dialer": {"connected": bool(dialers) or bool(vicis), "count": len(dialers) + len(vicis),
                       "names": [c.name for c in dialers] + [c.name for c in vicis]},
            "vicidial": {"connected": bool(vicis), "count": len(vicis),
                         "names": [c.name for c in vicis]},
            "aivoice": {"connected": any(c.kind == "aivoice" and c.status == "ok" for c in conns)}}


@router.get("/connections")
def list_connections(db: Session = Depends(get_db), user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    rows = db.query(models.DialerConnection).order_by(models.DialerConnection.id).all()
    return {"connections": [_conn_out(c) for c in rows]}


@router.post("/connections")
def add_connection(body: dict = Body(...), db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    name = (body.get("name") or "").strip()
    base_url = (body.get("base_url") or "").strip().rstrip("/")
    api_key = (body.get("api_key") or "").strip()
    if not (name and base_url and api_key):
        raise HTTPException(status_code=400, detail="name, base_url and api_key are required")
    c = models.DialerConnection(kind=(body.get("kind") or "dialer"), name=name, base_url=base_url,
                                api_key=api_key, branch=(body.get("branch") or None), enabled=True,
                                status="unknown")
    db.add(c)
    db.commit(); db.refresh(c)
    audit.record(db, user, "integration", None, entity_type="integration",
                 detail=f"Added dialer connection '{name}' ({base_url})")
    db.commit()
    return _conn_out(c)


@router.post("/connections/{cid}/test")
def test_connection(cid: int, db: Session = Depends(get_db),
                    user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    c = db.query(models.DialerConnection).filter(models.DialerConnection.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connection not found")
    ok, caps = False, None
    try:
        headers = {"Authorization": f"Bearer {c.api_key}", "X-Integration-Key": c.api_key}
        with httpx.Client(timeout=6.0, verify=False) as cl:
            h = cl.get(f"{c.base_url}/integration/health", headers=headers)
            ok = h.status_code < 400
            if ok:
                try:
                    caps = cl.get(f"{c.base_url}/integration/capabilities", headers=headers).json()
                except Exception:
                    caps = None
    except Exception as e:
        c.status = "down"; db.commit()
        return {"ok": False, "status": "down", "detail": str(e)[:200]}
    c.status = "ok" if ok else "down"
    c.capabilities = caps
    c.last_seen = datetime.now(timezone.utc)
    db.commit()
    return {"ok": ok, "status": c.status, "capabilities": caps}


@router.post("/connections/{cid}/toggle")
def toggle_connection(cid: int, db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    c = db.query(models.DialerConnection).filter(models.DialerConnection.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connection not found")
    c.enabled = not bool(c.enabled)
    db.commit()
    return _conn_out(c)


@router.delete("/connections/{cid}")
def delete_connection(cid: int, db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    c = db.query(models.DialerConnection).filter(models.DialerConnection.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(c); db.commit()
    return {"ok": True}


# ============================================================ click-to-call (RecoverIQ → dialer)
def _pick_dialer(db: Session, branch: str | None) -> models.DialerConnection | None:
    q = (db.query(models.DialerConnection)
         .filter(models.DialerConnection.kind == "dialer",
                 models.DialerConnection.enabled.is_(True),
                 models.DialerConnection.status == "ok"))
    rows = q.all()
    if branch:
        for c in rows:
            if (c.branch or "").strip().lower() == (branch or "").strip().lower():
                return c
    return rows[0] if rows else None


def _pick_vici(db: Session, branch: str | None) -> models.DialerConnection | None:
    rows = (db.query(models.DialerConnection)
            .filter(models.DialerConnection.kind == "vicidial",
                    models.DialerConnection.enabled.is_(True)).all())
    if branch:
        for c in rows:
            if (c.branch or "").strip().lower() == (branch or "").strip().lower():
                return c
    return rows[0] if rows else None


def _vici_agent_user(conn: models.DialerConnection, user: models.User) -> str | None:
    """Resolve a RecoverIQ user to their ViciDial agent user id. Uses the connection's agent_map
    (emp_code → vici user); falls back to the emp_code itself when shops set vici user = emp code."""
    caps = conn.capabilities or {}
    amap = {str(k).strip().upper(): str(v).strip() for k, v in (caps.get("agent_map") or {}).items()}
    code = (user.emp_code or "").strip().upper()
    return amap.get(code) or (user.emp_code or None)


@router.post("/click-to-call")
def click_to_call(body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """Ask the connected dialer to place a call: ring the agent, bridge to the customer.
    Prefers a connected ViciDial (agc/api.php external_dial on the agent's live session); falls
    back to a standalone RecoverIQ dialer if that's what's connected instead."""
    case = db.query(models.Case).filter(models.Case.id == int(body.get("case_id") or 0)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.phone:
        raise HTTPException(status_code=400, detail="This case has no phone number")
    # ── ViciDial path (existing office dialer) ────────────────────────────────────
    vici = _pick_vici(db, case.branch)
    if vici:
        caps = vici.capabilities or {}
        agent_user = _vici_agent_user(vici, user)
        if not agent_user:
            raise HTTPException(status_code=400,
                                detail="No ViciDial agent id mapped for your account. Ask admin to map it in Connections.")
        phone = "".join(ch for ch in str(case.phone) if ch.isdigit())[-12:]
        params = {
            "source": caps.get("source") or "recoveriq",
            "user": caps.get("vici_user") or "",
            "pass": caps.get("vici_pass") or "",
            "agent_user": agent_user,
            "function": "external_dial",
            "value": phone,
            "phone_code": str(caps.get("phone_code") or "91"),
            "search": "YES", "preview": "NO", "focus": "YES",
            "vendor_lead_code": str(case.id),
        }
        try:
            with httpx.Client(timeout=8.0, verify=False) as cl:
                r = cl.get(f"{vici.base_url}/agc/api.php", params=params)
                txt = (r.text or "").strip()
            vici.last_seen = datetime.now(timezone.utc)
            vici.status = "ok" if txt.upper().startswith("SUCCESS") else vici.status
            db.commit()
            if not txt.upper().startswith("SUCCESS"):
                # Most common cause: the agent isn't logged into the ViciDial agent screen.
                raise HTTPException(status_code=502,
                                    detail=f"ViciDial: {txt[:180] or 'no response'} — make sure the agent is logged into the ViciDial agent screen with their phone registered.")
            return {"ok": True, "dialer": vici.name, "via": "vicidial", "agent_user": agent_user, "detail": txt[:200]}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not reach ViciDial: {str(e)[:160]}")
    # ── Standalone RecoverIQ dialer path (fallback) ──────────────────────────────
    conn = _pick_dialer(db, case.branch)
    if not conn:
        raise HTTPException(status_code=400, detail="No dialer connected. Add one in Connections.")
    payload = {
        "contact": {"id": f"riq:case:{case.id}", "name": case.customer_name,
                    "phone": case.phone, "external_ref": case.account_no or case.card_no,
                    "branch": case.branch, "amount_due": str(case.pending_amount or 0)},
        "agent_id": f"riq:user:{user.id}", "agent_emp_code": user.emp_code,
        "campaign_id": f"riq:{case.bank}/{case.product}",
    }
    try:
        headers = {"Authorization": f"Bearer {conn.api_key}", "X-Integration-Key": conn.api_key}
        with httpx.Client(timeout=8.0, verify=False) as cl:
            r = cl.post(f"{conn.base_url}/calls/originate", json=payload, headers=headers)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code >= 400:
                raise HTTPException(status_code=502, detail=data.get("detail") or f"Dialer error {r.status_code}")
            return {"ok": True, "dialer": conn.name, "call": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the dialer: {str(e)[:160]}")


# ============================================================ dialer → RecoverIQ (keyed)
@router.get("/queues")
def queues(branch: str = None, product: str = None, conn: models.DialerConnection = Depends(_dialer_auth),
           db: Session = Depends(get_db)):
    """Call queues the dialer can work — one per bank/product (optionally branch-scoped)."""
    q = db.query(models.Case).filter(models.Case.removed.isnot(True))
    scope_branch = branch or conn.branch
    if scope_branch:
        q = q.filter(models.Case.branch == scope_branch)
    if product:
        q = q.filter(models.Case.product == product)
    groups: dict[str, dict] = {}
    for c in q.all():
        if (c.paid_status or "").upper() == "PAID" or getattr(c, "closed", False):
            continue
        key = f"{c.bank}/{c.product}"
        g = groups.setdefault(key, {"id": f"riq:queue:{key}", "name": key, "bank": c.bank,
                                    "product": c.product, "branch": scope_branch, "count": 0})
        g["count"] += 1
    return {"queues": list(groups.values())}


@router.get("/queues/{bank}/{product}/contacts")
def queue_contacts(bank: str, product: str, limit: int = 500, branch: str = None,
                   conn: models.DialerConnection = Depends(_dialer_auth), db: Session = Depends(get_db)):
    q = (db.query(models.Case)
         .filter(models.Case.removed.isnot(True), models.Case.bank == bank, models.Case.product == product))
    scope_branch = branch or conn.branch
    if scope_branch:
        q = q.filter(models.Case.branch == scope_branch)
    out = []
    for c in q.limit(max(1, min(limit, 2000))).all():
        if (c.paid_status or "").upper() == "PAID" or getattr(c, "closed", False) or not c.phone:
            continue
        out.append({"id": f"riq:case:{c.id}", "name": c.customer_name, "phone": c.phone,
                    "external_ref": c.account_no or c.card_no, "branch": c.branch,
                    "amount_due": str(c.pending_amount or 0), "disposition": c.disposition,
                    "language": None})
    return {"contacts": out, "count": len(out)}


def _case_from_ref(db: Session, contact_id: str):
    if contact_id and contact_id.startswith("riq:case:"):
        try:
            return db.query(models.Case).filter(models.Case.id == int(contact_id.split(":")[-1])).first()
        except Exception:
            return None
    return None


def _agent_from(db: Session, emp_code: str):
    if not emp_code:
        return None
    return db.query(models.User).filter(models.User.emp_code == emp_code).first()


@router.post("/calls")
def ingest_call(body: dict = Body(...), conn: models.DialerConnection = Depends(_dialer_auth),
                db: Session = Depends(get_db)):
    """Ingest a completed call from the dialer → a dated CallLog event on the case, attributed to
    the agent. Money (PAID) routes through paymath, exactly like an in-app payment."""
    case = _case_from_ref(db, body.get("contact_id") or "")
    if not case:
        raise HTTPException(status_code=404, detail="Unknown contact_id")
    agent = _agent_from(db, body.get("agent_emp_code"))
    disp = (body.get("disposition") or "").upper()
    ptp_amt = body.get("ptp_amount")
    ptp_date = body.get("ptp_date")
    paid_amt = Decimal(str(body.get("paid_amount") or 0))
    ptp_dt = None
    if ptp_date:
        try:
            ptp_dt = datetime.combine(datetime.fromisoformat(str(ptp_date)).date(), time.min).replace(tzinfo=timezone.utc)
        except Exception:
            ptp_dt = None
    log = models.CallLog(case_id=case.id, caller_id=(agent.id if agent else None),
                         disposition=disp or "PAYMENT",
                         ptp_amount=(Decimal(str(ptp_amt)) if ptp_amt else None),
                         ptp_date=ptp_dt, note=(body.get("note") or "Dialer call")[:2000],
                         recording_url=(body.get("recording_url") or None))
    db.add(log)
    case.last_contacted_at = datetime.now(timezone.utc)
    case.disposition = disp or case.disposition
    if paid_amt and paid_amt > 0:
        from .. import paymath
        case.received_amount = (Decimal(case.received_amount or 0) + paid_amt)
        n = Decimal(case.norm_amount or 0); s = Decimal(case.stab_amount or 0)
        if n > 0 or s > 0:
            recv = Decimal(case.received_amount or 0)
            case.norm_stab = "NORM" if (n > 0 and recv >= n) else ("STAB" if (s > 0 and recv >= s) else None)
        new_status = paymath.recompute(case)
        log.ptp_amount = paid_amt
        log.disposition = "PAID" if new_status == "PAID" else "PAYMENT"
    elif disp == "PTP":
        case.status = "ptp"; case.follow_up_date = (ptp_dt.date() if ptp_dt else case.follow_up_date)
    db.commit()
    try:
        from .realtime import notify_data_changed
        notify_data_changed(case.bank, case.product)
    except Exception:
        pass
    return {"ok": True, "case_id": case.id}


@router.post("/ptps")
def ingest_ptp(body: dict = Body(...), conn: models.DialerConnection = Depends(_dialer_auth),
               db: Session = Depends(get_db)):
    case = _case_from_ref(db, body.get("contact_id") or "")
    if not case:
        raise HTTPException(status_code=404, detail="Unknown contact_id")
    agent = _agent_from(db, body.get("agent_emp_code"))
    amt = body.get("amount")
    ptp_date = body.get("date")
    ptp_dt = None
    if ptp_date:
        try:
            ptp_dt = datetime.combine(datetime.fromisoformat(str(ptp_date)).date(), time.min).replace(tzinfo=timezone.utc)
        except Exception:
            ptp_dt = None
    db.add(models.CallLog(case_id=case.id, caller_id=(agent.id if agent else None),
                          disposition="PTP", ptp_amount=(Decimal(str(amt)) if amt else None),
                          ptp_date=ptp_dt, note="Dialer PTP"))
    case.status = "ptp"
    if ptp_dt:
        case.follow_up_date = ptp_dt.date()
    db.commit()
    return {"ok": True, "case_id": case.id}


# ============================================================ ViciDial connector
# Connect RecoverIQ to an EXISTING ViciDial (no self-hosted dialer). Click-to-call uses ViciDial's
# Agent API (external_dial) on the agent's live session; campaign push injects leads via the
# Non-Agent API (add_lead); dispositions + recordings come BACK via ViciDial's per-call "Dispo Call
# URL" hitting /vicidial/dispo. All HTTP API — no direct DB access to ViciDial.

def _vici_dispo_url(request_base: str, conn: models.DialerConnection) -> str:
    """The URL to paste into ViciDial campaign → 'Dispo Call URL'. ViciDial substitutes its own
    --A--var--B-- tokens at call time."""
    return (f"{request_base}/api/integration/vicidial/dispo"
            f"?key={conn.api_key}"
            "&case=--A--vendor_lead_code--B--"
            "&dispo=--A--dispo--B--"
            "&rec=--A--recording_filename--B--"
            "&agent=--A--user--B--"
            "&phone=--A--phone_number--B--"
            "&len=--A--talk_sec--B--")


@router.post("/vicidial/connect")
def vicidial_connect(body: dict = Body(...), db: Session = Depends(get_db),
                     user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    """Create or update THE ViciDial connection (one per branch, or one overall). Stores ViciDial
    API user/pass, campaign/list/source and the emp_code→vici-agent map in capabilities. Returns the
    Dispo Call URL to paste into ViciDial so dispositions + recordings flow back."""
    import secrets as _secrets
    name = (body.get("name") or "ViciDial").strip()
    base_url = (body.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="ViciDial base_url (e.g. http://192.168.1.50) is required")
    branch = (body.get("branch") or None)
    # Find existing vicidial conn for this branch (or the single global one) to update in place.
    q = db.query(models.DialerConnection).filter(models.DialerConnection.kind == "vicidial")
    existing = None
    for c in q.all():
        if (c.branch or "") == (branch or ""):
            existing = c
            break
    caps_in = {
        "vici_user": (body.get("vici_user") or "").strip(),
        "campaign_id": (body.get("campaign_id") or "").strip(),
        "list_id": (body.get("list_id") or "").strip(),
        "source": (body.get("source") or "recoveriq").strip(),
        "phone_code": (body.get("phone_code") or "91").strip(),
        "recording_base": (body.get("recording_base") or "").strip().rstrip("/"),
        # Recordings fetched over SFTP (when they aren't served over HTTP). RecoverIQ streams the
        # file on demand using these creds and the folder they live in.
        "sftp_host": (body.get("sftp_host") or "").strip(),
        "sftp_port": (body.get("sftp_port") or "").strip(),
        "sftp_user": (body.get("sftp_user") or "").strip(),
        "sftp_base": (body.get("sftp_base") or "").strip(),
        "agent_map": body.get("agent_map") or {},
    }
    if existing:
        caps = dict(existing.capabilities or {})
        caps.update({k: v for k, v in caps_in.items() if v not in (None, "", {})})
        # Only replace the password when a new non-empty one is supplied.
        if (body.get("vici_pass") or "").strip():
            caps["vici_pass"] = body["vici_pass"].strip()
        if (body.get("sftp_pass") or "").strip():
            caps["sftp_pass"] = body["sftp_pass"].strip()
        if isinstance(body.get("agent_map"), dict):
            caps["agent_map"] = body["agent_map"]
        existing.name = name or existing.name
        existing.base_url = base_url
        existing.branch = branch
        existing.capabilities = caps
        existing.enabled = True
        c = existing
    else:
        caps = dict(caps_in)
        if (body.get("vici_pass") or "").strip():
            caps["vici_pass"] = body["vici_pass"].strip()
        if (body.get("sftp_pass") or "").strip():
            caps["sftp_pass"] = body["sftp_pass"].strip()
        c = models.DialerConnection(kind="vicidial", name=name, base_url=base_url,
                                    api_key=_secrets.token_hex(16), branch=branch,
                                    enabled=True, status="unknown", capabilities=caps)
        db.add(c)
    db.commit(); db.refresh(c)
    audit.record(db, user, "integration", None, entity_type="integration",
                 detail=f"ViciDial connection '{name}' set ({base_url})")
    db.commit()
    request_base = (body.get("recoveriq_base") or "").strip().rstrip("/")
    out = _conn_out(c)
    out["dispo_url"] = _vici_dispo_url(request_base or "https://YOUR-RECOVERIQ-DOMAIN", c)
    return out


@router.post("/vicidial/test")
def vicidial_test(body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    """Verify ViciDial API creds with a harmless Non-Agent API call (version)."""
    c = db.query(models.DialerConnection).filter(models.DialerConnection.id == int(body.get("cid") or 0),
                                                 models.DialerConnection.kind == "vicidial").first()
    if not c:
        raise HTTPException(status_code=404, detail="ViciDial connection not found")
    caps = c.capabilities or {}
    params = {"source": caps.get("source") or "recoveriq", "user": caps.get("vici_user") or "",
              "pass": caps.get("vici_pass") or "", "function": "version"}
    try:
        with httpx.Client(timeout=8.0, verify=False) as cl:
            r = cl.get(f"{c.base_url}/vicidial/non_agent_api.php", params=params)
            txt = (r.text or "").strip()
        ok = "VERSION" in txt.upper() or txt.upper().startswith("SUCCESS")
        c.status = "ok" if ok else "down"
        c.last_seen = datetime.now(timezone.utc)
        db.commit()
        return {"ok": ok, "status": c.status, "detail": txt[:200]}
    except Exception as e:
        c.status = "down"; db.commit()
        return {"ok": False, "status": "down", "detail": str(e)[:200]}


@router.post("/vicidial/push")
def vicidial_push(body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles(*ADMIN_ROLES))):
    """Push the selected cases into a ViciDial list as leads (add_lead), tagging each with
    vendor_lead_code = case id so results map back. Filters: bank, product, branch, period, or an
    explicit case_ids list. list_id/campaign override the connection defaults when supplied."""
    c = _pick_vici(db, body.get("branch"))
    if not c:
        raise HTTPException(status_code=400, detail="No ViciDial connected. Add one in Connections.")
    caps = c.capabilities or {}
    list_id = str(body.get("list_id") or caps.get("list_id") or "").strip()
    if not list_id:
        raise HTTPException(status_code=400, detail="A ViciDial list_id is required (set it on the connection or pass it here).")
    q = db.query(models.Case).filter(models.Case.removed.isnot(True))
    ids = body.get("case_ids")
    if ids:
        q = q.filter(models.Case.id.in_([int(i) for i in ids]))
    else:
        for f in ("bank", "product"):
            if body.get(f):
                q = q.filter(getattr(models.Case, f) == body[f])
        if body.get("branch"):
            from sqlalchemy import func as _f
            q = q.filter(_f.lower(_f.trim(models.Case.branch)) == str(body["branch"]).strip().lower())
        if body.get("period"):
            q = q.filter(models.Case.period == body["period"])
    cases = q.limit(int(body.get("limit") or 5000)).all()
    pushed = skipped = failed = 0
    with httpx.Client(timeout=12.0, verify=False) as cl:
        for cs in cases:
            if not cs.phone or (cs.paid_status or "").upper() == "PAID" or getattr(cs, "closed", False):
                skipped += 1
                continue
            phone = "".join(ch for ch in str(cs.phone) if ch.isdigit())[-12:]
            if not phone:
                skipped += 1
                continue
            params = {
                "source": caps.get("source") or "recoveriq",
                "user": caps.get("vici_user") or "", "pass": caps.get("vici_pass") or "",
                "function": "add_lead", "phone_number": phone,
                "phone_code": str(caps.get("phone_code") or "91"),
                "list_id": list_id, "vendor_lead_code": str(cs.id),
                "first_name": (cs.customer_name or "")[:30],
                "address3": (cs.bank or ""), "comments": f"{cs.bank}/{cs.product} pend {cs.pending_amount}",
                "custom_fields": "Y", "duplicate_check": "DUPLIST",
            }
            try:
                r = cl.get(f"{c.base_url}/vicidial/non_agent_api.php", params=params)
                if (r.text or "").upper().strip().startswith("SUCCESS") or "ADDED TO LIST" in (r.text or "").upper():
                    pushed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
    c.last_seen = datetime.now(timezone.utc); db.commit()
    audit.record(db, user, "integration", None, entity_type="integration",
                 detail=f"ViciDial push → list {list_id}: {pushed} leads ({skipped} skipped, {failed} failed)")
    db.commit()
    return {"ok": True, "list_id": list_id, "pushed": pushed, "skipped": skipped, "failed": failed,
            "campaign_id": caps.get("campaign_id")}


@router.get("/vicidial/dispo")
def vicidial_dispo(key: str = "", case: str = "", dispo: str = "", rec: str = "",
                   agent: str = "", phone: str = "", length: str = "",
                   db: Session = Depends(get_db)):
    """ViciDial per-call 'Dispo Call URL' target — brings the DISPOSITION + RECORDING back onto the
    case. Authenticated by ?key= (the connection's api_key). Matches by vendor_lead_code = case id."""
    conn = (db.query(models.DialerConnection)
            .filter(models.DialerConnection.kind == "vicidial",
                    models.DialerConnection.api_key == key).first())
    if not conn:
        raise HTTPException(status_code=401, detail="Invalid key")
    try:
        cs = db.query(models.Case).filter(models.Case.id == int(case)).first()
    except Exception:
        cs = None
    if not cs:
        return {"ok": False, "detail": "no case match"}
    caps = conn.capabilities or {}
    # Recording URL. Priority: an absolute URL ViciDial already sent → SFTP fetch (when the
    # recordings live on the server's filesystem, reached over SFTP) → an HTTP recording base.
    rec_url = None
    if rec:
        if str(rec).lower().startswith("http"):
            rec_url = rec
        elif caps.get("sftp_host"):
            rec_url = _rec_signed_url(conn.id, rec)          # /api/integration/recording?... streams over SFTP
        elif caps.get("recording_base"):
            rec_url = f"{caps['recording_base']}/{rec}.mp3"
    ag = db.query(models.User).filter(models.User.emp_code == agent).first() if agent else None
    # Map the ViciDial agent user back to a RecoverIQ user via agent_map if emp_code didn't match.
    if not ag and agent:
        amap = {str(v).strip(): str(k).strip() for k, v in (caps.get("agent_map") or {}).items()}
        emp = amap.get(str(agent).strip())
        if emp:
            ag = db.query(models.User).filter(models.User.emp_code == emp).first()
    d = (dispo or "").upper().strip()
    note = f"ViciDial call ({dispo or 'dispo'})" + (f" · {length}s" if length else "")
    db.add(models.CallLog(case_id=cs.id, caller_id=(ag.id if ag else None),
                          disposition=d or "CALL", note=note[:2000], recording_url=rec_url))
    cs.last_contacted_at = datetime.now(timezone.utc)
    if d:
        cs.disposition = d
        if d in ("PTP", "PROMISE"):
            cs.status = "ptp"
    conn.last_seen = datetime.now(timezone.utc)
    db.commit()
    try:
        from .realtime import notify_data_changed
        notify_data_changed(cs.bank, cs.product)
    except Exception:
        pass
    return {"ok": True, "case_id": cs.id, "recording": bool(rec_url)}


# ============================================================ recording fetch over SFTP
# When ViciDial's recordings aren't served over HTTP (they live on the server filesystem, reached
# via SFTP), RecoverIQ streams a recording on demand over SFTP. The playable link is a SIGNED,
# EXPIRING URL (HMAC with the app secret) so it needs no login header and can be used in an <audio>
# tag, yet can't be forged or shared forever.
import hashlib as _hashlib
import hmac as _hmac
import time as _time
import base64 as _b64


def _rec_secret() -> bytes:
    from ..config import get_settings
    return (get_settings().secret_key or "dev-secret-change-me").encode()


def _rec_sig(conn_id: int, filename: str, exp: int) -> str:
    msg = f"{conn_id}|{filename}|{exp}".encode()
    return _b64.urlsafe_b64encode(_hmac.new(_rec_secret(), msg, _hashlib.sha256).digest()[:18]).decode()


def _rec_signed_url(conn_id: int, filename: str, ttl_days: int = 7) -> str:
    exp = int(_time.time()) + ttl_days * 86400
    from urllib.parse import quote
    return (f"/api/integration/recording?conn={conn_id}&f={quote(filename)}"
            f"&exp={exp}&sig={_rec_sig(conn_id, filename, exp)}")


@router.get("/recording")
def fetch_recording(conn: int, f: str, exp: int, sig: str, db: Session = Depends(get_db)):
    """Stream a call recording that lives on the ViciDial server's filesystem, fetched over SFTP.
    Authenticated by the signed, expiring URL (?sig=&exp=) built when the call result came in — so
    it plays in an <audio> element without a login header. Looks for the file directly under the
    configured SFTP base, then (bounded) searches sub-folders by exact name."""
    if int(exp) < int(_time.time()):
        raise HTTPException(status_code=410, detail="Recording link expired")
    if not _hmac.compare_digest(sig, _rec_sig(conn, f, int(exp))):
        raise HTTPException(status_code=403, detail="Bad signature")
    c = db.query(models.DialerConnection).filter(models.DialerConnection.id == conn,
                                                 models.DialerConnection.kind == "vicidial").first()
    if not c:
        raise HTTPException(status_code=404, detail="Connection not found")
    caps = c.capabilities or {}
    host = caps.get("sftp_host")
    if not host:
        raise HTTPException(status_code=400, detail="SFTP not configured for this connection")
    try:
        import paramiko
    except Exception:
        raise HTTPException(status_code=501, detail="paramiko not installed on the RecoverIQ server (pip install paramiko)")
    # harden the filename — no path traversal; keep just the basename.
    base_name = (f or "").replace("\\", "/").split("/")[-1].strip()
    if not base_name or base_name.startswith("."):
        raise HTTPException(status_code=400, detail="Bad filename")
    port = int(caps.get("sftp_port") or 22)
    # One or more roots (comma-separated). Recordings are partitioned per ViciDial USER GROUP and
    # then by YEAR/MONTH, e.g. /home/ICICI/2026/06/<file>. So a base of "/home" plus the date parsed
    # from the filename lets us jump straight to the right folder without a full crawl.
    roots = [r.strip().rstrip("/") or "/" for r in str(caps.get("sftp_base") or "/").split(",") if r.strip()] or ["/"]
    exts = ["", ".mp3", ".wav", ".gsm"]
    import re as _re
    dm = _re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", base_name)   # a YYYYMMDD stamp in the filename
    yy, mm, dd = (dm.group(1), dm.group(2), dm.group(3)) if dm else (None, None, None)

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(host, port=port, username=caps.get("sftp_user") or "",
                    password=caps.get("sftp_pass") or "", timeout=10, look_for_keys=False, allow_agent=False)
        sftp = cli.open_sftp()
        import stat as _stat

        # ViciDial's recording_filename often omits the channel suffix (-all/-in/-out) and the
        # extension, so match the stem too. e.g. given "20261007-100451_AXIS001_7036765403_AXIS"
        # the real file is "…_AXIS-all.mp3".
        name_variants = [base_name] + [base_name + sfx for sfx in ("-all", "-in", "-out")]

        def _file_in(d, prefix_ok=False):
            """Find the recording in directory d — exact name (with suffix/extension variants), or
            (when prefix_ok, used only for the targeted date folder) any file that starts with the
            stem and is an audio file."""
            for nm in name_variants:
                for e in exts:
                    p = f"{d}/{nm}{e}"
                    try:
                        sftp.stat(p); return p
                    except Exception:
                        pass
            if prefix_ok:
                try:
                    for en in sftp.listdir(d):
                        low = en.lower()
                        if en.startswith(base_name) and low.endswith((".mp3", ".wav", ".gsm")):
                            return f"{d}/{en}"
                except Exception:
                    pass
            return None

        def _subdirs(d):
            try:
                return [e.filename for e in sftp.listdir_attr(d) if _stat.S_ISDIR(e.st_mode)]
            except Exception:
                return []

        def _date_dirs(base):
            """Candidate date-partitioned folders under a base: base, base/YYYY/MM, base/YYYY/MM/DD."""
            out = [base]
            if yy:
                out += [f"{base}/{yy}/{mm}", f"{base}/{yy}/{mm}/{dd}", f"{base}/{yy}-{mm}", f"{base}/{yy}{mm}"]
            return out

        found = None
        # 1) Try each root directly, and its date-partitioned subfolders.
        for base in roots:
            for d in _date_dirs(base):
                found = _file_in(d, prefix_ok=True)
                if found:
                    break
            if found:
                break
        # 2) One level of group folders under each root (e.g. /home/ICICI, /home/AXIS), then date dirs.
        if not found:
            for base in roots:
                for grp in _subdirs(base):
                    for d in _date_dirs(f"{base}/{grp}"):
                        found = _file_in(d, prefix_ok=True)
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
        # 3) Last resort: bounded recursive search by exact name.
        if not found:
            targets = {base_name} | {base_name + e for e in exts if e}
            stack = [(r, 0) for r in roots]
            seen = 0
            while stack and not found and seen < 6000:
                d, depth = stack.pop()
                try:
                    entries = sftp.listdir_attr(d)
                except Exception:
                    continue
                for en in entries:
                    seen += 1
                    full = f"{d}/{en.filename}"
                    if _stat.S_ISDIR(en.st_mode):
                        if depth < 5:
                            stack.append((full, depth + 1))
                    elif en.filename in targets:
                        found = full
                        break
        if not found:
            cli.close()
            raise HTTPException(status_code=404, detail="Recording file not found on the server")

        ctype = "audio/wav" if found.lower().endswith(".wav") else "audio/mpeg"
        fh = sftp.open(found, "rb")
        fh.prefetch()

        def _gen():
            try:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                try: fh.close()
                except Exception: pass
                try: cli.close()
                except Exception: pass

        from fastapi.responses import StreamingResponse
        dl = found.split("/")[-1]
        return StreamingResponse(_gen(), media_type=ctype,
                                 headers={"Content-Disposition": f'inline; filename="{dl}"',
                                          "Cache-Control": "private, max-age=3600"})
    except HTTPException:
        try: cli.close()
        except Exception: pass
        raise
    except Exception as e:
        try: cli.close()
        except Exception: pass
        raise HTTPException(status_code=502, detail=f"Could not fetch recording over SFTP: {str(e)[:160]}")
