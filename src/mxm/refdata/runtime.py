"""Runtime façade for MXM reference data."""

from __future__ import annotations

from datetime import date

from mxm.config import MXMConfig
from mxm.refdata import diagnostics, materialisation, queries
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.diagnostics import SmokeCheckReport
from mxm.refdata.factories import (
    FuturesContractFactory,
    FuturesProductFactory,
    PeriodFactory,
)
from mxm.refdata.models import FuturesContract, FuturesProduct, Period, PeriodType
from mxm.refdata.models.period_cycles import PeriodCycle, PeriodCycleMembership
from mxm.refdata.utils.cache_manager import CacheManager


class RefData:
    """Materialised runtime object graph for MXM reference data.

    The class owns resolved runtime dependencies and exposes the package's
    outward-facing operations as a stable façade. Implementation logic lives in
    dedicated modules such as ``materialisation``, ``queries``, and
    ``diagnostics``.
    """

    def __init__(
        self,
        *,
        config: MXMConfig,
        session_manager: SQLSessionManager,
        product_factory: FuturesProductFactory,
        contract_factory: FuturesContractFactory,
        period_factory: PeriodFactory,
    ) -> None:
        """Initialise the runtime façade from explicit dependencies."""
        self.config = config
        self.session_manager = session_manager
        self.product_factory = product_factory
        self.contract_factory = contract_factory
        self.period_factory = period_factory
        self.cache: CacheManager[object] = CacheManager(maxsize=10000)

    def build(self) -> None:
        """Build the refdata database without first dropping existing tables."""
        materialisation.build_refdata(self)

    def rebuild(self) -> None:
        """Destructively rebuild the refdata database."""
        materialisation.rebuild_refdata(self)

    def ensure_ready(self) -> None:
        """Ensure the refdata database is initialised and populated."""
        materialisation.ensure_refdata_ready(self)

    def check_ready(self) -> None:
        """Check whether the refdata database is initialised and populated."""
        queries.check_refdata_ready(self)

    def setup_instruments(
        self,
        *,
        json_root: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        """Materialise periods, period cycles, products, and contracts."""
        materialisation.setup_instruments(
            self,
            json_root=json_root,
            start_date=start_date,
            end_date=end_date,
        )

    def initialise_futures_products(
        self,
        *,
        json_root: str | None = None,
    ) -> None:
        """Initialise futures products from the configured JSON source."""
        materialisation.initialise_futures_products(self, json_root=json_root)

    def initialise_periods(
        self,
        *,
        start_date: date,
        end_date: date,
        period_types: list[PeriodType] | None = None,
    ) -> None:
        """Initialise calendar periods for the requested range."""
        materialisation.initialise_periods(
            self,
            start_date=start_date,
            end_date=end_date,
            period_types=period_types,
        )

    def initialise_period_cycles(self) -> None:
        """Initialise canonical period cycles and cycle memberships."""
        materialisation.initialise_period_cycles(self)

    def initialise_futures_contracts(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> None:
        """Initialise futures contracts from stored products and periods."""
        materialisation.initialise_futures_contracts(
            self,
            start_date=start_date,
            end_date=end_date,
        )

    def smokecheck(self) -> SmokeCheckReport:
        """Run operational smoke checks against the configured database."""
        return diagnostics.run_refdata_smokechecks(self)

    def maybe_get_contract_by_id(self, contract_id: str) -> FuturesContract | None:
        """Retrieve a futures contract by contract ID, if available."""
        return queries.maybe_get_contract_by_id(self, contract_id)

    def get_contract_by_id(self, contract_id: str) -> FuturesContract:
        """Retrieve a futures contract by contract ID, enforcing existence."""
        return queries.get_contract_by_id(self, contract_id)

    def get_contracts_by_id(self, contract_ids: list[str]) -> list[FuturesContract]:
        """Retrieve futures contracts by ID, preserving input order."""
        return queries.get_contracts_by_id(self, contract_ids)

    def get_active_contracts(
        self,
        as_of_date: date,
        *,
        product_id: str | None = None,
        product_ids: list[str] | None = None,
    ) -> list[FuturesContract]:
        """Retrieve contracts active on a given date."""
        return queries.get_active_contracts(
            self,
            as_of_date,
            product_id=product_id,
            product_ids=product_ids,
        )

    def get_all_products(self) -> list[FuturesProduct]:
        """Retrieve all futures products."""
        return queries.get_all_products(self)

    def get_product_by_id(self, product_id: str) -> FuturesProduct:
        """Retrieve a futures product by product ID, enforcing existence."""
        return queries.get_product_by_id(self, product_id)

    def get_contracts_for_product(
        self,
        product_id: str,
        *,
        period_type: PeriodType | str | None = None,
    ) -> list[FuturesContract]:
        """Retrieve all contracts for a futures product."""
        return queries.get_contracts_for_product(
            self,
            product_id,
            period_type=period_type,
        )

    def get_contracts_for_date(self, target_date: date) -> list[FuturesContract]:
        """Retrieve contracts whose delivery period contains a given date."""
        return queries.get_contracts_for_date(self, target_date)

    def get_periods(self) -> list[Period]:
        """Retrieve all available periods."""
        return queries.get_periods(self)

    def get_period_by_id(self, period_id: str) -> Period | None:
        """Retrieve a period by period ID, if present."""
        return queries.get_period_by_id(self, period_id)

    def get_periods_by_id(self, period_ids: list[str]) -> list[Period]:
        """Retrieve periods by period ID, preserving input order."""
        return queries.get_periods_by_id(self, period_ids)

    def get_cycles(self) -> list[PeriodCycle]:
        """Retrieve all available period cycles."""
        return queries.get_cycles(self)

    def get_cycle_by_id(self, cycle_id: str) -> PeriodCycle | None:
        """Retrieve a period cycle by cycle ID, if present."""
        return queries.get_cycle_by_id(self, cycle_id)

    def get_cycle_memberships(self, cycle_id: str) -> list[PeriodCycleMembership]:
        """Retrieve memberships for a period cycle."""
        return queries.get_cycle_memberships(self, cycle_id)

    def get_cycle_elements(
        self,
        period_ids: list[str],
        *,
        cycle_id: str,
    ) -> dict[str, int]:
        """Map period IDs to cycle elements for a period cycle."""
        return queries.get_cycle_elements(self, period_ids, cycle_id=cycle_id)

    def get_cycle_element(
        self,
        period_id: str,
        *,
        cycle_id: str,
    ) -> int | None:
        """Return one period's cycle element for a period cycle."""
        return queries.get_cycle_element(self, period_id, cycle_id=cycle_id)
