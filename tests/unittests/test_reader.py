"""Unit tests for the materialised reference-data reader capability."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import date
from typing import cast

import pytest
from psycopg import Connection
from pytest import MonkeyPatch

from mxm.refdata import reader as reader_module
from mxm.refdata.models import (
    FuturesContract,
    FuturesProduct,
    Period,
    PeriodType,
)
from mxm.refdata.models.currencies import Currency
from mxm.refdata.models.period_cycles import PeriodCycleMembership
from mxm.refdata.models.units import ProductUnit
from mxm.refdata.reader import (
    RefDataLookupError,
    RefDataReader,
)
from mxm.refdata.sql.postgres import (
    PostgresDatabase,
    PostgresRow,
)


class FakePostgresDatabase:
    """Minimal transaction provider for reader unit tests."""

    def __init__(
        self,
        *,
        schema: str = "refdata_test_abc",
    ) -> None:
        """Initialise the fake database."""

        self.schema = schema
        self.transaction_calls = 0
        self.connection = cast(
            Connection[PostgresRow],
            object(),
        )

    @contextmanager
    def transaction(
        self,
    ) -> Generator[Connection[PostgresRow]]:
        """Yield one opaque connection without implementing PostgreSQL."""

        self.transaction_calls += 1
        yield self.connection


def _reader() -> tuple[RefDataReader, FakePostgresDatabase]:
    """Construct a reader with a minimal fake database."""

    database = FakePostgresDatabase()

    reader = RefDataReader(
        database=cast(
            PostgresDatabase,
            database,
        ),
    )

    return (
        reader,
        database,
    )


def _period(
    period_id: str,
    period_type: PeriodType,
    first_date: date,
    last_date: date,
) -> Period:
    """Construct a representative period."""

    return Period(
        period_id=period_id,
        period_type=period_type,
        first_date=first_date,
        last_date=last_date,
    )


def _year_period(
    *,
    period_id: str = "2026",
) -> Period:
    """Construct a yearly period."""

    return _period(
        period_id,
        PeriodType.YEAR,
        date(2026, 1, 1),
        date(2026, 12, 31),
    )


def _quarter_period(
    *,
    period_id: str = "2026-Q1",
) -> Period:
    """Construct a quarterly period."""

    return _period(
        period_id,
        PeriodType.QUARTER,
        date(2026, 1, 1),
        date(2026, 3, 31),
    )


def _month_period(
    *,
    period_id: str = "2026-01",
) -> Period:
    """Construct a monthly period."""

    return _period(
        period_id,
        PeriodType.MONTH,
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def _contract(
    *,
    product_id: str = "PRODUCT_A",
    period_id: str = "2026-01",
) -> FuturesContract:
    """Construct a representative futures contract."""

    return FuturesContract(
        contract_id=f"{product_id}.{period_id}",
        product_id=product_id,
        period_id=period_id,
        contract_size=100.0,
        unit=ProductUnit.TROY_OUNCE,
        currency=Currency.USD,
        trading_calendar="CME",
        first_day_of_interest=date(2025, 1, 1),
        last_trading_day=date(2026, 12, 31),
    )


def _membership(
    *,
    period_id: str,
    cycle_element: int,
    cycle_instance: int = 2026,
    cycle_id: str = "CALENDAR_MONTHS",
) -> PeriodCycleMembership:
    """Construct a representative period-cycle membership."""

    return PeriodCycleMembership(
        cycle_id=cycle_id,
        period_id=period_id,
        cycle_instance=cycle_instance,
        cycle_element=cycle_element,
    )


# ---------------------------------------------------------------------------
# Lookup policy
# ---------------------------------------------------------------------------


def test_contract_lookup_distinguishes_optional_and_required_missing_values(
    monkeypatch: MonkeyPatch,
) -> None:
    """Optional lookup returns None while required lookup raises."""

    def fake_fetch_futures_contracts_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        contract_ids: Sequence[str],
    ) -> dict[str, FuturesContract]:
        del connection, schema, contract_ids
        return {}

    monkeypatch.setattr(
        reader_module,
        "fetch_futures_contracts_by_ids",
        fake_fetch_futures_contracts_by_ids,
    )

    reader, _ = _reader()

    assert reader.maybe_get_contract_by_id("MISSING") is None

    with pytest.raises(
        RefDataLookupError,
        match=r"FuturesContract not found.*MISSING",
    ):
        reader.get_contract_by_id("MISSING")


def test_product_lookup_requires_product_to_exist(
    monkeypatch: MonkeyPatch,
) -> None:
    """Required product lookup raises when persistence returns no product."""

    def fake_fetch_futures_products_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        product_ids: Sequence[str],
    ) -> dict[str, FuturesProduct]:
        del connection, schema, product_ids
        return {}

    monkeypatch.setattr(
        reader_module,
        "fetch_futures_products_by_ids",
        fake_fetch_futures_products_by_ids,
    )

    reader, _ = _reader()

    with pytest.raises(
        RefDataLookupError,
        match=r"FuturesProduct not found.*MISSING_PRODUCT",
    ):
        reader.get_product_by_id("MISSING_PRODUCT")


# ---------------------------------------------------------------------------
# Ordered multi-ID lookup semantics
# ---------------------------------------------------------------------------


def test_contracts_by_id_preserves_input_order_duplicates_and_omits_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    """Contract multi-lookup reconstructs the caller's requested sequence."""

    first = _contract(
        period_id="2026-01",
    )
    second = _contract(
        period_id="2026-02",
    )

    def fake_fetch_futures_contracts_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        contract_ids: Sequence[str],
    ) -> dict[str, FuturesContract]:
        del connection, schema, contract_ids

        return {
            first.contract_id: first,
            second.contract_id: second,
        }

    monkeypatch.setattr(
        reader_module,
        "fetch_futures_contracts_by_ids",
        fake_fetch_futures_contracts_by_ids,
    )

    reader, _ = _reader()

    contracts = reader.get_contracts_by_id(
        [
            second.contract_id,
            "MISSING",
            first.contract_id,
            second.contract_id,
        ]
    )

    assert contracts == [
        second,
        first,
        second,
    ]


