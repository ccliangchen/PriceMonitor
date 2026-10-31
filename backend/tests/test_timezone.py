from datetime import UTC, datetime

from app.core.db import dispose_db, init_db, session_scope
from app.core.models import Account
from app.core.schemas import AccountResponse


def test_sqlite_datetime_is_utc_aware(tmp_path):
    init_db(tmp_path)
    with session_scope() as db:
        account = Account(
            platform="jd",
            display_name="京东账号",
            profile_dir="profile",
            status="logged_in",
            last_login_at=datetime(2026, 10, 30, 6, 7, 17, tzinfo=UTC),
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        assert account.last_login_at is not None
        assert account.last_login_at.tzinfo is not None
        response = AccountResponse.model_validate(account)
        serialized = response.model_dump(mode="json")["last_login_at"]
        assert serialized.endswith("Z") or "+00:00" in serialized

    dispose_db()
