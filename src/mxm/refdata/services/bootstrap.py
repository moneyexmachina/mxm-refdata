from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from mxm.refdata.config import RefDataConfigData
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.models.orm.futures_products import FuturesProductORM


class RefDataNotInitialisedError(RuntimeError):
    """Raised when refdata is required but DB auto-initialisation is forbidden."""


def _db_has_any_products(session_manager: SQLSessionManager) -> bool:
    """Return whether the configured refdata database contains any products."""
    try:
        with session_manager.db_session_scope() as session:
            return session.query(FuturesProductORM).limit(1).first() is not None
    except SQLAlchemyError:
        return False


def build_refdata(
    *,
    config: RefDataConfigData,
    session_manager: SQLSessionManager,
) -> None:
    """Build the refdata database without first dropping existing tables."""
    from mxm.refdata.services.ref_data_service import RefDataService

    session_manager.init_db()

    RefDataService.from_config_data(
        config=config,
        session_manager=session_manager,
    ).setup_instruments()


def rebuild_refdata(
    *,
    config: RefDataConfigData,
    session_manager: SQLSessionManager,
) -> None:
    """Destructively rebuild the refdata database."""
    from mxm.refdata.services.ref_data_service import RefDataService

    svc = RefDataService.from_config_data(
        config=config,
        session_manager=session_manager,
    )

    svc.reset_database()
    svc.setup_instruments()


def ensure_refdata_ready(
    session_manager: SQLSessionManager,
    config: RefDataConfigData,
) -> None:
    """Ensure the refdata database is initialised and populated.

    If already populated, this is a no-op. If empty and buildable, the configured
    reference-data universe is materialised. If managed, missing refdata is an
    error.
    """
    if _db_has_any_products(session_manager):
        return

    if config["REFDATA_DB_MODE"] != "buildable":
        raise RefDataNotInitialisedError(
            "Refdata database is not initialised and auto-creation is forbidden "
            f"(REFDATA_DB_MODE={config['REFDATA_DB_MODE']!r}). "
            "Initialise refdata explicitly."
        )

    build_refdata(
        config=config,
        session_manager=session_manager,
    )
