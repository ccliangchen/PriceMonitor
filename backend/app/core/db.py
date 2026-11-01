from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _ensure_lightweight_migrations(engine: Engine) -> None:
    """Apply tiny additive migrations for databases created by older builds."""
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("price_snapshots")}
    if "confidence" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE price_snapshots ADD COLUMN confidence VARCHAR(16)")
            )
    with engine.begin() as connection:
        # Older builds used three levels and often left confidence empty.
        # Current policy is high/low only: explicit final page prices are
        # high, everything else is low and never used for history/push.
        connection.execute(
            text("UPDATE price_snapshots SET confidence='low' WHERE confidence='medium'")
        )
        connection.execute(
            text(
                "UPDATE price_snapshots SET confidence='high' "
                "WHERE source='checkout' AND status='ok' AND confidence IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE price_snapshots SET confidence='high' "
                "WHERE source='page' AND status='ok' AND confidence IS NULL "
                "AND page_price_cents IS NOT NULL "
                "AND estimated_price_cents IS NOT NULL "
                "AND estimated_price_cents < page_price_cents "
                "AND coupon_discount_cents > 0 "
                "AND listing_id IN (SELECT id FROM listings WHERE platform='taobao')"
            )
        )
        connection.execute(
            text(
                "UPDATE price_snapshots SET confidence='high' "
                "WHERE source='page' AND status='ok' "
                "AND (confidence IS NULL OR confidence='low') "
                "AND page_price_cents IS NOT NULL "
                "AND estimated_price_cents = page_price_cents "
                "AND (coupon_discount_cents IS NULL OR coupon_discount_cents = 0) "
                "AND listing_id IN (SELECT id FROM listings WHERE platform='jd')"
            )
        )
        connection.execute(
            text(
                "UPDATE price_snapshots SET confidence='low' "
                "WHERE source='page' AND status='ok' AND confidence IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE price_snapshots SET confidence='high' "
                "WHERE source='page' AND status='ok' AND confidence='low' "
                "AND coupon_discount_cents=0 "
                "AND page_price_cents IS NOT NULL "
                "AND page_price_cents=estimated_price_cents "
                "AND listing_id IN (SELECT id FROM listings WHERE platform='jd')"
            )
        )


def init_db(data_dir: Path) -> Engine:
    global _engine, _SessionLocal

    if _engine is not None:
        _engine.dispose()

    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "data.db"
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
        future=True,
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(_engine)
    _ensure_lightweight_migrations(_engine)
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database has not been initialized")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database has not been initialized")
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db() -> bool:
    if _engine is None:
        return False
    try:
        with _engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def dispose_db() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
