"""Tests for mxm-refdata composition root."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.engine import make_url

from mxm.config import MXMConfig, make_subconfig
from mxm.refdata.composition import build_refdata
from mxm.runtime import RuntimeContext, RuntimePaths
from mxm.secrets import SecretsApi
from mxm.types import RuntimeIdentity


def _make_runtime_context(
    *,
    mocker: MockerFixture,
    refdata_config: dict[str, object],
    db_configs: dict[str, object] | None = None,
    secrets: Mock | None = None,
) -> RuntimeContext:
    """Construct a RuntimeContext for composition tests."""
    if secrets is None:
        secrets = mocker.Mock(spec=SecretsApi)

    return RuntimeContext(
        identity=RuntimeIdentity(
            app="mxm-refdata",
            environment="dev",
            machine="monolith",
            substrate="local-process",
            role="default",
        ),
        config=make_subconfig(
            {
                "mxm_refdata": refdata_config,
            }
        ),
        secrets=cast(SecretsApi, secrets),
        db_configs=cast(MXMConfig, db_configs or {}),
        paths=RuntimePaths(
            data_root=Path("/tmp/mxm/data"),
            artifact_root=Path("/tmp/mxm/artifacts"),
            export_root=Path("/tmp/mxm/exports"),
            log_root=Path("/tmp/mxm/logs"),
        ),
    )


@pytest.fixture
def sqlite_runtime_context(
    mocker: MockerFixture,
) -> RuntimeContext:
    """Provide a development RuntimeContext with an explicit SQLite URL."""
    return _make_runtime_context(
        mocker=mocker,
        refdata_config={
            "SQL_DB_URL": "sqlite:///:memory:",
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
            "REFDATA_CONTRACT_START_DATE": "2000-01-02",
            "REFDATA_CONTRACT_END_DATE": "2046-12-31",
        },
    )


@pytest.fixture
def postgresql_runtime_context(
    mocker: MockerFixture,
) -> RuntimeContext:
    """Provide an operational RuntimeContext with PostgreSQL configuration."""
    secrets = mocker.Mock(spec=SecretsApi)
    secrets.get_secret.return_value = "test-p@ssword:with/symbols"

    return _make_runtime_context(
        mocker=mocker,
        refdata_config={
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
            "REFDATA_CONTRACT_START_DATE": "2000-01-02",
            "REFDATA_CONTRACT_END_DATE": "2046-12-31",
        },
        db_configs={
            "operational_state": {
                "driver": "postgresql",
                "name": "mxm_dev",
                "user": "mxm_dev_app",
                "password_ref": "mxm_dev_db_password",
                "host": "localhost",
                "port": 5432,
            }
        },
        secrets=secrets,
    )


def test_build_refdata_wires_explicit_database_url_without_secret_access(
    sqlite_runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """An explicit URL should bypass runtime database and secret resolution."""
    config = cast(
        MXMConfig,
        {
            "SQL_DB_URL": "sqlite:///:memory:",
            "REFDATA_DB_MODE": "buildable",
        },
    )

    make_view = mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=config,
    )

    session_manager = mocker.Mock(name="session_manager")
    product_factory = mocker.Mock(name="product_factory")
    contract_factory = mocker.Mock(name="contract_factory")
    period_factory = mocker.Mock(name="period_factory")

    build_session_manager = mocker.patch(
        "mxm.refdata.composition.SQLSessionManager.from_db_url",
        return_value=session_manager,
    )
    build_product_factory = mocker.patch(
        "mxm.refdata.composition.FuturesProductFactory.from_config",
        return_value=product_factory,
    )
    build_contract_factory = mocker.patch(
        "mxm.refdata.composition.FuturesContractFactory.from_config",
        return_value=contract_factory,
    )
    period_factory_type = mocker.patch(
        "mxm.refdata.composition.PeriodFactory",
        return_value=period_factory,
    )

    refdata = build_refdata(sqlite_runtime_context)

    make_view.assert_called_once_with(
        sqlite_runtime_context.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )
    build_session_manager.assert_called_once_with("sqlite:///:memory:")
    build_product_factory.assert_called_once_with(config)
    build_contract_factory.assert_called_once_with(config)
    period_factory_type.assert_called_once_with()

    assert refdata.config is config
    assert refdata.session_manager is session_manager
    assert refdata.product_factory is product_factory
    assert refdata.contract_factory is contract_factory
    assert refdata.period_factory is period_factory

    secrets = sqlite_runtime_context.secrets
    assert secrets is not None
    assert cast(Mock, secrets).mock_calls == []


def test_build_refdata_resolves_operational_postgresql_database(
    postgresql_runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """Operational composition should resolve PostgreSQL through RuntimeContext."""
    config = cast(
        MXMConfig,
        {
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
        },
    )

    mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=config,
    )

    session_manager = mocker.Mock(name="session_manager")
    product_factory = mocker.Mock(name="product_factory")
    contract_factory = mocker.Mock(name="contract_factory")
    period_factory = mocker.Mock(name="period_factory")

    build_session_manager = mocker.patch(
        "mxm.refdata.composition.SQLSessionManager.from_db_url",
        return_value=session_manager,
    )
    mocker.patch(
        "mxm.refdata.composition.FuturesProductFactory.from_config",
        return_value=product_factory,
    )
    mocker.patch(
        "mxm.refdata.composition.FuturesContractFactory.from_config",
        return_value=contract_factory,
    )
    mocker.patch(
        "mxm.refdata.composition.PeriodFactory",
        return_value=period_factory,
    )

    refdata = build_refdata(postgresql_runtime_context)

    secrets = postgresql_runtime_context.secrets
    assert secrets is not None

    cast(Mock, secrets).get_secret.assert_called_once_with(
        "mxm_dev_db_password",
        identity=postgresql_runtime_context.identity,
    )

    build_session_manager.assert_called_once()
    database_url = make_url(build_session_manager.call_args.args[0])

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.username == "mxm_dev_app"
    assert database_url.password == "test-p@ssword:with/symbols"
    assert database_url.host == "localhost"
    assert database_url.port == 5432
    assert database_url.database == "mxm_dev"

    assert refdata.config is config
    assert refdata.session_manager is session_manager
    assert refdata.product_factory is product_factory
    assert refdata.contract_factory is contract_factory
    assert refdata.period_factory is period_factory


def test_build_refdata_requires_database_configuration(
    mocker: MockerFixture,
) -> None:
    """Composition should fail when neither database route is configured."""
    runtime_context = _make_runtime_context(
        mocker=mocker,
        refdata_config={
            "REFDATA_DB_MODE": "buildable",
        },
        db_configs={},
    )

    mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=cast(
            MXMConfig,
            {
                "REFDATA_DB_MODE": "buildable",
            },
        ),
    )

    with pytest.raises(RuntimeError, match="operational_state"):
        build_refdata(runtime_context)


def test_build_refdata_requires_resolvable_database_password(
    postgresql_runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """An unavailable configured password should fail explicitly."""
    secrets = postgresql_runtime_context.secrets
    assert secrets is not None
    cast(Mock, secrets).get_secret.return_value = None

    mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=cast(
            MXMConfig,
            {
                "REFDATA_DB_MODE": "buildable",
            },
        ),
    )

    build_session_manager = mocker.patch(
        "mxm.refdata.composition.SQLSessionManager.from_db_url",
    )

    with pytest.raises(RuntimeError, match="could not be resolved"):
        build_refdata(postgresql_runtime_context)

    build_session_manager.assert_not_called()


def test_build_refdata_propagates_persistence_construction_failure(
    sqlite_runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """Persistence construction failures should not be concealed."""
    config = cast(
        MXMConfig,
        {
            "SQL_DB_URL": "sqlite:///:memory:",
        },
    )

    mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=config,
    )
    mocker.patch(
        "mxm.refdata.composition.SQLSessionManager.from_db_url",
        side_effect=RuntimeError("persistence construction failed"),
    )

    with pytest.raises(
        RuntimeError,
        match="persistence construction failed",
    ):
        build_refdata(sqlite_runtime_context)
