"""Factory to create futures contracts."""

import datetime
import threading
from typing import Dict

from mxm_refdata.models.contracts.futures_contract import FuturesContract
from mxm_refdata.models.months import Month
from mxm_refdata.models.periods import Period, PeriodType
from mxm_refdata.models.products.futures_product import FuturesProduct
from mxm_refdata.trading_calendars.first_day_of_interest import (
    calculate_first_day_of_interest,
)
from mxm_refdata.trading_calendars.last_trading_day import calculate_last_trading_day
from mxm_refdata.trading_calendars.trading_calendar import TradingCalendar


class FuturesContractFactory:
    """Factory for generating and retrieving FuturesContract instances."""

    _instance = None  # Singleton instance
    _lock = threading.Lock()  # Lock for thread safety
    _cache: Dict[str, FuturesContract] = {}  # Cache for created contracts

    def __new__(cls) -> "FuturesContractFactory":
        """Ensures only one instance of FuturesContractFactory is created."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def create_contracts_for_product(
        self, product: FuturesProduct, available_periods: Dict[str, Period]
    ) -> list[FuturesContract]:
        """
        Create all FuturesContract objects for a given product using available periods.

        Args:
            product (FuturesProduct): The product for which contracts are created.
            available_periods (Dict[str, Period]): Dictionary of period_id -> Period instances.

        Returns:
            list[FuturesContract]: A list of valid FuturesContract objects.
        """
        contracts = []

        period_types = (
            product.period_types
            if isinstance(product.period_types, (list, tuple, set))
            else [product.period_types]
        )

        for period in available_periods.values():
            if period.period_type not in period_types:
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

    def clear_cache(self):
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
            start=datetime.date(1980, 1, 1),
            end=datetime.date(2046, 12, 31),
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
