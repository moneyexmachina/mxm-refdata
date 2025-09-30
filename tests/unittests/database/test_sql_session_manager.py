"""Test cases for the SQLSessionManager class."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mxm_refdata.database.sql_session_manager import SQLSessionManager


@pytest.fixture(scope="session")
def db_engine():
    """Create a persistent test database and ensure cleanup after tests."""
    test_db_path = "test_db.sqlite"
    engine = create_engine(f"sqlite:///{test_db_path}")

    yield engine  # Provide the engine for testing

    # Cleanup: Remove test database after tests complete
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.fixture(scope="module")
def session_factory(db_engine):
    """Provide a session factory for testing."""
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture
def session_manager(db_engine, session_factory):
    """Provide an instance of SQLSessionManager for testing."""
    return SQLSessionManager(engine=db_engine, session_factory=session_factory)


def test_db_session_scope(session_manager):
    """Test transactional scope within `db_session_scope`."""
    with session_manager.db_session_scope() as session:
        assert session is not None, "Session should be provided in scope."
        assert session.is_active, "Session should be active inside scope."

    # Verify session is closed by checking `_is_active`
    assert not getattr(session, "_is_active", False), (
        "Session should be inactive after scope exits."
    )


def test_get_db_session(session_manager):
    """Test obtaining a database session."""
    session = session_manager.get_db_session()
    assert isinstance(session, Session)
    session.close()


def test_init_db(session_manager):
    """Test initializing the database."""
    assert session_manager.init_db() is True


def test_drop_db(session_manager):
    """Test dropping the database."""
    assert session_manager.drop_db() is True


def test_check_db_connection(session_manager):
    """Test if database connection check works."""
    session_manager.init_db()  # Ensure DB is initialized before checking
    assert session_manager.check_db_connection() is True, (
        "Database connection should be active."
    )


def test_get_session_factory_default(session_manager):
    """Test retrieving the default session factory."""
    session_factory = session_manager.get_session_factory()
    assert session_factory is not None, "Default session factory should not be None."
    assert callable(session_factory), "Session factory should be a callable."
    assert isinstance(session_factory(), Session), (
        "Session factory should return a valid SQLAlchemy session."
    )


def test_get_session_factory_custom(session_manager, session_factory):
    """Test retrieving a custom session factory."""
    custom_session_manager = SQLSessionManager(
        engine=session_manager.get_engine(), session_factory=session_factory
    )

    assert custom_session_manager.get_session_factory() is session_factory, (
        "Expected the provided session factory."
    )
    assert callable(custom_session_manager.get_session_factory()), (
        "Session factory should be a callable."
    )
    assert isinstance(
        custom_session_manager.get_session_factory()(),
        Session,
    ), "Custom session factory should return a valid SQLAlchemy session."
