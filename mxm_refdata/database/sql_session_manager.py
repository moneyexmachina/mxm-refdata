"""SQL Session Manager for handling database interactions."""

import logging
from contextlib import contextmanager
from typing import Callable, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql import text

from mxm_refdata.models.orm import Base
from mxm_refdata.utils.config import load_config

logging.basicConfig(level=logging.INFO)


class SQLSessionManager:
    """Manages database sessions while ensuring consistent engine initialization."""

    def __init__(
        self,
        engine: Optional[Engine] = None,
        session_factory: Optional[Callable[[], Session]] = None,
    ):
        """
        Initialize the SQLSessionManager with a specific engine and session factory.

        Args:
            engine (Optional[Engine]): The database engine to use.
            session_factory (Optional[Callable[[], Session]]): A callable that provides new sessions.
        """
        config = load_config()
        self.engine: Engine = engine or create_engine(config.SQL_DB_URL, echo=True)
        self.session_factory: Callable[[], Session] = session_factory or sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def get_engine(self) -> Engine:
        """Return the configured database engine."""
        return self.engine

    def get_session_factory(self) -> Callable[[], Session]:
        """Return the configured session factory."""
        return self.session_factory

    def get_db_session(self) -> Session:
        """
        Provide a new database session.

        Returns:
            Session: A new SQLAlchemy session.
        """
        return self.session_factory()

    @contextmanager
    def db_session_scope(self):
        """
        Provide a transactional scope for database operations.

        Yields:
            Session: A transactional database session.
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
        """Initialize the database schema."""
        try:
            logging.info("Initializing database schema...")
            Base.metadata.create_all(bind=self.engine)
            logging.info(f"Tables created: {Base.metadata.tables.keys()}")
            return True
        except Exception as e:
            logging.error(f"Failed to initialize database schema: {e}")
            return False

    def drop_db(self) -> bool:
        """Drop all tables in the database."""
        try:
            logging.info("Dropping all tables in the database...")
            Base.metadata.drop_all(bind=self.engine)
            logging.info("All tables dropped successfully.")
            return True
        except Exception as e:
            logging.error(f"Failed to drop database: {e}")
            return False

    def check_db_connection(self) -> bool:
        """Check if the database connection is active."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                logging.info("Database connection is active.")
                return True
        except Exception as e:
            logging.error(f"Database connection check failed: {e}")
            return False
