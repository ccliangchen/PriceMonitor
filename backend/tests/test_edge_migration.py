from sqlalchemy import create_engine, text

from app.core.db import _ensure_lightweight_migrations
from app.core.models import Base


def test_existing_taobao_edge_preference_resets_to_direct_first():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE listings (id INTEGER PRIMARY KEY, platform TEXT, status TEXT)")
        )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO listings (id,platform,status) VALUES "
                "(1,'taobao','active'),(2,'taobao','paused'),(3,'jd','active')"
            )
        )
        for listing_id, platform in ((1, "taobao"), (2, "taobao"), (3, "jd")):
            connection.execute(
                text(
                    "INSERT INTO job_runs "
                    "(platform,listing_id,job_type,started_at,status,error_message) "
                    "VALUES (:platform,:listing_id,'page_price',:started_at,'failed',:error)"
                ),
                {
                    "platform": platform,
                    "listing_id": listing_id,
                    "started_at": "2026-11-02 04:04:00",
                    "error": "淘宝触发验证",
                },
            )

    _ensure_lightweight_migrations(engine)

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id,capture_mode,status FROM listings ORDER BY id")
        ).all()
    assert rows == [
        (1, "primary", "active"),
        (2, "primary", "paused"),
        (3, "primary", "active"),
    ]

    with engine.begin() as connection:
        connection.execute(text("UPDATE listings SET capture_mode='edge' WHERE id=1"))
    _ensure_lightweight_migrations(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT capture_mode FROM listings WHERE id=1")
        ).scalar_one() == "primary"


def test_restart_does_not_promote_rejected_jd_price_to_high_confidence():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE listings (id INTEGER PRIMARY KEY, platform TEXT, "
                "status TEXT, capture_mode TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE price_snapshots (id INTEGER PRIMARY KEY, "
                "listing_id INTEGER, source TEXT, status TEXT, confidence TEXT, "
                "page_price_cents INTEGER, estimated_price_cents INTEGER, "
                "coupon_discount_cents INTEGER)"
            )
        )
        connection.execute(
            text("INSERT INTO listings VALUES (6,'jd','active','primary')")
        )
        connection.execute(
            text(
                "INSERT INTO price_snapshots VALUES "
                "(1,6,'page','ok','low',50000,50000,0),"
                "(2,6,'page','ok',NULL,394348,394348,0)"
            )
        )
    _ensure_lightweight_migrations(engine)
    _ensure_lightweight_migrations(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id,confidence FROM price_snapshots ORDER BY id")
        ).all() == [(1, "low"), (2, "high")]


def test_existing_products_start_with_monitoring_enabled():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO products (id) VALUES (1)"))
    Base.metadata.create_all(engine)

    _ensure_lightweight_migrations(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT monitoring_enabled FROM products WHERE id=1")
        ).scalar_one() == 1
