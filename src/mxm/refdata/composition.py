"""Composition root for MXM reference data."""

from __future__ import annotations

from sqlalchemy import URL

from mxm.config import MXMConfig, make_view
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.factories import (
    FuturesContractFactory,
    FuturesProductFactory,
    PeriodFactory,
)
from mxm.refdata.runtime import RefData
from mxm.runtime import RuntimeContext


def build_refdata(ctx: RuntimeContext) -> RefData:
    """Build the RefData runtime object graph from a resolved RuntimeContext."""
    config = make_view(
        ctx.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )

    db_url = resolve_database_url(
        ctx=ctx,
        config=config,
    )

    session_manager = SQLSessionManager.from_db_url(db_url)

    return RefData(
        config=config,
        session_manager=session_manager,
        product_factory=FuturesProductFactory.from_config(config),
        contract_factory=FuturesContractFactory.from_config(config),
        period_factory=PeriodFactory(),
    )


def resolve_database_url(
    *,
    ctx: RuntimeContext,
    config: MXMConfig,
) -> str:
    """Resolve the configured refdata database URL."""
    explicit_url = config.get("SQL_DB_URL")
    if explicit_url is not None:
        return str(explicit_url)

    db_configs = ctx.db_configs
    if db_configs is None:
        raise RuntimeError("RuntimeContext does not contain database configuration.")

    secrets = ctx.secrets
    if secrets is None:
        raise RuntimeError("RuntimeContext does not contain a configured secrets API.")

    try:
        db_config = db_configs["operational_state"]
    except KeyError as err:
        raise RuntimeError(
            "Database configuration 'operational_state' is missing."
        ) from err

    password_ref = str(db_config["password_ref"])
    password = secrets.get_secret(
        password_ref,
        identity=ctx.identity,
    )

    if password is None:
        raise RuntimeError(f"Database password {password_ref!r} could not be resolved.")

    driver = str(db_config["driver"])
    if driver != "postgresql":
        raise RuntimeError(f"Unsupported operational database driver: {driver!r}.")

    url = URL.create(
        drivername="postgresql+psycopg",
        username=str(db_config["user"]),
        password=password,
        host=str(db_config["host"]),
        port=int(db_config["port"]),
        database=str(db_config["name"]),
    )

    return url.render_as_string(hide_password=False)
