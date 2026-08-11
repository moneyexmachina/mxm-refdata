"""Runtime façade for the MXM reference-data application."""

from __future__ import annotations

from mxm.config import MXMConfig
from mxm.refdata.diagnostics import (
    RefDataDiagnosticReport,
    run_refdata_diagnostics,
)
from mxm.refdata.materialisation import (
    build_refdata,
    rebuild_refdata,
)
from mxm.refdata.reader import RefDataReader
from mxm.refdata.sql.postgres import PostgresDatabase

__all__ = [
    "RefData",
]


class RefData:
    """Assembled runtime façade for the MXM reference-data application.

    ``RefData`` is the complete application capability produced by the
    composition root.

    Read-only reference-data access is exposed through ``reader`` so that the
    restricted ``RefDataReader`` capability can also be passed independently
    to downstream applications.

    Materialisation and diagnostics are exposed as application operations while
    their implementations remain in their dedicated capability modules.
    """

    def __init__(
        self,
        *,
        config: MXMConfig,
        database: PostgresDatabase,
        reader: RefDataReader,
    ) -> None:
        """Initialise one composed reference-data application."""

        self.config = config
        self.database = database
        self.reader = reader

    def build(self) -> None:
        """Materialise configured reference data non-destructively."""

        build_refdata(
            config=self.config,
            database=self.database,
        )

    def rebuild(self) -> None:
        """Destructively rematerialise the owned reference-data schema."""

        rebuild_refdata(
            config=self.config,
            database=self.database,
        )

    def diagnostics(self) -> RefDataDiagnosticReport:
        """Inspect the operational state without changing it."""

        return run_refdata_diagnostics(
            database=self.database,
            reader=self.reader,
        )
