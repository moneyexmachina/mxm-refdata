"""Pure generation of futures contracts."""

from __future__ import annotations

from collections.abc import Iterable

from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.months import Month
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct
from mxm.refdata.trading_calendars.first_day_of_interest import (
    calculate_first_day_of_interest,
)
from mxm.refdata.trading_calendars.last_trading_day import (
    calculate_last_trading_day,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar

__all__ = [
    "generate_futures_contract",
    "generate_futures_contracts",
]


def generate_futures_contracts(
    *,
    product: FuturesProduct,
    periods: Iterable[Period],
) -> list[FuturesContract]:
    """Generate all valid futures contracts for a product.

    Periods are considered in input order. A contract is generated when the
    period type is supported by the product and the period satisfies the
    product's valid-period rule.

    Args:
        product:
            Complete operational futures-product specification.
        periods:
            Available periods to consider, in desired output order.

    Returns:
        Generated immutable futures contracts in period input order.
    """

    trading_calendar = TradingCalendar(
        product.trading_calendar,
    )

    contracts: list[FuturesContract] = []

    for period in periods:
        if not _is_valid_period(
            product=product,
            period=period,
        ):
            continue

        contracts.append(
            _generate_futures_contract(
                product=product,
                period=period,
                trading_calendar=trading_calendar,
            )
        )

    return contracts


def generate_futures_contract(
    *,
    product: FuturesProduct,
    period: Period,
) -> FuturesContract:
    """Generate one futures contract for a product and period.

    This operation assumes that the caller has selected the desired period.
    Product-period eligibility is handled by ``generate_futures_contracts``
    when generating a product's complete contract set.

    Args:
        product:
            Complete operational futures-product specification.
        period:
            Delivery or expiry period for the contract.

    Returns:
        The generated immutable futures contract.
    """

    trading_calendar = TradingCalendar(
        product.trading_calendar,
    )

    return _generate_futures_contract(
        product=product,
        period=period,
        trading_calendar=trading_calendar,
    )


def _generate_futures_contract(
    *,
    product: FuturesProduct,
    period: Period,
    trading_calendar: TradingCalendar,
) -> FuturesContract:
    """Generate one contract using an already-constructed trading calendar."""

    contract_rules = product.contract_rules

    last_trading_day = calculate_last_trading_day(
        product_id=product.product_id,
        period=period,
        trading_calendar=trading_calendar,
        rule=contract_rules.last_trading_rule,
    )

    first_day_of_interest = calculate_first_day_of_interest(
        product_id=product.product_id,
        period=period,
        trading_calendar=trading_calendar,
        rule=contract_rules.first_day_of_interest_rule,
        last_trading_rule=contract_rules.last_trading_rule,
    )

    return FuturesContract(
        product_id=product.product_id,
        period_id=period.period_id,
        contract_id=_create_contract_id(
            product.product_id,
            period.period_id,
        ),
        contract_size=product.contract_size,
        currency=product.currency,
        unit=product.unit,
        trading_calendar=product.trading_calendar,
        first_day_of_interest=first_day_of_interest,
        last_trading_day=last_trading_day,
    )


def _is_valid_period(
    *,
    product: FuturesProduct,
    period: Period,
) -> bool:
    """Return whether a period can produce a contract for a product."""

    if period.period_type not in product.period_types:
        return False

    if period.period_type is PeriodType.MONTH:
        month_code = Month(
            period.first_date.month,
        ).as_cme_code

        return month_code in product.valid_period_rule

    return True


def _create_contract_id(
    product_id: str,
    period_id: str,
) -> str:
    """Construct the canonical futures-contract identifier."""

    return f"{product_id}.{period_id}"
