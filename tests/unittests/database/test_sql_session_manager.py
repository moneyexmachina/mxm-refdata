"""Test cases for the SQLSessionManager class."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mxm.refdata.database.sql_session_manager import SQLSessionManager

type SessionFactory = sessionmaker[Session]


@pytest.fixture(scope="session")
def db_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    """Create a persistent test database and ensure cleanup after tests."""
    test_db_path = tmp_path_factory.mktemp("sql") / "test_db.sqlite"
    engine = create_engine(f"sqlite:///{test_db_path}")

    yield engine

    engine.dispose()


@pytest.fixture(scope="module")
def session_factory(db_engine: Engine) -> SessionFactory:
    """Provide a session factory for testing."""
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture
def session_manager(
    db_engine: Engine,
    session_factory: SessionFactory,
) -> SQLSessionManager:
    """Provide an instance of SQLSessionManager for testing."""
    return SQLSessionManager(engine=db_engine, session_factory=session_factory)


def test_db_session_scope(session_manager: SQLSessionManager) -> None:
    """Test transactional scope within `db_session_scope`."""
    with session_manager.db_session_scope() as session:
        assert session is not None, "Session should be provided in scope."
        assert session.is_active, "Session should be active inside scope."


def test_get_db_session(session_manager: SQLSessionManager) -> None:
    """Test obtaining a database session."""
    session = session_manager.get_db_session()
    try:
        assert isinstance(session, Session)
    finally:
        session.close()


def test_init_db(session_manager: SQLSessionManager) -> None:
    """Test initializing the database."""
    assert session_manager.init_db() is True


def test_drop_db(session_manager: SQLSessionManager) -> None:
    """Test dropping the database."""
    assert session_manager.drop_db() is True


def test_check_db_connection(session_manager: SQLSessionManager) -> None:
    """Test if database connection check works."""
    session_manager.init_db()
    assert session_manager.check_db_connection() is True


def test_get_session_factory_default(session_manager: SQLSessionManager) -> None:
    """Test retrieving the default session factory."""
    factory = session_manager.get_session_factory()

    assert factory is not None, "Default session factory should not be None."
    assert callable(factory), "Session factory should be a callable."

    session = factory()
    try:
        assert isinstance(session, Session)
    finally:
        session.close()


def test_get_session_factory_custom(
    session_manager: SQLSessionManager,
    session_factory: SessionFactory,
) -> None:
    """Test retrieving a custom session factory."""
    custom_session_manager = SQLSessionManager(
        engine=session_manager.get_engine(),
        session_factory=session_factory,
    )

    factory = custom_session_manager.get_session_factory()

    assert factory is session_factory, "Expected the provided session factory."
    assert callable(factory), "Session factory should be a callable."

    session = factory()
    try:
        assert isinstance(session, Session)
    finally:
        session.close()
