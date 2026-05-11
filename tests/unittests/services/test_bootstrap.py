"""Tests for refdata bootstrap policy and build helpers."""

from __future__ import annotations

from typing import ClassVar, cast

import pytest
from pytest import MonkeyPatch

from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.services import bootstrap
from mxm.refdata.services.bootstrap import (
    RefDataNotInitialisedError,
    build_refdata,
    ensure_refdata_ready,
    rebuild_refdata,
)
from mxm.refdata.utils.config import Config


class DummySQLSessionManager:
    def __init__(self) -> None:
        self.init_db_calls = 0

    def init_db(self) -> bool:
        self.init_db_calls += 1
        return True


class DummyRefDataService:
    """Test double for RefDataService."""

    instances: ClassVar[list[DummyRefDataService]] = []

    def __init__(self, session_manager: SQLSessionManager) -> None:
        self.session_manager = session_manager
        self.reset_database_calls = 0
        self.setup_instruments_calls = 0
        self.setup_kwargs: dict[str, object] | None = None
        DummyRefDataService.instances.append(self)

    def reset_database(self) -> None:
        self.reset_database_calls += 1

    def setup_instruments(
        self,
        *,
        csv_file_path: str | None = None,
        start_date: object | None = None,
        end_date: object | None = None,
    ) -> None:
        self.setup_instruments_calls += 1
        self.setup_kwargs = {
            "csv_file_path": csv_file_path,
            "start_date": start_date,
            "end_date": end_date,
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
    monkeypatch: MonkeyPatch,
) -> None:
    """build_refdata should initialise schema and populate instruments."""
    _patch_refdata_service(monkeypatch)

    build_refdata(
        session_manager=cast(SQLSessionManager, session_manager),
        csv_file_path="/tmp/products.csv",
    )
    assert session_manager.init_db_calls == 1

    service = DummyRefDataService.instances[0]
    assert service.session_manager is session_manager
    assert service.reset_database_calls == 0
    assert service.setup_instruments_calls == 1
    assert service.setup_kwargs == {
        "csv_file_path": "/tmp/products.csv",
        "start_date": None,
        "end_date": None,
    }


def test_rebuild_refdata_resets_database_then_sets_up_instruments(
    session_manager: DummySQLSessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """rebuild_refdata should destructively reset and repopulate instruments."""
    _patch_refdata_service(monkeypatch)

    rebuild_refdata(
        session_manager=cast(SQLSessionManager, session_manager),
        csv_file_path="/tmp/products.csv",
    )

    service = DummyRefDataService.instances[0]
    assert service.session_manager is session_manager
    assert service.reset_database_calls == 1
    assert service.setup_instruments_calls == 1
    assert service.setup_kwargs == {
        "csv_file_path": "/tmp/products.csv",
        "start_date": None,
        "end_date": None,
    }


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

    cfg = Config(REFDATA_DB_MODE="managed")

    ensure_refdata_ready(cast(SQLSessionManager, session_manager), cfg)
    assert session_manager.init_db_calls == 0
    assert DummyRefDataService.instances == []


def test_ensure_refdata_ready_raises_in_managed_mode_when_empty(
    session_manager: DummySQLSessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """ensure_refdata_ready should raise when DB is empty and mode is managed."""
    monkeypatch.setattr(bootstrap, "_db_has_any_products", _db_has_no_products)

    cfg = Config(REFDATA_DB_MODE="managed")

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

    cfg = Config(
        REFDATA_DB_MODE="buildable",
        REFDATA_FUTURES_PRODUCTS_CSV_PATH="/tmp/products.csv",
    )

    ensure_refdata_ready(cast(SQLSessionManager, session_manager), cfg)
    assert session_manager.init_db_calls == 1

    service = DummyRefDataService.instances[0]
    assert service.session_manager is session_manager
    assert service.reset_database_calls == 0
    assert service.setup_instruments_calls == 1
    assert service.setup_kwargs == {
        "csv_file_path": "/tmp/products.csv",
        "start_date": None,
        "end_date": None,
    }
