"""Unit tests for the MXM reference-data composition root."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pytest_mock import MockerFixture

from mxm.config import MXMConfig, make_subconfig
from mxm.refdata.composition import build_refdata
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sql.postgres import PostgresDatabase
from mxm.runtime import RuntimeContext, RuntimePaths
from mxm.secrets import SecretsApi
from mxm.types import RuntimeIdentity


def _make_runtime_context(
    *,
    db_configs: dict[str, object] | None,
    secrets: SecretsApi | None,
) -> RuntimeContext:
    """Construct a representative mxm-refdata runtime context."""

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
                "mxm_refdata": {
                    "REFDATA_DB_MODE": "buildable",
                    "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
                    "REFDATA_CONTRACT_START_DATE": "2000-01-02",
                    "REFDATA_CONTRACT_END_DATE": "2046-12-31",
                },
            }
        ),
        secrets=secrets,
        db_configs=(
            cast(
                MXMConfig,
                db_configs,
            )
            if db_configs is not None
            else None
        ),
        paths=RuntimePaths(
            data_root=Path("/tmp/mxm/data"),
            artifact_root=Path("/tmp/mxm/artifacts"),
            export_root=Path("/tmp/mxm/exports"),
            log_root=Path("/tmp/mxm/logs"),
        ),
    )


def _operational_database_config(
    *,
    driver: str = "postgresql",
) -> dict[str, object]:
    """Return representative operational PostgreSQL configuration."""

    return {
        "operational_state": {
            "driver": driver,
            "name": "mxm_dev",
            "user": "mxm_dev_app",
            "password_ref": "mxm_dev_db_password",
            "host": "localhost",
            "port": 5432,
        },
    }


def test_build_refdata_assembles_operational_application(
    mocker: MockerFixture,
) -> None:
    """Composition resolves runtime inputs and assembles one RefData object."""

    secrets = mocker.Mock(
        spec=SecretsApi,
    )
    secrets.get_secret.return_value = "test-password"

    runtime_context = _make_runtime_context(
        db_configs=_operational_database_config(),
        secrets=cast(
            SecretsApi,
            secrets,
        ),
    )

    config = cast(
        MXMConfig,
        {
            "REFDATA_DB_MODE": "buildable",
            "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/tmp/products",
            "REFDATA_CONTRACT_START_DATE": "2000-01-02",
            "REFDATA_CONTRACT_END_DATE": "2046-12-31",
        },
    )

    make_view = mocker.patch(
        "mxm.refdata.composition.make_view",
        return_value=config,
    )

    database = mocker.Mock(
        spec=PostgresDatabase,
    )
    build_database = mocker.patch(
        "mxm.refdata.composition.PostgresDatabase.from_config",
        return_value=database,
    )

    reader = mocker.Mock(
        spec=RefDataReader,
    )
    reader_type = mocker.patch(
        "mxm.refdata.composition.RefDataReader",
        return_value=reader,
    )

    refdata = build_refdata(
        runtime_context,
    )

    make_view.assert_called_once_with(
        runtime_context.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )

    secrets.get_secret.assert_called_once_with(
        "mxm_dev_db_password",
        identity=runtime_context.identity,
    )

    build_database.assert_called_once_with(
        host="localhost",
        port=5432,
        database="mxm_dev",
        user="mxm_dev_app",
        password="test-password",
    )

    reader_type.assert_called_once_with(
        database=database,
    )

    assert refdata.config is config
    assert refdata.database is database
    assert refdata.reader is reader


def test_build_refdata_requires_database_configuration(
    mocker: MockerFixture,
) -> None:
    """Composition requires runtime database configuration."""

    secrets = mocker.Mock(
        spec=SecretsApi,
    )

    runtime_context = _make_runtime_context(
        db_configs=None,
        secrets=cast(
            SecretsApi,
            secrets,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="does not contain database configuration",
    ):
        build_refdata(
            runtime_context,
        )


def test_build_refdata_requires_operational_state_database(
    mocker: MockerFixture,
) -> None:
    """Composition requires the operational_state database configuration."""

    secrets = mocker.Mock(
        spec=SecretsApi,
    )

    runtime_context = _make_runtime_context(
        db_configs={},
        secrets=cast(
            SecretsApi,
            secrets,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="operational_state",
    ):
        build_refdata(
            runtime_context,
        )


def test_build_refdata_requires_secrets_api() -> None:
    """Composition requires a secrets capability for database credentials."""

    runtime_context = _make_runtime_context(
        db_configs=_operational_database_config(),
        secrets=None,
    )

    with pytest.raises(
        RuntimeError,
        match="configured secrets API",
    ):
        build_refdata(
            runtime_context,
        )


def test_build_refdata_rejects_non_postgresql_operational_database(
    mocker: MockerFixture,
) -> None:
    """The operational reference-data database must be PostgreSQL."""

    secrets = mocker.Mock(
        spec=SecretsApi,
    )

    runtime_context = _make_runtime_context(
        db_configs=_operational_database_config(
            driver="sqlite",
        ),
        secrets=cast(
            SecretsApi,
            secrets,
        ),
    )

    build_database = mocker.patch(
        "mxm.refdata.composition.PostgresDatabase.from_config",
    )

    with pytest.raises(
        RuntimeError,
        match="Unsupported operational database driver",
    ):
        build_refdata(
            runtime_context,
        )

    secrets.get_secret.assert_not_called()
    build_database.assert_not_called()


def test_build_refdata_requires_resolvable_database_password(
    mocker: MockerFixture,
) -> None:
    """Composition fails before persistence construction if the secret is absent."""

    secrets = mocker.Mock(
        spec=SecretsApi,
    )
    secrets.get_secret.return_value = None

    runtime_context = _make_runtime_context(
        db_configs=_operational_database_config(),
        secrets=cast(
            SecretsApi,
            secrets,
        ),
    )

    build_database = mocker.patch(
        "mxm.refdata.composition.PostgresDatabase.from_config",
    )

    with pytest.raises(
        RuntimeError,
        match="could not be resolved",
    ):
        build_refdata(
            runtime_context,
        )

    secrets.get_secret.assert_called_once_with(
        "mxm_dev_db_password",
        identity=runtime_context.identity,
    )

    build_database.assert_not_called()
