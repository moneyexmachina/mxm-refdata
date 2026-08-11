"""Read-only capability for materialised MXM reference data."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from mxm.refdata.models import (
    FuturesContract,
    FuturesProduct,
    Period,
    PeriodType,
)
from mxm.refdata.models.period_cycles import (
    PeriodCycle,
    PeriodCycleMembership,
)
from mxm.refdata.sql.futures_contracts import (
    fetch_active_futures_contracts,
    fetch_futures_contracts_by_ids,
    fetch_futures_contracts_for_product,
)
from mxm.refdata.sql.futures_products import (
    fetch_futures_products,
    fetch_futures_products_by_ids,
)
from mxm.refdata.sql.period_cycles import (
    fetch_period_cycle_memberships_by_cycle_ids,
    fetch_period_cycle_memberships_for_periods,
    fetch_period_cycles,
    fetch_period_cycles_by_ids,
)
from mxm.refdata.sql.periods import (
    fetch_periods,
    fetch_periods_by_ids,
)
from mxm.refdata.sql.postgres import PostgresDatabase

__all__ = [
    "RefDataLookupError",
    "RefDataReader",
]


class RefDataLookupError(KeyError):
    """Raised when required materialised reference data cannot be found."""


class RefDataReader:
    """Read-only capability for materialised MXM reference data.

    ``RefDataReader`` owns transaction scope and consumer-facing read
    semantics over the plain-SQL PostgreSQL persistence boundary.

    The capability can be supplied independently to downstream applications
    such as ``mxm-moneymachine``.
    """

    def __init__(
        self,
        *,
        database: PostgresDatabase,
    ) -> None:
        """Initialise the reader from its PostgreSQL dependency."""

        self._database = database

    def maybe_get_contract_by_id(
        self,
        contract_id: str,
    ) -> FuturesContract | None:
        """Retrieve a futures contract by ID, if present."""

        with self._database.transaction() as connection:
            contracts = fetch_futures_contracts_by_ids(
                connection,
                schema=self._database.schema,
                contract_ids=(contract_id,),
            )

        return contracts.get(contract_id)

    def get_contract_by_id(
        self,
        contract_id: str,
    ) -> FuturesContract:
        """Retrieve a futures contract by ID, enforcing existence."""

        contract = self.maybe_get_contract_by_id(contract_id)

        if contract is None:
            raise RefDataLookupError(
                f"FuturesContract not found for contract_id={contract_id!r}. "
                "This indicates missing or incomplete reference data."
            )

        return contract

    def get_contracts_by_id(
        self,
        contract_ids: Sequence[str],
    ) -> list[FuturesContract]:
        """Retrieve futures contracts by ID, preserving input order.

        Missing IDs are omitted. Repeated requested IDs remain repeated in
        the returned list when the corresponding contract exists.
        """

        if not contract_ids:
            return []

        with self._database.transaction() as connection:
            contracts = fetch_futures_contracts_by_ids(
                connection,
                schema=self._database.schema,
                contract_ids=contract_ids,
            )

        return [
            contracts[contract_id]
            for contract_id in contract_ids
            if contract_id in contracts
        ]

    def get_active_contracts(
        self,
        as_of_date: date,
        *,
        product_id: str | None = None,
        product_ids: Sequence[str] | None = None,
    ) -> list[FuturesContract]:
        """Retrieve contracts active on a given date.

        Results are grouped by product and ordered within each product using
        the domain ordering of the contracts' delivery periods.
        """

        if product_id is not None and product_ids is not None:
            raise ValueError("Provide only one of product_id or product_ids, not both.")

        selected_product_ids: Sequence[str] | None

        if product_id is not None:
            selected_product_ids = (product_id,)
        else:
            selected_product_ids = product_ids

        if selected_product_ids is not None and not selected_product_ids:
            return []

        with self._database.transaction() as connection:
            contracts = fetch_active_futures_contracts(
                connection,
                schema=self._database.schema,
                as_of_date=as_of_date,
                product_ids=selected_product_ids,
            )

            periods = fetch_periods_by_ids(
                connection,
                schema=self._database.schema,
                period_ids=[contract.period_id for contract in contracts.values()],
            )

        return _order_contracts_by_period(
            contracts.values(),
            periods,
            group_by_product=True,
        )

    def get_products(
        self,
    ) -> list[FuturesProduct]:
        """Retrieve all futures products in stable product-ID order."""

        with self._database.transaction() as connection:
            products = fetch_futures_products(
                connection,
                schema=self._database.schema,
            )

        return sorted(
            products.values(),
            key=lambda product: product.product_id,
        )

    def get_product_by_id(
        self,
        product_id: str,
    ) -> FuturesProduct:
        """Retrieve a futures product by ID, enforcing existence."""

        with self._database.transaction() as connection:
            products = fetch_futures_products_by_ids(
                connection,
                schema=self._database.schema,
                product_ids=(product_id,),
            )

        product = products.get(product_id)

        if product is None:
            raise RefDataLookupError(
                f"FuturesProduct not found for product_id={product_id!r}. "
                "This indicates missing or incomplete reference data."
            )

        return product

    def get_contracts_for_product(
        self,
        product_id: str,
        *,
        period_type: PeriodType | str | None = None,
    ) -> list[FuturesContract]:
        """Retrieve contracts for one product in domain period order."""

        resolved_period_type = _resolve_period_type(period_type)

        with self._database.transaction() as connection:
            contracts = fetch_futures_contracts_for_product(
                connection,
                schema=self._database.schema,
                product_id=product_id,
                period_type=resolved_period_type,
            )

            periods = fetch_periods_by_ids(
                connection,
                schema=self._database.schema,
                period_ids=[contract.period_id for contract in contracts.values()],
            )

        return _order_contracts_by_period(
            contracts.values(),
            periods,
            group_by_product=False,
        )

    def get_periods(
        self,
    ) -> list[Period]:
        """Retrieve all available periods in domain period order."""

        with self._database.transaction() as connection:
            periods = fetch_periods(
                connection,
                schema=self._database.schema,
            )

        return sorted(periods.values())

    def get_period_by_id(
        self,
        period_id: str,
    ) -> Period | None:
        """Retrieve a period by ID, if present."""

        with self._database.transaction() as connection:
            periods = fetch_periods_by_ids(
                connection,
                schema=self._database.schema,
                period_ids=(period_id,),
            )

        return periods.get(period_id)

    def get_periods_by_id(
        self,
        period_ids: Sequence[str],
    ) -> list[Period]:
        """Retrieve periods by ID, preserving input order.

        Missing IDs are omitted. Repeated requested IDs remain repeated in
        the returned list when the corresponding period exists.
        """

        if not period_ids:
            return []

        with self._database.transaction() as connection:
            periods = fetch_periods_by_ids(
                connection,
                schema=self._database.schema,
                period_ids=period_ids,
            )

        return [periods[period_id] for period_id in period_ids if period_id in periods]

    def get_cycles(
        self,
    ) -> list[PeriodCycle]:
        """Retrieve all available period cycles in stable cycle-ID order."""

        with self._database.transaction() as connection:
            cycles = fetch_period_cycles(
                connection,
                schema=self._database.schema,
            )

        return sorted(
            cycles.values(),
            key=lambda cycle: cycle.cycle_id,
        )

    def get_cycle_by_id(
        self,
        cycle_id: str,
    ) -> PeriodCycle | None:
        """Retrieve a period cycle by ID, if present."""

        with self._database.transaction() as connection:
            cycles = fetch_period_cycles_by_ids(
                connection,
                schema=self._database.schema,
                cycle_ids=(cycle_id,),
            )

        return cycles.get(cycle_id)

    def get_cycle_memberships(
        self,
        cycle_id: str,
    ) -> list[PeriodCycleMembership]:
        """Retrieve memberships for one period cycle in cycle-position order."""

        with self._database.transaction() as connection:
            memberships = fetch_period_cycle_memberships_by_cycle_ids(
                connection,
                schema=self._database.schema,
                cycle_ids=(cycle_id,),
            )

        return sorted(
            memberships.values(),
            key=lambda membership: (
                membership.cycle_instance,
                membership.cycle_element,
                membership.period_id,
            ),
        )

    def get_cycle_elements(
        self,
        period_ids: Sequence[str],
        *,
        cycle_id: str,
    ) -> dict[str, int]:
        """Map selected period IDs to cycle elements.

        Requested periods that are not members of the selected cycle are
        absent from the returned mapping.
        """

        if not period_ids:
            return {}

        with self._database.transaction() as connection:
            memberships = fetch_period_cycle_memberships_for_periods(
                connection,
                schema=self._database.schema,
                cycle_id=cycle_id,
                period_ids=period_ids,
            )

        return {
            membership.period_id: membership.cycle_element
            for membership in sorted(
                memberships.values(),
                key=lambda membership: membership.period_id,
            )
        }

    def get_cycle_element(
        self,
        period_id: str,
        *,
        cycle_id: str,
    ) -> int | None:
        """Return one period's cycle element, if present."""

        elements = self.get_cycle_elements(
            (period_id,),
            cycle_id=cycle_id,
        )

        return elements.get(period_id)