def test_periods_by_id_preserves_input_order_duplicates_and_omits_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    """Period multi-lookup reconstructs the caller's requested sequence."""

    year = _year_period()
    month = _month_period()

    def fake_fetch_periods_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        period_ids: Sequence[str],
    ) -> dict[str, Period]:
        del connection, schema, period_ids

        return {
            year.period_id: year,
            month.period_id: month,
        }

    monkeypatch.setattr(
        reader_module,
        "fetch_periods_by_ids",
        fake_fetch_periods_by_ids,
    )

    reader, _ = _reader()

    periods = reader.get_periods_by_id(
        [
            month.period_id,
            "MISSING",
            year.period_id,
            month.period_id,
        ]
    )

    assert periods == [
        month,
        year,
        month,
    ]


# ---------------------------------------------------------------------------
# Input semantics
# ---------------------------------------------------------------------------


def test_active_contracts_rejects_product_id_and_product_ids_together() -> None:
    """Single-product and multi-product filters are mutually exclusive."""

    reader, database = _reader()

    with pytest.raises(
        ValueError,
        match=r"only one of product_id or product_ids",
    ):
        reader.get_active_contracts(
            date(2026, 1, 15),
            product_id="PRODUCT_A",
            product_ids=["PRODUCT_B"],
        )

    assert database.transaction_calls == 0


def test_contracts_for_product_resolves_period_type_string(
    monkeypatch: MonkeyPatch,
) -> None:
    """Consumer-facing period-type values resolve to the domain enum."""

    captured_period_type: PeriodType | None = None

    def fake_fetch_futures_contracts_for_product(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        product_id: str,
        period_type: PeriodType | None = None,
    ) -> dict[str, FuturesContract]:
        nonlocal captured_period_type

        del connection, schema, product_id
        captured_period_type = period_type

        return {}

    def fake_fetch_periods_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        period_ids: Sequence[str],
    ) -> dict[str, Period]:
        del connection, schema, period_ids
        return {}

    monkeypatch.setattr(
        reader_module,
        "fetch_futures_contracts_for_product",
        fake_fetch_futures_contracts_for_product,
    )
    monkeypatch.setattr(
        reader_module,
        "fetch_periods_by_ids",
        fake_fetch_periods_by_ids,
    )

    reader, _ = _reader()

    contracts = reader.get_contracts_for_product(
        "PRODUCT_A",
        period_type="month",
    )

    assert contracts == []
    assert captured_period_type is PeriodType.MONTH


