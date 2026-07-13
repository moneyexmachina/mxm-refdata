"""Database session management for mxm-refdata."""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql import text

from mxm.refdata.models.orm import Base

logger = logging.getLogger(__name__)


class SQLSessionManager:
    """Manage database connectivity, sessions, and transactional scopes.

    This class does not discover configuration, load environment files, or infer
    database locations. Callers must either provide already-materialised database
    session infrastructure to the constructor or use ``from_db_url`` with an
    explicit database URL.
    """

    def __init__(
        self,
        *,
        engine: Engine,
        session_factory: Callable[[], Session],
    ) -> None:
        """Initialise the manager from explicit database session infrastructure.

        Args:
            engine: Database engine used for connectivity and schema operations.
            session_factory: Factory producing database sessions.
        """
        self.engine = engine
        self.session_factory = session_factory

    @classmethod
    def from_db_url(
        cls,
        db_url: str,
        *,
        echo: bool = False,
    ) -> SQLSessionManager:
        """Construct a session manager from an explicit database URL.

        Args:
            db_url: Database URL understood by the current database backend.
            echo: Whether the backend should emit generated query logs.

        Returns:
            Configured database session manager.
        """
        normalised_db_url = _normalise_sqlite_db_url(db_url)

        engine = create_engine(normalised_db_url, echo=echo)
        session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )

        return cls(
            engine=engine,
            session_factory=session_factory,
        )

    def get_engine(self) -> Engine:
        """Return the configured database engine."""
        return self.engine

    def get_session_factory(self) -> Callable[[], Session]:
        """Return the configured database session factory."""
        return self.session_factory

    def get_db_session(self) -> Session:
        """Return a new database session."""
        return self.session_factory()

    @contextmanager
    def db_session_scope(self) -> Generator[Session]:
        """Provide a transactional database session scope.

        The yielded session is committed on successful exit, rolled back on
        exception, and closed in all cases.

        Yields:
            Database session.
        """
        db_session = self.get_db_session()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    def init_db(self) -> bool:
        """Create all managed database tables.

        Returns:
            True if schema initialisation succeeds, otherwise False.
        """
        try:
            logger.info("Initializing database schema.")
            Base.metadata.create_all(bind=self.engine)
            logger.info("Tables created: %s", list(Base.metadata.tables.keys()))
            return True
        except Exception:
            logger.exception("Failed to initialize database schema.")
            return False

    def drop_db(self) -> bool:
        """Drop all managed database tables.

        Returns:
            True if schema deletion succeeds, otherwise False.
        """
        try:
            logger.info("Dropping all managed database tables.")
            Base.metadata.drop_all(bind=self.engine)
            logger.info("All managed database tables dropped successfully.")
            return True
        except Exception:
            logger.exception("Failed to drop managed database tables.")
            return False

    def check_db_connection(self) -> bool:
        """Check whether the configured database connection is active.

        Returns:
            True if a trivial query succeeds, otherwise False.
        """
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("Database connection is active.")
            return True
        except Exception:
            logger.exception("Database connection check failed.")
            return False


def _normalise_sqlite_db_url(sql_db_url: str) -> str:
    """Expand user paths and ensure parent dirs for file-based SQLite URLs."""
    prefix = "sqlite:///"
    if not sql_db_url.startswith(prefix):
        return sql_db_url

    raw_path = sql_db_url[len(prefix) :]
    if not raw_path or raw_path == ":memory:":
        return sql_db_url

    db_path = Path(raw_path).expanduser()

    if db_path.is_absolute():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    return f"{prefix}{db_path}"
