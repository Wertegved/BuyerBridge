from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DatabaseSession
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.tables import Base
from app.main import app
from app.models.buyer import Buyer
from app.models.email import Email
from app.models.search import Search
from app.models.session import Session as SessionRecord
from app.models.user import User
from app.routes.auth import get_current_user


def test_clear_dashboard_data_only_deletes_current_users_records():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with DatabaseSession(engine) as database:
        current_user = User(
            name="Current User",
            email="current@example.com",
            password_hash="unused",
            is_active=True,
        )
        other_user = User(
            name="Other User",
            email="other@example.com",
            password_hash="unused",
            is_active=True,
        )
        database.add_all([current_user, other_user])
        database.flush()

        start = datetime(2026, 1, 1)
        database.add_all([
            Search(
                user_id=current_user.id,
                product_category="First",
                product_description="A sufficiently long product description.",
                buyer_type="Retailer",
                location="New York",
                country="United States",
                result_count=2,
                created_at=start,
            ),
            Search(
                user_id=other_user.id,
                product_category="Other",
                product_description="A sufficiently long product description.",
                buyer_type="Retailer",
                location="Chicago",
                country="United States",
                result_count=1,
                created_at=start + timedelta(days=1),
            ),
            Search(
                user_id=current_user.id,
                product_category="Second",
                product_description="A sufficiently long product description.",
                buyer_type="Retailer",
                location="Boston",
                country="United States",
                result_count=1,
                created_at=start + timedelta(days=2),
            ),
        ])
        database.flush()

        buyers = [
            Buyer(business_name="Current First A", created_at=start + timedelta(hours=1)),
            Buyer(business_name="Current First B", created_at=start + timedelta(hours=2)),
            Buyer(business_name="Other User Buyer", created_at=start + timedelta(days=1, hours=1)),
            Buyer(business_name="Current Second", created_at=start + timedelta(days=2, hours=1)),
            Buyer(business_name="Unassociated Buyer", created_at=start - timedelta(days=1)),
        ]
        database.add_all(buyers)
        database.flush()

        database.add_all([
            Email(user_id=current_user.id, buyer_id=buyers[0].id, subject="Current email", message="Message"),
            Email(user_id=current_user.id, buyer_id=buyers[3].id, subject="Current email 2", message="Message"),
            Email(user_id=other_user.id, buyer_id=buyers[2].id, subject="Other email", message="Message"),
        ])
        database.add(
            SessionRecord(
                user_id=current_user.id,
                session_token_hash="current-session",
                expires_at=start + timedelta(days=30),
            )
        )
        database.commit()

        def override_database():
            with DatabaseSession(engine) as request_database:
                yield request_database

        previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = override_database
        client = TestClient(app)
        try:
            unauthorized = client.delete("/api/dashboard/data")
            assert unauthorized.status_code == 401

            app.dependency_overrides[get_current_user] = lambda: current_user
            response = client.delete("/api/dashboard/data")
            assert response.status_code == 200
            assert response.json() == {
                "status": "ok",
                "deleted": {"searches": 2, "buyers": 3, "emails": 2},
            }
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

        assert set(database.execute(select(Search.user_id)).scalars().all()) == {other_user.id}
        assert database.execute(select(Buyer.business_name).order_by(Buyer.id)).scalars().all() == [
            "Other User Buyer",
            "Unassociated Buyer",
        ]
        assert database.execute(select(Email.user_id)).scalars().all() == [other_user.id]
        assert database.execute(select(User.id).order_by(User.id)).scalars().all() == [
            current_user.id,
            other_user.id,
        ]
        assert database.execute(select(SessionRecord.user_id)).scalars().all() == [current_user.id]

    Base.metadata.drop_all(engine)
    engine.dispose()
