"""Read-only public API façade for MXM reference data."""

from __future__ import annotations

from datetime import date

from mxm.refdata.composition import build_refdata
from mxm.refdata.models import FuturesContract, FuturesProduct, Period, PeriodType
from mxm.refdata.models.period_cycles import PeriodCycle, PeriodCycleMembership
from mxm.refdata.queries import RefDataLookupError
from mxm.refdata.runtime import RefData
from mxm.runtime import RuntimeContext


class RefDataAPI:
    """Read-only public API over a materialised RefData runtime graph."""

    def __init__(self, refdata: RefData) -> None:
        """Initialise the API from a materialised RefData runtime."""
        self._refdata = refdata

    @classmethod
    def from_runtime_context(cls, ctx: RuntimeContext) -> RefDataAPI:
        """Construct a read-only API from a resolved RuntimeContext."""
        return cls(build_refdata(ctx))

    def check_ready(self) -> None:
        """Check whether the refdata database is initialised and populated."""
        self._refdata.check_ready()

    def maybe_get_contract_by_id(self, contract_id: str) -> FuturesContract | None:
        """Retrieve a futures contract by contract ID, if available."""
        return self._refdata.maybe_get_contract_by_id(contract_id)

    def get_contract_by_id(self, contract_id: str) -> FuturesContract:
        """Retrieve a futures contract by contract ID, enforcing existence."""
        return self._refdata.get_contract_by_id(contract_id)

    def get_contracts_by_id(self, contract_ids: list[str]) -> list[FuturesContract]:
        """Retrieve futures contracts by ID, preserving input order."""
        return self._refdata.get_contracts_by_id(contract_ids)

    def get_active_contracts(
        self,
        as_of_date: date,
        *,
        product_id: str | None = None,
        product_ids: list[str] | None = None,
    ) -> list[FuturesContract]:
        """Retrieve contracts active on a given date."""
        return self._refdata.get_active_contracts(
            as_of_date,
            product_id=product_id,
            product_ids=product_ids,
        )

    def get_all_products(self) -> list[FuturesProduct]:
        """Retrieve all futures products."""
        return self._refdata.get_all_products()

    def get_product_by_id(self, product_id: str) -> FuturesProduct:
        """Retrieve a futures product by product ID, enforcing existence."""
        return self._refdata.get_product_by_id(product_id)

    def get_contracts_for_product(
        self,
        product_id: str,
        *,
        period_type: PeriodType | str | None = None,
    ) -> list[FuturesContract]:
        """Retrieve all contracts for a futures product."""
        return self._refdata.get_contracts_for_product(
            product_id,
            period_type=period_type,
        )

    def get_contracts_for_date(self, target_date: date) -> list[FuturesContract]:
        """Retrieve contracts whose delivery period contains a given date."""
        return self._refdata.get_contracts_for_date(target_date)

    def get_periods(self) -> list[Period]:
        """Retrieve all available periods."""
        return self._refdata.get_periods()

    def get_period_by_id(self, period_id: str) -> Period | None:
        """Retrieve a period by period ID, if present."""
        return self._refdata.get_period_by_id(period_id)

    def get_periods_by_id(self, period_ids: list[str]) -> list[Period]:
        """Retrieve periods by period ID, preserving input order."""
        return self._refdata.get_periods_by_id(period_ids)

    def get_cycles(self) -> list[PeriodCycle]:
        """Retrieve all available period cycles."""
        return self._refdata.get_cycles()

    def get_cycle_by_id(self, cycle_id: str) -> PeriodCycle | None:
        """Retrieve a period cycle by cycle ID, if present."""
        return self._refdata.get_cycle_by_id(cycle_id)

    def get_cycle_memberships(self, cycle_id: str) -> list[PeriodCycleMembership]:
        """Retrieve memberships for a period cycle."""
        return self._refdata.get_cycle_memberships(cycle_id)

    def get_cycle_elements(
        self,
        period_ids: list[str],
        *,
        cycle_id: str,
    ) -> dict[str, int]:
        """Map period IDs to cycle elements for a period cycle."""
        return self._refdata.get_cycle_elements(period_ids, cycle_id=cycle_id)

    def get_cycle_element(
        self,
        period_id: str,
        *,
        cycle_id: str,
    ) -> int | None:
        """Return one period's cycle element for a period cycle."""
        return self._refdata.get_cycle_element(period_id, cycle_id=cycle_id)


__all__ = [
    "RefDataAPI",
    "RefDataLookupError",
]
