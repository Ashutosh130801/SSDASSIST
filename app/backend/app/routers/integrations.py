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
    return {"id": c.id, "kind": c.kind, "name": c.name, "base_url": c.base_url,
            "api_key_masked": _mask(c.api_key or ""), "branch": c.branch,
            "enabled": bool(c.enabled), "status": c.status,
            "capabilities": c.capabilities or {},
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
    return {"dialer": {"connected": bool(dialers), "count": len(dialers),
                       "names": [c.name for c in dialers]},
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


@router.post("/click-to-call")
def click_to_call(body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """Ask the connected dialer to place a call: ring the agent, bridge to the customer."""
    case = db.query(models.Case).filter(models.Case.id == int(body.get("case_id") or 0)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.phone:
        raise HTTPException(status_code=400, detail="This case has no phone number")
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
                         ptp_date=ptp_dt, note=(body.get("note") or "Dialer call")[:2000])
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
