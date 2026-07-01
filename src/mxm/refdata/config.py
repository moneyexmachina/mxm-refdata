"""Configuration data structures for mxm-refdata."""

from __future__ import annotations

from importlib.resources import as_file, files
from typing import NotRequired, TypedDict

DEFAULT_REFDATA_DB_MODE = "buildable"
DEFAULT_CONTRACT_START_DATE = "1980-01-02"
DEFAULT_CONTRACT_END_DATE = "2046-12-31"

VALID_REFDATA_DB_MODES = frozenset({"buildable", "managed"})


class RefDataConfigInput(TypedDict):
    """Possibly partial resolved configuration input for mxm-refdata."""

    SQL_DB_URL: str
    REFDATA_DB_MODE: NotRequired[str]
    REFDATA_FUTURES_PRODUCTS_JSON_ROOT: NotRequired[str]
    REFDATA_CONTRACT_START_DATE: NotRequired[str]
    REFDATA_CONTRACT_END_DATE: NotRequired[str]


class RefDataConfigData(TypedDict):
    """Fully materialised configuration data required to construct mxm-refdata."""

    SQL_DB_URL: str
    REFDATA_DB_MODE: str
    REFDATA_FUTURES_PRODUCTS_JSON_ROOT: str
    REFDATA_CONTRACT_START_DATE: str
    REFDATA_CONTRACT_END_DATE: str


# ---------------------------------------------------------------------
# NORMALISATION
# ---------------------------------------------------------------------


def normalise_refdata_config_data(
    config: RefDataConfigInput,
) -> RefDataConfigData:
    """Return fully materialised refdata configuration data.

    Optional input fields are filled with package defaults.
    The returned config is complete and suitable for constructing
    configured refdata services.
    """

    db_mode = config.get("REFDATA_DB_MODE", DEFAULT_REFDATA_DB_MODE)
    if db_mode not in VALID_REFDATA_DB_MODES:
        raise ValueError(
            "REFDATA_DB_MODE must be one of: "
            f"{sorted(VALID_REFDATA_DB_MODES)}. Got {db_mode!r}."
        )

    futures_products_json_root = config.get("REFDATA_FUTURES_PRODUCTS_JSON_ROOT")

    if futures_products_json_root is None:
        futures_products_json_root = _default_futures_products_json_root()

    return {
        "SQL_DB_URL": config["SQL_DB_URL"],
        "REFDATA_DB_MODE": db_mode,
        "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": futures_products_json_root,
        "REFDATA_CONTRACT_START_DATE": config.get(
            "REFDATA_CONTRACT_START_DATE",
            DEFAULT_CONTRACT_START_DATE,
        ),
        "REFDATA_CONTRACT_END_DATE": config.get(
            "REFDATA_CONTRACT_END_DATE",
            DEFAULT_CONTRACT_END_DATE,
        ),
    }


# ---------------------------------------------------------------------
# DEFAULT DATA SOURCE
# ---------------------------------------------------------------------


def _default_futures_products_json_root() -> str:
    """Return packaged fallback JSON root directory for bootstrap."""

    resource = files("mxm.refdata").joinpath("data/products/futures")
    with as_file(resource) as path:
        return str(path)
