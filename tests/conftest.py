import os

os.environ.setdefault("SECRET_KEY", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("MQTT_USERNAME", "test-backend")
os.environ.setdefault("MQTT_PASSWORD", "test-backend-password")
# httpx ASGITransport se predstavlja kao 127.0.0.1 -- to je "broker" u testovima.
os.environ.setdefault("MQTT_HOOK_ALLOWED_HOSTS", '["127.0.0.1"]')

from collections.abc import AsyncGenerator, Awaitable, Callable  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine.url import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Uvoz modula sa modelima popunjava `Base.metadata` -- bez toga `create_all`
# u `engine` fixture-u ne bi napravio nijednu tabelu.
import app.models.anomaly_log  # noqa: E402, F401
import app.models.audit_log  # noqa: E402, F401
import app.models.classroom  # noqa: E402, F401
import app.models.device  # noqa: E402, F401
import app.models.device_config  # noqa: E402, F401
import app.models.measurement  # noqa: E402, F401
import app.models.schedule  # noqa: E402, F401
import app.models.sensor_config  # noqa: E402, F401
import app.models.user  # noqa: E402, F401
from app.core.config import settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.classroom import Classroom  # noqa: E402
from app.models.device import Device, DeviceStatus  # noqa: E402
from app.models.user import Role, User  # noqa: E402


def _test_database_url() -> str:
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return override
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test").render_as_string(
        hide_password=False
    )


async def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_async_engine(
        target.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": target.database},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    await admin.dispose()


@pytest.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine]:
    url = _test_database_url()
    await _create_database_if_missing(url)

    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(
    session: AsyncSession, email: str, password: str, role: Role
) -> User:
    user = User(email=email, hashed_password=hash_password(password), role=role)
    session.add(user)
    await session.commit()
    return user


async def _authorized(
    ac: AsyncClient, session: AsyncSession, email: str, role: Role
) -> AsyncClient:
    password = "secret-password-123"
    await _make_user(session, email, password, role)
    response = await ac.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    ac.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return ac


@pytest.fixture
async def user_client(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncClient:
    return await _authorized(client, db_session, "user@test.rs", Role.USER)


@pytest.fixture
async def admin_client(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncClient:
    return await _authorized(client, db_session, "admin@test.rs", Role.ADMIN)


ClassroomFactory = Callable[..., Awaitable[Classroom]]
DeviceFactory = Callable[..., Awaitable[Device]]


@pytest.fixture
def make_classroom(db_session: AsyncSession) -> ClassroomFactory:
    async def _make(name: str = "A-101", description: str | None = None) -> Classroom:
        classroom = Classroom(name=name, description=description)
        db_session.add(classroom)
        await db_session.flush()
        return classroom

    return _make


@pytest.fixture
def make_device(db_session: AsyncSession) -> DeviceFactory:
    """Ubacuje uredjaj direktno u bazu -- REST API za uredjaje jos ne postoji."""

    async def _make(
        classroom_id: int,
        username: str = "esp32-1",
        secret: str = "device-secret-123",
        status: DeviceStatus = DeviceStatus.ACTIVE,
    ) -> Device:
        device = Device(
            classroom_id=classroom_id,
            username=username,
            hashed_password=hash_password(secret),
            status=status,
        )
        db_session.add(device)
        await db_session.flush()
        return device

    return _make
