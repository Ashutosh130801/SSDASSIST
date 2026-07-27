from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import get_settings

settings = get_settings()

# Allow SQLite fallback for quick local runs if someone overrides DATABASE_URL.
connect_args = {}
_is_sqlite = settings.database_url.startswith("sqlite")
if _is_sqlite:
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

if _is_sqlite:
    # Keep read endpoints (ORDER BY / large SELECTs) working even when the host
    # disk is nearly full: sort/temp data goes to memory instead of a disk temp
    # file. (Writes still need free disk — free space on the machine to fix 500s.)
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
