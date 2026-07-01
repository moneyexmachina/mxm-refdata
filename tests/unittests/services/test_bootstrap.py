"""Tests for refdata bootstrap policy and build helpers."""

from __future__ import annotations

from typing import ClassVar, cast

import pytest
from pytest import MonkeyPatch

from mxm.refdata.config import RefDataConfigData
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.services import bootstrap
from mxm.refdata.services.bootstrap import (
    RefDataNotInitialisedError,
    build_refdata,
    ensure_refdata_ready,
    rebuild_refdata,
)


class DummySQLSessionManager:
    def __init__(self) -> None:
        self.init_db_calls = 0

    def init_db(self) -> bool:
        self.init_db_calls += 1
        return True


class DummyRefDataService:
    """Test double for RefDataService."""

    instances: ClassVar[list[DummyRefDataService]] = []

    def __init__(
        self,
        *,
        config: RefDataConfigData,
        session_manager: SQLSessionManager,
    ) -> None:
        self.config = config
        self.session_manager = session_manager
        self.reset_database_calls = 0
        self.setup_instruments_calls = 0
        DummyRefDataService.instances.append(self)

    @classmethod
    def from_config_data(
        cls,
        *,
        config: RefDataConfigData,
        session_manager: SQLSessionManager,
    ) -> DummyRefDataService:
        """Construct the dummy service from config data."""
        return cls(config=config, session_manager=session_manager)

    def reset_database(self) -> None:
        self.reset_database_calls += 1

    def setup_instruments(self) -> None:
        self.setup_instruments_calls += 1


@pytest.fixture(scope="module")
def refdata_config() -> RefDataConfigData:
    """Provide fully materialised refdata config for service tests."""

    return {
        "SQL_DB_URL": "sqlite:///:memory:",
        "REFDATA_DB_MODE": "buildable",
        "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
        "REFDATA_CONTRACT_START_DATE": "2000-01-01",
        "REFDATA_CONTRACT_END_DATE": "2045-12-31",
    }


@pytest.fixture(autouse=True)
def reset_dummy_refdata_service() -> None:
    """Clear DummyRefDataService instance tracking before each test."""
    DummyRefDataService.instances.clear()


@pytest.fixture
def session_manager() -> DummySQLSessionManager:
    """Return a mocked SQLSessionManager with the correct runtime type."""
    return DummySQLSessionManager()


def _patch_refdata_service(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mxm.refdata.services.ref_data_service.RefDataService",
        DummyRefDataService,
    )


def test_build_refdata_initialises_schema_and_sets_up_instruments(
    session_manager: DummySQLSessionManager,
    refdata_config: RefDataConfigData,
    monkeypatch: MonkeyPatch,
) -> None:
    """build_refdata should initialise schema and populate instruments."""
    _patch_refdata_service(monkeypatch)

    build_refdata(
        config=refdata_config,
        session_manager=cast(SQLSessionManager, session_manager),
    )
    assert session_manager.init_db_calls == 1

    service = DummyRefDataService.instances[0]
    assert service.session_manager is session_manager
    assert service.reset_database_calls == 0
    assert service.setup_instruments_calls == 1


def test_rebuild_refdata_resets_database_then_sets_up_instruments(
    session_manager: DummySQLSessionManager,
    refdata_config: RefDataConfigData,
    monkeypatch: MonkeyPatch,
) -> None:
    """rebuild_refdata should destructively reset and repopulate instruments."""
    _patch_refdata_service(monkeypatch)

    rebuild_refdata(
        config=refdata_config,
        session_manager=cast(SQLSessionManager, session_manager),
    )

    service = DummyRefDataService.instances[0]
    assert service.session_manager is session_manager
    assert service.reset_database_calls == 1
    assert service.setup_instruments_calls == 1


def _db_has_products(_: SQLSessionManager) -> bool:
    return True


def _db_has_no_products(_: SQLSessionManager) -> bool:
    return False


def test_ensure_refdata_ready_noops_when_products_exist(
    session_manager: DummySQLSessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """ensure_refdata_ready should do nothing when refdata is already populated."""
    monkeypatch.setattr(bootstrap, "_db_has_any_products", _db_has_products)
    cfg: RefDataConfigData = {
        "SQL_DB_URL": "sqlite:///:memory:",
        "REFDATA_DB_MODE": "managed",
        "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
        "REFDATA_CONTRACT_START_DATE": "1980-01-01",
        "REFDATA_CONTRACT_END_DATE": "2046-12-31",
    }

    ensure_refdata_ready(cast(SQLSessionManager, session_manager), cfg)
    assert session_manager.init_db_calls == 0
    assert DummyRefDataService.instances == []


def test_ensure_refdata_ready_raises_in_managed_mode_when_empty(
    session_manager: DummySQLSessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """ensure_refdata_ready should raise when DB is empty and mode is managed."""
    monkeypatch.setattr(bootstrap, "_db_has_any_products", _db_has_no_products)
    cfg: RefDataConfigData = {
        "SQL_DB_URL": "sqlite:///:memory:",
        "REFDATA_DB_MODE": "managed",
        "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
        "REFDATA_CONTRACT_START_DATE": "1980-01-01",
        "REFDATA_CONTRACT_END_DATE": "2046-12-31",
    }

    with pytest.raises(RefDataNotInitialisedError):
        ensure_refdata_ready(cast(SQLSessionManager, session_manager), cfg)
    assert session_manager.init_db_calls == 0
    assert DummyRefDataService.instances == []


def test_ensure_refdata_ready_builds_when_empty_and_buildable(
    session_manager: DummySQLSessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """ensure_refdata_ready should build refdata when DB is empty and buildable."""
    monkeypatch.setattr(bootstrap, "_db_has_any_products", _db_has_no_products)
    _patch_refdata_service(monkeypatch)
    cfg: RefDataConfigData = {
        "SQL_DB_URL": "sqlite:///:memory:",
        "REFDATA_DB_MODE": "buildable",
        "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
        "REFDATA_CONTRACT_START_DATE": "1980-01-01",
        "REFDATA_CONTRACT_END_DATE": "2046-12-31",
    }
    ensure_refdata_ready(cast(SQLSessionManager, session_manager), cfg)
    assert session_manager.init_db_calls == 1

    service = DummyRefDataService.instances[0]
    assert service.session_manager is session_manager
    assert service.reset_database_calls == 0
    assert service.setup_instruments_calls == 1
