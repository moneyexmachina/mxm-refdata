"""Composition root for MXM reference data."""

from __future__ import annotations

from mxm.config import make_view
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.factories import (
    FuturesContractFactory,
    FuturesProductFactory,
    PeriodFactory,
)
from mxm.refdata.runtime import RefData
from mxm.runtime import RuntimeContext


def build_refdata(ctx: RuntimeContext) -> RefData:
    """Build the RefData runtime object graph from a resolved RuntimeContext."""
    config = make_view(
        ctx.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )

    session_manager = SQLSessionManager.from_db_url(config["SQL_DB_URL"])

    return RefData(
        config=config,
        session_manager=session_manager,
        product_factory=FuturesProductFactory.from_config(config),
        contract_factory=FuturesContractFactory.from_config(config),
        period_factory=PeriodFactory(),
    )
