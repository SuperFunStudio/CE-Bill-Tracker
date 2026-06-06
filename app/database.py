from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Convert postgresql:// to postgresql+asyncpg:// for async driver.
# asyncpg does not support the ?host= query parameter for Unix sockets (that's a libpq/psycopg2
# feature). Instead we strip it from the URL and pass it via connect_args so asyncpg receives
# it as a keyword argument directly.
_raw_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

_parsed = urlparse(_raw_url)
_query = parse_qs(_parsed.query, keep_blank_values=True)
_socket_host = _query.pop("host", [None])[0]  # e.g. /cloudsql/project:region:instance

_clean_url = urlunparse(_parsed._replace(query=urlencode({k: v[0] for k, v in _query.items()})))

_connect_args: dict = {"server_settings": {"client_encoding": "utf8"}}
if _socket_host:
    # asyncpg accepts `host` as a keyword arg; for a Unix socket directory it appends
    # /.s.PGSQL.<port> automatically (port defaults to 5432).
    _connect_args["host"] = _socket_host

engine = create_async_engine(
    _clean_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
