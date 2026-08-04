"""Tests for mxm-refdata composition root."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from mxm.config import MXMConfig, make_subconfig
from mxm.refdata.composition import build_refdata
from mxm.refdata.runtime import RefData
from mxm.runtime import RuntimeContext, RuntimePaths
from mxm.secrets import SecretsApi
from mxm.types import RuntimeIdentity


@pytest.fixture
def runtime_context(mocker: MockerFixture) -> RuntimeContext:
    """Provide a minimal RuntimeContext with mxm_refdata configuration."""
    config = make_subconfig(
        {
            "mxm_refdata": {
                "SQL_DB_URL": "sqlite:///:memory:",
                "REFDATA_DB_MODE": "buildable",
                "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
                "REFDATA_CONTRACT_START_DATE": "2000-01-02",
                "REFDATA_CONTRACT_END_DATE": "2046-12-31",
            }
        }
    )

    return RuntimeContext(
        identity=RuntimeIdentity(
            app="mxm-refdata",
            environment="dev",
            machine="bridge",
            substrate="local-process",
            role="default",
        ),
        config=config,
        secrets=cast(SecretsApi, mocker.Mock(spec=SecretsApi)),
        db_configs=cast(MXMConfig, {}),
        paths=RuntimePaths(
            data_root=Path("/tmp/mxm/data"),
            artifact_root=Path("/tmp/mxm/artifacts"),
            export_root=Path("/tmp/mxm/exports"),
            log_root=Path("/tmp/mxm/logs"),
        ),
    )


def test_build_refdata_from_runtime_context(
    runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """build_refdata should compose a RefData runtime from RuntimeContext."""
    mocker.patch(
        ("mxm.refdata.factories.futures_product_factory.parse_futures_product_specs"),
        return_value=[],
    )
    refdata = build_refdata(runtime_context)

    assert isinstance(refdata, RefData)
    assert refdata.config["SQL_DB_URL"] == "sqlite:///:memory:"
    assert refdata.config["REFDATA_DB_MODE"] == "buildable"
    assert refdata.config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"] == "/tmp/products"
    assert refdata.config["REFDATA_CONTRACT_START_DATE"] == "2000-01-02"
    assert refdata.config["REFDATA_CONTRACT_END_DATE"] == "2046-12-31"
    assert refdata.session_manager is not None
    assert refdata.product_factory is not None
    assert refdata.contract_factory is not None
    assert refdata.period_factory is not None


def test_build_refdata_wires_dependencies_from_resolved_context(
    runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """build_refdata should construct each dependency from resolved config."""
    config = cast(
        MXMConfig,
        {
            "SQL_DB_URL": "postgresql://mxm_dev_app@example/mxm_dev",
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

    refdata = build_refdata(runtime_context)

    make_view.assert_called_once_with(
        runtime_context.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )
    build_session_manager.assert_called_once_with(config["SQL_DB_URL"])
    build_product_factory.assert_called_once_with(config)
    build_contract_factory.assert_called_once_with(config)
    period_factory_type.assert_called_once_with()

    assert refdata.config is config
    assert refdata.session_manager is session_manager
    assert refdata.product_factory is product_factory
    assert refdata.contract_factory is contract_factory
    assert refdata.period_factory is period_factory

    # Composition must not resolve secrets independently.
    secrets = runtime_context.secrets
    assert secrets is not None
    assert cast(Mock, secrets).mock_calls == []


def test_build_refdata_requires_explicit_database_url(
    runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """Missing persistence configuration should fail explicitly."""
    mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=cast(MXMConfig, {}),
    )

    with pytest.raises(KeyError, match="SQL_DB_URL"):
        build_refdata(runtime_context)


def test_build_refdata_propagates_persistence_construction_failure(
    runtime_context: RuntimeContext,
    mocker: MockerFixture,
) -> None:
    """Persistence construction failures should not be concealed."""
    config = cast(
        MXMConfig,
        {"SQL_DB_URL": "postgresql://mxm_dev_app@example/mxm_dev"},
    )
    mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=config,
    )
    mocker.patch(
        "mxm.refdata.composition.SQLSessionManager.from_db_url",
        side_effect=RuntimeError("persistence construction failed"),
    )

    with pytest.raises(RuntimeError, match="persistence construction failed"):
        build_refdata(runtime_context)
