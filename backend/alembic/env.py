from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# When running Alembic from backend/, imports resolve from this directory.
from config import settings, sqlalchemy_connect_args
from models.models import Base


# Alembic Config object (reads settings from alembic.ini)
config = context.config

# Configure Python logging via alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata used for autogenerate support
target_metadata = Base.metadata


def _database_url() -> str:
    # Use the same DATABASE_URL the app uses (from backend/.env via Settings)
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args=sqlalchemy_connect_args(),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
