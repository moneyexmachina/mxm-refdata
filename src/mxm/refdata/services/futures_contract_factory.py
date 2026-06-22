"""Factory to create futures contracts."""

from mxm.refdata.config import RefDataConfigData
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.months import Month
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct
from mxm.refdata.trading_calendars.first_day_of_interest import (
    calculate_first_day_of_interest,
)
from mxm.refdata.trading_calendars.last_trading_day import calculate_last_trading_day
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar


class FuturesContractFactory:
    """Factory for generating and retrieving FuturesContract instances."""

    def __init__(
        self,
    ) -> None:
        self._cache: dict[str, FuturesContract] = {}

    def create_contracts_for_product(
        self, product: FuturesProduct, available_periods: dict[str, Period]
    ) -> list[FuturesContract]:
        """
        Create all FuturesContract objects for a given product using available periods.

        Args:
            product (FuturesProduct): The product for which contracts are created.
            available_periods (Dict[str, Period]): Dictionary of period_id -> Period instances.

        Returns:
            list[FuturesContract]: A list of valid FuturesContract objects.
        """
        contracts: list[FuturesContract] = []

        for period in available_periods.values():
            if period.period_type not in product.period_types:
                continue  # Skip periods that don't match product requirements

            if self._is_valid_period(product, period):
                contract_id = self._create_contract_id(
                    product.product_id, period.period_id
                )

                if contract_id not in self._cache:
                    contract = self.create_contract(product, period)
                    self._cache[contract_id] = contract
                else:
                    contract = self._cache[contract_id]

                contracts.append(contract)

        return contracts

    def _is_valid_period(self, product: FuturesProduct, period: Period) -> bool:
        """
        Determine whether a period is valid for a given product based on valid_period_rule.

        Args:
            product (FuturesProduct): The product being evaluated.
            period (Period): The period being checked.

        Returns:
            bool: True if the period is valid for the product.
        """
        if period.period_type == PeriodType.MONTH:
            return (
                Month(period.first_date.month).as_cme_code in product.valid_period_rule
            )

        return True

    def clear_cache(self) -> None:
        """Clear the cache of created contracts."""
        self._cache.clear()

    def _create_contract_id(self, product_id: str, period_id: str) -> str:
        """Create a unique contract ID from product and period IDs."""
        return f"{product_id}.{period_id}"

    def create_contract(
        self, product: FuturesProduct, period: Period
    ) -> FuturesContract:
        """
        Create a FuturesContract object for a given product and period.

        Args:
            product (FuturesProduct): The product for which the contract is created.
            period (Period): The delivery period for the contract.

        Returns:
            FuturesContract: A valid FuturesContract object.
        """
        trading_calendar = TradingCalendar(
            product.trading_calendar,
        )

        last_trading_day = calculate_last_trading_day(
            product.product_id, period, trading_calendar
        )
        first_day_of_interest = calculate_first_day_of_interest(
            product.product_id, period, trading_calendar
        )

        return FuturesContract(
            product_id=product.product_id,
            period_id=period.period_id,
            contract_id=self._create_contract_id(product.product_id, period.period_id),
            contract_size=product.contract_size,
            currency=product.currency,
            unit=product.unit,
            trading_calendar=product.trading_calendar,
            first_day_of_interest=first_day_of_interest,
            last_trading_day=last_trading_day,
        )

    @classmethod
    def from_config_data(cls, config: RefDataConfigData) -> "FuturesContractFactory":
        """Construct a factory from fully materialised refdata configuration."""
        _ = config
        return cls()
