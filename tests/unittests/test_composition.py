"""Tests for mxm-refdata composition root."""

from __future__ import annotations

from pathlib import Path
from typing import cast

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
