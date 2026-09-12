from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import get_settings

settings = get_settings()

# Allow SQLite fallback for quick local runs if someone overrides DATABASE_URL.
connect_args = {}
_is_sqlite = settings.database_url.startswith("sqlite")
if _is_sqlite:
    connect_args = {"check_same_thread": False}

# Pool sizing (applies to both SQLite and Postgres). The default 5 + 10 overflow was too
# small once every client started sending a presence heartbeat: under load all 15 connections
# get checked out waiting on the DB and the next request times out. A larger pool + recycle
# absorbs those spikes. These values are safe and beneficial on Postgres too (no change needed
# when DATABASE_URL is switched over for go-live).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=20,          # persistent connections kept open
    max_overflow=40,       # extra burst connections when the pool is busy
    pool_recycle=1800,     # recycle a connection after 30 min (avoids stale server-side closes)
    pool_timeout=30,       # wait up to 30s for a free connection before erroring
    connect_args=connect_args,
)

# Make it unambiguous which database this process is actually using (credentials hidden).
try:
    _where = settings.database_url.split("://", 1)[-1]
    _where = _where.split("@")[-1] if "@" in _where else _where
    print(f"[SSD] Database: {'SQLite' if _is_sqlite else 'PostgreSQL'}  ->  {_where}", flush=True)
except Exception:
    pass

if _is_sqlite:
    # Keep read endpoints (ORDER BY / large SELECTs) working even when the host
    # disk is nearly full: sort/temp data goes to memory instead of a disk temp
    # file. (Writes still need free disk — free space on the machine to fix 500s.)
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA temp_store=MEMORY")
        # WAL lets readers and one writer work at the same time, instead of every reader
        # blocking behind the writer (the root cause of the QueuePool timeouts under the
        # presence-heartbeat write load). busy_timeout makes a writer WAIT up to 20s for the
        # lock instead of holding its pooled connection and jamming the pool. synchronous=NORMAL
        # is the safe, standard pairing with WAL. All SQLite-only: this hook never fires on
        # Postgres, so nothing here needs undoing at go-live.
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=20000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ----------------------------------------------------------------------------
# PostgreSQL-safety guard (applies to EVERY model, EVERY insert/update).
# SQLite silently accepts values that PostgreSQL rejects and aborts the whole
# transaction on. The two classic import killers are:
#   1) a string longer than its column's declared length  -> value too long
#   2) a NUL byte (\x00) inside text                       -> invalid for type text
# This before_flush hook cleans both on the way in, so a stray Excel cell can
# never crash an import/seed/edit on Postgres. It is a no-op for well-formed data
# and harmless on SQLite too.
# ----------------------------------------------------------------------------
from sqlalchemy import String as _SAString, Text as _SAText          # noqa: E402
from sqlalchemy.orm import Session as _SASession                      # noqa: E402


def _pg_safe(obj):
    try:
        cols = obj.__table__.columns
    except Exception:
        return
    for col in cols:
        if not isinstance(col.type, (_SAString, _SAText)):
            continue
        val = getattr(obj, col.name, None)
        if not isinstance(val, str):
            continue
        new = val
        if "\x00" in new:
            new = new.replace("\x00", "")
        limit = getattr(col.type, "length", None)
        if limit and len(new) > limit:
            new = new[:limit].rstrip()
        if new != val:
            setattr(obj, col.name, new)


@event.listens_for(_SASession, "before_flush")
def _pg_safe_before_flush(session, flush_context, instances):
    for obj in list(session.new) + list(session.dirty):
        _pg_safe(obj)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
