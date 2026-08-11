"""Composition root for MXM reference data."""

from __future__ import annotations

from mxm.config import make_view
from mxm.refdata.reader import RefDataReader
from mxm.refdata.runtime import RefData
from mxm.refdata.sql.postgres import PostgresDatabase
from mxm.runtime import RuntimeContext

__all__ = [
    "build_refdata",
]


def build_refdata(
    ctx: RuntimeContext,
) -> RefData:
    """Build the RefData runtime object graph from a resolved RuntimeContext.

    Runtime configuration and secrets are resolved only at this composition
    boundary. Lower application layers receive concrete dependencies rather
    than runtime context, database configuration, or secret references.
    """

    config = make_view(
        ctx.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )

    database = _build_database(
        ctx=ctx,
    )

    reader = RefDataReader(
        database=database,
    )

    return RefData(
        config=config,
        database=database,
        reader=reader,
    )


def _build_database(
    *,
    ctx: RuntimeContext,
) -> PostgresDatabase:
    """Build the operational PostgreSQL boundary from runtime configuration."""

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

    driver = str(db_config["driver"])

    if driver != "postgresql":
        raise RuntimeError(f"Unsupported operational database driver: {driver!r}.")

    password_ref = str(db_config["password_ref"])

    password = secrets.get_secret(
        password_ref,
        identity=ctx.identity,
    )

    if password is None:
        raise RuntimeError(f"Database password {password_ref!r} could not be resolved.")

    return PostgresDatabase.from_config(
        host=str(db_config["host"]),
        port=int(db_config["port"]),
        database=str(db_config["name"]),
        user=str(db_config["user"]),
        password=password,
    )
