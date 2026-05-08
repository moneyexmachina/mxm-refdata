from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.utils.config import Config


class RefDataNotInitialisedError(RuntimeError):
    """Raised when refdata is required but DB auto-initialisation is forbidden."""


def _db_has_any_products(session_manager: SQLSessionManager) -> bool:
    try:
        with session_manager.db_session_scope() as session:
            return session.query(FuturesProductORM).limit(1).first() is not None
    except SQLAlchemyError:
        # Covers missing tables/schema or other DB-level failures
        return False


def ensure_refdata_ready(session_manager: SQLSessionManager, cfg: Config) -> None:
    """
    Ensure the refdata DB is initialised and populated.

    - If already populated, no-op.
    - If not populated:
        - buildable: materialise from packaged specs.
        - managed: raise.
    """
    if _db_has_any_products(session_manager):
        return

    mode = getattr(cfg, "REFDATA_DB_MODE", "buildable")
    if mode != "buildable":
        raise RefDataNotInitialisedError(
            "Refdata database is not initialised and auto-creation is forbidden "
            f"(REFDATA_DB_MODE={mode!r}). Initialise refdata explicitly."
        )
    # Buildable mode: ensure schema exists, then materialise
    session_manager.init_db()

    # Buildable mode: materialise
    from mxm.refdata.services.ref_data_service import RefDataService

    RefDataService(session_manager=session_manager).setup_instruments()
