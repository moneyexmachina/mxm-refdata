from __future__ import annotations

from datetime import date

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
        return False


def build_refdata(
    *,
    session_manager: SQLSessionManager | None = None,
    csv_file_path: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> None:
    """Build the refdata database without first dropping existing tables."""
    from mxm.refdata.services.ref_data_service import RefDataService

    sm = session_manager or SQLSessionManager()
    sm.init_db()

    RefDataService(session_manager=sm).setup_instruments(
        csv_file_path=csv_file_path,
        start_date=start_date,
        end_date=end_date,
    )


def rebuild_refdata(
    *,
    session_manager: SQLSessionManager | None = None,
    csv_file_path: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> None:
    """Destructively rebuild the refdata database."""
    from mxm.refdata.services.ref_data_service import RefDataService

    sm = session_manager or SQLSessionManager()
    svc = RefDataService(session_manager=sm)

    svc.reset_database()
    svc.setup_instruments(
        csv_file_path=csv_file_path,
        start_date=start_date,
        end_date=end_date,
    )


def ensure_refdata_ready(session_manager: SQLSessionManager, cfg: Config) -> None:
    """
    Ensure the refdata DB is initialised and populated.

    If already populated, this is a no-op. If empty and buildable, the packaged
    ontology is materialised. If managed, missing refdata is an error.
    """
    if _db_has_any_products(session_manager):
        return

    if cfg.REFDATA_DB_MODE != "buildable":
        raise RefDataNotInitialisedError(
            "Refdata database is not initialised and auto-creation is forbidden "
            f"(REFDATA_DB_MODE={cfg.REFDATA_DB_MODE!r}). Initialise refdata explicitly."
        )

    build_refdata(
        session_manager=session_manager,
        csv_file_path=cfg.REFDATA_FUTURES_PRODUCTS_CSV_PATH,
    )