def _order_contracts_by_period(
    contracts: Iterable[FuturesContract],
    periods: Mapping[str, Period],
    *,
    group_by_product: bool,
) -> list[FuturesContract]:
    """Order contracts using the domain ordering of their delivery periods.

    Contract ID provides deterministic ordering between contracts whose
    periods compare equivalently. When requested, product ID provides the
    outer grouping.

    Every persisted contract is expected to reference a materialised period.
    Missing referenced periods indicate inconsistent reference-data state.
    """

    ordered_contracts = list(contracts)

    missing_period_ids = sorted(
        {
            contract.period_id
            for contract in ordered_contracts
            if contract.period_id not in periods
        }
    )

    if missing_period_ids:
        raise RefDataLookupError(
            "Materialised futures contracts reference missing periods: "
            f"{missing_period_ids!r}"
        )

    # Python sorting is stable. Apply the least significant deterministic
    # ordering first, then the semantic Period ordering, and finally the
    # optional product grouping.
    ordered_contracts.sort(
        key=lambda contract: contract.contract_id,
    )
    ordered_contracts.sort(
        key=lambda contract: periods[contract.period_id],
    )

    if group_by_product:
        ordered_contracts.sort(
            key=lambda contract: contract.product_id,
        )

    return ordered_contracts


def _resolve_period_type(
    period_type: PeriodType | str | None,
) -> PeriodType | None:
    """Resolve optional consumer-facing period-type input."""

    if period_type is None:
        return None

    if isinstance(period_type, PeriodType):
        return period_type

    try:
        return PeriodType(period_type)
    except ValueError as err:
        raise ValueError(f"Unknown period_type {period_type!r}") from err