# ---------------------------------------------------------------------------
# Domain contract ordering
# ---------------------------------------------------------------------------


def test_contracts_for_product_uses_period_domain_ordering(
    monkeypatch: MonkeyPatch,
) -> None:
    """Contract ordering follows Period.__lt__, not persistence ordering."""

    year = _year_period()
    quarter = _quarter_period()
    month = _month_period()

    year_contract = _contract(
        period_id=year.period_id,
    )
    quarter_contract = _contract(
        period_id=quarter.period_id,
    )
    month_contract = _contract(
        period_id=month.period_id,
    )

    def fake_fetch_futures_contracts_for_product(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        product_id: str,
        period_type: PeriodType | None = None,
    ) -> dict[str, FuturesContract]:
        del connection, schema, product_id, period_type

        # Deliberately opposite to the domain ordering.
        return {
            month_contract.contract_id: month_contract,
            quarter_contract.contract_id: quarter_contract,
            year_contract.contract_id: year_contract,
        }

    def fake_fetch_periods_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        period_ids: Sequence[str],
    ) -> dict[str, Period]:
        del connection, schema, period_ids

        return {
            month.period_id: month,
            year.period_id: year,
            quarter.period_id: quarter,
        }

    monkeypatch.setattr(
        reader_module,
        "fetch_futures_contracts_for_product",
        fake_fetch_futures_contracts_for_product,
    )
    monkeypatch.setattr(
        reader_module,
        "fetch_periods_by_ids",
        fake_fetch_periods_by_ids,
    )

    reader, _ = _reader()

    contracts = reader.get_contracts_for_product(
        "PRODUCT_A",
    )

    assert contracts == [
        year_contract,
        quarter_contract,
        month_contract,
    ]


def test_active_contracts_group_by_product_then_use_period_ordering(
    monkeypatch: MonkeyPatch,
) -> None:
    """Active contracts group by product and use domain order within each."""

    year = _year_period()
    quarter = _quarter_period()
    month = _month_period()

    product_a_year = _contract(
        product_id="PRODUCT_A",
        period_id=year.period_id,
    )
    product_a_month = _contract(
        product_id="PRODUCT_A",
        period_id=month.period_id,
    )
    product_b_quarter = _contract(
        product_id="PRODUCT_B",
        period_id=quarter.period_id,
    )
    product_b_month = _contract(
        product_id="PRODUCT_B",
        period_id=month.period_id,
    )

    def fake_fetch_active_futures_contracts(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        as_of_date: date,
        product_ids: Sequence[str] | None = None,
    ) -> dict[str, FuturesContract]:
        del connection, schema, as_of_date, product_ids

        return {
            product_b_month.contract_id: product_b_month,
            product_a_month.contract_id: product_a_month,
            product_b_quarter.contract_id: product_b_quarter,
            product_a_year.contract_id: product_a_year,
        }

    def fake_fetch_periods_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        period_ids: Sequence[str],
    ) -> dict[str, Period]:
        del connection, schema, period_ids

        return {
            month.period_id: month,
            quarter.period_id: quarter,
            year.period_id: year,
        }

    monkeypatch.setattr(
        reader_module,
        "fetch_active_futures_contracts",
        fake_fetch_active_futures_contracts,
    )
    monkeypatch.setattr(
        reader_module,
        "fetch_periods_by_ids",
        fake_fetch_periods_by_ids,
    )

    reader, _ = _reader()

    contracts = reader.get_active_contracts(
        date(2026, 1, 15),
    )

    assert contracts == [
        product_a_year,
        product_a_month,
        product_b_quarter,
        product_b_month,
    ]


