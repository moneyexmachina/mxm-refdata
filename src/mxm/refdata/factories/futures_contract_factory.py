"""Factory for creating futures contracts."""

from __future__ import annotations

from mxm.config import MXMConfig
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.months import Month
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct
from mxm.refdata.models.products.futures_product_spec import ContractRules
from mxm.refdata.trading_calendars.first_day_of_interest import (
    calculate_first_day_of_interest,
)
from mxm.refdata.trading_calendars.last_trading_day import (
    calculate_last_trading_day,
)
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


class FuturesContractFactory:
    """Factory for generating and interning FuturesContract instances.

    The factory is independent of product/specification storage.

    Callers must supply the FuturesProduct, its associated ContractRules,
    and the Period explicitly.
    """

    def __init__(self) -> None:
        """Initialise an empty contract cache."""

        self._cache: dict[str, FuturesContract] = {}

    def create_contracts_for_product(
        self,
        *,
        product: FuturesProduct,
        contract_rules: ContractRules,
        available_periods: dict[str, Period],
    ) -> list[FuturesContract]:
        """Create all valid contracts for a futures product.

        Args:
            product:
                Exchange-defined futures product.
            contract_rules:
                Structured rules used to derive contract lifecycle dates.
            available_periods:
                Mapping of period_id to available Period instances.

        Returns:
            Valid contracts in available-period iteration order.
        """

        contracts: list[FuturesContract] = []

        for period in available_periods.values():
            if period.period_type not in product.period_types:
                continue

            if not self._is_valid_period(
                product=product,
                period=period,
            ):
                continue

            contract_id = self._create_contract_id(
                product.product_id,
                period.period_id,
            )

            contract = self._cache.get(contract_id)

            if contract is None:
                contract = self.create_contract(
                    product=product,
                    contract_rules=contract_rules,
                    period=period,
                )
                self._cache[contract_id] = contract

            contracts.append(contract)

        return contracts

    def create_contract(
        self,
        *,
        product: FuturesProduct,
        contract_rules: ContractRules,
        period: Period,
    ) -> FuturesContract:
        """Create a futures contract for a product and period.

        Args:
            product:
                Exchange-defined futures product.
            contract_rules:
                Structured rules used to derive lifecycle dates.
            period:
                Delivery or expiry period for the contract.

        Returns:
            Constructed FuturesContract.
        """

        trading_calendar = TradingCalendar(
            product.trading_calendar,
        )

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
            contract_id=self._create_contract_id(
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

    def clear_cache(self) -> None:
        """Clear the cache of constructed contracts."""

        self._cache.clear()

    @staticmethod
    def _is_valid_period(
        *,
        product: FuturesProduct,
        period: Period,
    ) -> bool:
        """Return whether a period is valid for a product."""

        if period.period_type is PeriodType.MONTH:
            month_code = Month(
                period.first_date.month,
            ).as_cme_code

            return month_code in product.valid_period_rule

        return True

    @staticmethod
    def _create_contract_id(
        product_id: str,
        period_id: str,
    ) -> str:
        """Create a unique contract identifier."""

        return f"{product_id}.{period_id}"

    @classmethod
    def from_config(
        cls,
        config: MXMConfig,
    ) -> FuturesContractFactory:
        """Construct a factory from fully materialised configuration."""

        _ = config
        return cls()
