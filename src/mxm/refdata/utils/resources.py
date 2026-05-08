from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator

from mxm.refdata.utils.config import Config


@contextmanager
def futures_products_csv_path(cfg: Config) -> Iterator[Path]:
    """
    Yield a filesystem Path to the futures products CSV.

    If cfg.REFDATA_FUTURES_PRODUCTS_CSV_PATH is set, yield that path.
    Otherwise, yield a materialised path to the packaged CSV resource.

    The path may be backed by a temporary file; callers must consume it
    within the context manager.
    """
    override = cfg.REFDATA_FUTURES_PRODUCTS_CSV_PATH
    if override:
        yield Path(override)
        return

    resource = files("mxm_refdata").joinpath("data/futures_products.csv")
    with as_file(resource) as p:
        yield Path(p)
