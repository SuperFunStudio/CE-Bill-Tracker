import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Load .env for local development (no-op in Cloud Run where env vars are injected)
from dotenv import load_dotenv
load_dotenv()

config = context.config

# Override sqlalchemy.url from environment
db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL is not set. Cannot run migrations.", file=sys.stderr)
    sys.exit(1)

# Alembic needs sync driver; strip asyncpg if present
db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so autogenerate detects them
from app.database import Base
import app.models  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # lock_timeout: a schema change (e.g. ALTER TABLE ADD COLUMN) needs an
    # ACCESS EXCLUSIVE lock. The live API uses some of these tables (e.g.
    # alert_subscriptions), so the lock can be momentarily held elsewhere. Without
    # a timeout the migration waits forever AND blocks the app behind it — exactly
    # the 30-min build hang we hit. 15s makes a blocked migration fail fast and
    # release its queue slot; the build step retries to catch a clean window.
    # lock_timeout only fires while WAITING for a lock, so it never interrupts a
    # migration that is already running.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-c client_encoding=utf8 -c lock_timeout=15000"},
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
