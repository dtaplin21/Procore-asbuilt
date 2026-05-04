"""DATABASE_SSL_INSECURE_DEV and APP_ENV behavior for Postgres TLS."""

from config import Settings, sqlalchemy_connect_args


def test_insecure_ssl_disabled_when_production_even_if_requested():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        app_env="production",
        database_ssl_insecure_dev=True,
    )
    assert s.database_ssl_insecure_dev is False


def test_sqlalchemy_connect_args_empty_when_insecure_off():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        app_env="development",
        database_ssl_insecure_dev=False,
    )
    assert sqlalchemy_connect_args(s) == {}


def test_sqlalchemy_connect_args_insecure_dev_returns_ssl_context():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        app_env="development",
        database_ssl_insecure_dev=True,
    )
    args = sqlalchemy_connect_args(s)
    assert "ssl_context" in args
    ctx = args["ssl_context"]
    assert ctx.verify_mode.name == "CERT_NONE"


def test_sqlalchemy_connect_args_ignored_in_production():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        app_env="production",
        database_ssl_insecure_dev=True,
    )
    assert s.database_ssl_insecure_dev is False
    assert sqlalchemy_connect_args(s) == {}
