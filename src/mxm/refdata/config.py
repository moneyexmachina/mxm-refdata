"""Configuration data structures for mxm-refdata."""

from __future__ import annotations

from importlib.resources import as_file, files
from typing import NotRequired, TypedDict

DEFAULT_REFDATA_DB_MODE = "buildable"
DEFAULT_FUTURES_PRODUCTS_CSV_PATH = "packaged"
DEFAULT_CONTRACT_START_DATE = "1980-01-02"
DEFAULT_CONTRACT_END_DATE = "2046-12-31"

VALID_REFDATA_DB_MODES = frozenset({"buildable", "managed"})


class RefDataConfigInput(TypedDict):
    """Possibly partial resolved configuration input for mxm-refdata."""

    SQL_DB_URL: str
    REFDATA_DB_MODE: NotRequired[str]
    REFDATA_FUTURES_PRODUCTS_CSV_PATH: NotRequired[str]
    REFDATA_CONTRACT_START_DATE: NotRequired[str]
    REFDATA_CONTRACT_END_DATE: NotRequired[str]


class RefDataConfigData(TypedDict):
    """Fully materialised configuration data required to construct mxm-refdata."""

    SQL_DB_URL: str
    REFDATA_DB_MODE: str
    REFDATA_FUTURES_PRODUCTS_CSV_PATH: str
    REFDATA_CONTRACT_START_DATE: str
    REFDATA_CONTRACT_END_DATE: str


def normalise_refdata_config_data(
    config: RefDataConfigInput,
) -> RefDataConfigData:
    """Return fully materialised refdata configuration data.

    Optional input fields are filled with package defaults. The returned config
    is complete and suitable for constructing configured refdata services.
    """
    db_mode = config.get("REFDATA_DB_MODE", DEFAULT_REFDATA_DB_MODE)
    if db_mode not in VALID_REFDATA_DB_MODES:
        raise ValueError(
            "REFDATA_DB_MODE must be one of: "
            f"{sorted(VALID_REFDATA_DB_MODES)}. Got {db_mode!r}."
        )
    futures_products_csv_path = config.get("REFDATA_FUTURES_PRODUCTS_CSV_PATH")

    if futures_products_csv_path is None:
        futures_products_csv_path = _default_futures_products_csv_path()

    return {
        "SQL_DB_URL": config["SQL_DB_URL"],
        "REFDATA_DB_MODE": db_mode,
        "REFDATA_FUTURES_PRODUCTS_CSV_PATH": futures_products_csv_path,
        "REFDATA_CONTRACT_START_DATE": config.get(
            "REFDATA_CONTRACT_START_DATE",
            DEFAULT_CONTRACT_START_DATE,
        ),
        "REFDATA_CONTRACT_END_DATE": config.get(
            "REFDATA_CONTRACT_END_DATE",
            DEFAULT_CONTRACT_END_DATE,
        ),
    }


# TODO(mxm-static-data-store):
# The packaged futures_products.csv fallback exists only to support the
# bootstrap phase of mxm-refdata.
#
# Long term, curated product definitions should live in a dedicated
# mxm-static-data-store package/repository and be materialised into
# RefDataConfigData during configuration resolution.
#
# Once mxm-static-data-store exists:
#   - remove packaged CSV fallback logic
#   - require a concrete products source path in RefDataConfigData
#   - keep mxm-refdata focused on refdata construction and querying
#     rather than static data distribution
def _default_futures_products_csv_path() -> str:
    resource = files("mxm.refdata").joinpath("data/futures_products.csv")
    with as_file(resource) as path:
        return str(path)