def test_contract_ordering_rejects_missing_referenced_period(
    monkeypatch: MonkeyPatch,
) -> None:
    """A persisted contract may not silently lose its referenced period."""

    contract = _contract(
        product_id="PRODUCT_A",
        period_id="MISSING_PERIOD",
    )

    def fake_fetch_futures_contracts_for_product(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        product_id: str,
        period_type: PeriodType | None = None,
    ) -> dict[str, FuturesContract]:
        del connection, schema, product_id, period_type

        return {
            contract.contract_id: contract,
        }

    def fake_fetch_periods_by_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        period_ids: Sequence[str],
    ) -> dict[str, Period]:
        del connection, schema, period_ids
        return {}

    monkeypatch.setattr(
        reader_module,
        "fetch_futures_contracts_for_product",
        fake_fetch_futures_contracts_for_product,
    )
    monkeypatch.setattr(
        reader_module,
        "fetch_periods_by_ids",
        fake_fetch_periods_by_ids,
    )

    reader, _ = _reader()

    with pytest.raises(
        RefDataLookupError,
        match=r"missing periods.*MISSING_PERIOD",
    ):
        reader.get_contracts_for_product(
            "PRODUCT_A",
        )


# ---------------------------------------------------------------------------
# Cycle semantics
# ---------------------------------------------------------------------------


def test_cycle_memberships_are_returned_in_cycle_position_order(
    monkeypatch: MonkeyPatch,
) -> None:
    """Cycle memberships are ordered by instance, element, and period ID."""

    january = _membership(
        period_id="2026-01",
        cycle_element=1,
    )
    february = _membership(
        period_id="2026-02",
        cycle_element=2,
    )
    december_previous_year = _membership(
        period_id="2025-12",
        cycle_instance=2025,
        cycle_element=12,
    )

    def fake_fetch_period_cycle_memberships_by_cycle_ids(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        cycle_ids: Sequence[str],
    ) -> dict[tuple[str, str], PeriodCycleMembership]:
        del connection, schema, cycle_ids

        return {
            (
                february.cycle_id,
                february.period_id,
            ): february,
            (
                january.cycle_id,
                january.period_id,
            ): january,
            (
                december_previous_year.cycle_id,
                december_previous_year.period_id,
            ): december_previous_year,
        }

    monkeypatch.setattr(
        reader_module,
        "fetch_period_cycle_memberships_by_cycle_ids",
        fake_fetch_period_cycle_memberships_by_cycle_ids,
    )

    reader, _ = _reader()

    memberships = reader.get_cycle_memberships(
        "CALENDAR_MONTHS",
    )

    assert memberships == [
        december_previous_year,
        january,
        february,
    ]


def test_cycle_element_projection_and_missing_element_semantics(
    monkeypatch: MonkeyPatch,
) -> None:
    """Cycle memberships project to elements and missing values remain absent."""

    january = _membership(
        period_id="2026-01",
        cycle_element=1,
    )
    march = _membership(
        period_id="2026-03",
        cycle_element=3,
    )

    memberships_by_period_id = {
        january.period_id: january,
        march.period_id: march,
    }

    def fake_fetch_period_cycle_memberships_for_periods(
        connection: Connection[PostgresRow],
        *,
        schema: str,
        cycle_id: str,
        period_ids: Sequence[str],
    ) -> dict[tuple[str, str], PeriodCycleMembership]:
        del connection, schema

        return {
            (
                cycle_id,
                period_id,
            ): memberships_by_period_id[period_id]
            for period_id in period_ids
            if period_id in memberships_by_period_id
        }

    monkeypatch.setattr(
        reader_module,
        "fetch_period_cycle_memberships_for_periods",
        fake_fetch_period_cycle_memberships_for_periods,
    )

    reader, _ = _reader()

    elements = reader.get_cycle_elements(
        [
            "2026-03",
            "MISSING",
            "2026-01",
        ],
        cycle_id="CALENDAR_MONTHS",
    )

    assert elements == {
        "2026-01": 1,
        "2026-03": 3,
    }

    assert (
        reader.get_cycle_element(
            "2026-01",
            cycle_id="CALENDAR_MONTHS",
        )
        == 1
    )

    assert (
        reader.get_cycle_element(
            "MISSING",
            cycle_id="CALENDAR_MONTHS",
        )
        is None
    )
