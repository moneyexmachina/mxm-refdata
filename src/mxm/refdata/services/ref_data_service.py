"""Service to create, update, and manage reference data in the database."""

import logging
from datetime import date

from sqlalchemy.orm import DeclarativeBase

from mxm.refdata.config import RefDataConfigData
from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.factories import (
    FuturesContractFactory,
    FuturesProductFactory,
    PeriodFactory,
)
from mxm.refdata.mappings import (
    futures_contract_to_orm,
    futures_product_from_orm,
    futures_product_to_orm,
    period_from_orm,
    period_to_orm,
)
from mxm.refdata.models import FuturesContract, FuturesProduct, Period, PeriodType
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.period_cycles import CycleInstanceKind
from mxm.refdata.trading_calendars.trading_calendar import TradingCalendar

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CYCLE_ID_CALENDAR_MONTHS = "CALENDAR_MONTHS"
CYCLE_ID_CALENDAR_QUARTERS = "CALENDAR_QUARTERS"
CONTRACT_RULE_LOOKBACK_YEARS = 2
CONTRACT_RULE_LOOKAHEAD_YEARS = 1


class RefDataService:
    """
    Manages reference data processes including initializing, updating, and resetting futures products.
    """

    def __init__(
        self,
        *,
        config: RefDataConfigData,
        session_manager: SQLSessionManager,
        product_factory: FuturesProductFactory | None = None,
        contract_factory: FuturesContractFactory | None = None,
        period_factory: PeriodFactory | None = None,
    ) -> None:
        """Initialise the service from explicit refdata dependencies."""
        self.config = config
        self.session_manager = session_manager
        self.product_factory = (
            product_factory or FuturesProductFactory.from_config_data(config)
        )
        self.contract_factory = (
            contract_factory or FuturesContractFactory.from_config_data(config)
        )
        self.period_factory = period_factory or PeriodFactory()

    def reset_database(self):
        """
        Reset the database by dropping and reinitializing all tables.
        WARNING: This will delete all existing data.
        """
        logger.warning("Resetting the database. This will delete ALL existing data.")
        self.session_manager.drop_db()
        self.session_manager.init_db()
        logger.info("Database successfully reset.")

    def _is_database_empty(self) -> bool:
        """
        Check if the database contains any data in any relevant tables.

        Returns:
            bool: True if all relevant tables are empty, False otherwise.
        """
        with self.session_manager.db_session_scope() as session:
            tables_to_check = [FuturesProductORM, FuturesContractORM, PeriodORM]

            for table in tables_to_check:
                if session.query(table).count() > 0:
                    return False  # At least one table is not empty

        return True  # All tables are empty

    def is_table_empty(self, orm_model: type[DeclarativeBase]) -> bool:
        """
        Check if a given ORM table is empty.

        Args:
            orm_model (Base): The SQLAlchemy ORM model representing the table.

        Returns:
            bool: True if the table is empty, False otherwise.
        """
        with self.session_manager.db_session_scope() as session:
            return session.query(orm_model).count() == 0

    def setup_instruments(
        self,
        json_root: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        """
        Perform a full instrument setup: initialise periods, products, and contracts.

        This method is a convenience function that ensures all required data is set up correctly.

        NOTE: initialisation expects boundary-aligned horizons.
        We filter to periods fully contained in [start_date, end_date] deliberately.
        Do not call this with arbitrary dates; use a separate overlap query for ad hoc ranges.
        Args:
            csv_file_path (Optional[str]): Path to the CSV file for futures products.
            start_date (Optional[date]): Start date for contract generation (default: today).
            end_date (Optional[date]): End date for contract generation (default: +1 year).
        """
        logging.info("Starting full instrument setup...")

        # Ensure we have a reasonable date range if not provided
        start_date = start_date or date.fromisoformat(
            self.config["REFDATA_CONTRACT_START_DATE"]
        )
        end_date = end_date or date.fromisoformat(
            self.config["REFDATA_CONTRACT_END_DATE"]
        )

        # Step 1: Initialise periods (YEAR, QUARTER, MONTH)
        self.initialise_periods(start_date=start_date, end_date=end_date)
        self.initialise_period_cycles()
        # Step 2: Initialise futures products from CSV
        self.initialise_futures_products(json_root=json_root)

        # Step 3: Generate and store contracts for each product
        self.initialise_futures_contracts(start_date=start_date, end_date=end_date)

        logging.info("Full instrument setup completed successfully.")

    def initialise_futures_products(self, json_root: str | None = None) -> None:
        """
        Initialize the database with futures products from JSON source.

        Args:
            json_root (Optional[str]):
                Path to the JSON directory containing futures product definitions.
                If None, uses the default path from config.

        Raises:
            ValueError: If the database is not empty.
        """

        if not self.is_table_empty(FuturesProductORM):
            raise ValueError(
                "Database already contains products. Run `reset_database()` first."
            )

        root = json_root or self.config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"]

        products = self.product_factory.initialise_from_json(root)

        with self.session_manager.db_session_scope() as session:
            for product in products:
                product_orm = futures_product_to_orm(product)
                session.add(product_orm)

    def initialise_periods(
        self,
        start_date: date,
        end_date: date,
        period_types: list[PeriodType] | None = None,
    ) -> None:
        """
        Initialise periods for a given date range and set of period types.

        Ensures that all required periods exist **before** any contracts reference them.

        Args:
            start_date (date): The start date for period creation.
            end_date (date): The end date for period creation.
            period_types (Optional[list[PeriodType]]): List of period types to create.
                Defaults to YEAR, QUARTER, and MONTH.
        """
        if not self.is_table_empty(PeriodORM):
            raise ValueError(
                "Database already contains periods. Run `reset_database()` first."
            )

        if period_types is None:
            period_types = [PeriodType.YEAR, PeriodType.QUARTER, PeriodType.MONTH]

        with self.session_manager.db_session_scope() as session:
            existing_period_ids = {p.period_id for p in session.query(PeriodORM).all()}

        new_periods: list[Period] = []
        for period_type in period_types:
            generated_periods = self.period_factory.get_periods_in_range(
                start_date, end_date, period_type
            )

            for period in generated_periods:
                if period.period_id not in existing_period_ids:
                    new_periods.append(period)

        if new_periods:
            with self.session_manager.db_session_scope() as session:
                for period in new_periods:
                    session.add(
                        period_to_orm(period)
                    )  # Convert & store only new periods

    def initialise_futures_contracts(self, start_date: date, end_date: date) -> None:
        """
        Initialize futures contracts using existing products and periods in the database.

        Args:
            start_date (date): The start date for contract generation.
            end_date (date): The end date for contract generation.
        """

        with self.session_manager.db_session_scope() as session:
            products = [
                futures_product_from_orm(product_orm)
                for product_orm in session.query(FuturesProductORM).all()
            ]
            if not products:
                raise ValueError(
                    "No products found in the database. "
                    "Run initialise_futures_products() first."
                )

            self._validate_calendar_coverage_for_contract_initialisation(
                products=products,
                start_date=start_date,
                end_date=end_date,
            )

            with self.session_manager.db_session_scope() as session:
                periods = {
                    p.period_id: period_from_orm(p)
                    for p in session.query(PeriodORM)
                    .filter(
                        PeriodORM.first_date >= start_date,
                        PeriodORM.last_date <= end_date,
                    )
                    .all()
                }
                if not periods:
                    raise ValueError(
                        "No periods found in the database. Run initialise_periods() first."
                    )
        # Generate contracts outside of session
        contracts: list[FuturesContract] = []
        for product in products:
            product_contracts = self.contract_factory.create_contracts_for_product(
                product, periods
            )
            contracts.extend(product_contracts)

        # Store contracts in the database
        with self.session_manager.db_session_scope() as session:
            for contract in contracts:
                session.add(futures_contract_to_orm(contract=contract))

    def initialise_period_cycles(self) -> None:
        """
        Initialise canonical PeriodCycles and PeriodCycleMemberships.

        Requires PeriodORM to already exist.
        """
        if not self.is_table_empty(PeriodCycleORM) or not self.is_table_empty(
            PeriodCycleMembershipORM
        ):
            raise ValueError(
                "Database already contains period cycles. Run `reset_database()` first."
            )

        with self.session_manager.db_session_scope() as session:
            # --- cycle definitions ---
            session.add_all(
                [
                    PeriodCycleORM(
                        cycle_id=CYCLE_ID_CALENDAR_MONTHS,
                        name="Calendar Months",
                        period_type=PeriodType.MONTH.name,
                        instance_kind=CycleInstanceKind.YEAR.value,
                        cycle_size=12,
                    ),
                    PeriodCycleORM(
                        cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
                        name="Calendar Quarters",
                        period_type=PeriodType.QUARTER.name,
                        instance_kind=CycleInstanceKind.YEAR.value,
                        cycle_size=4,
                    ),
                ]
            )

            # --- memberships derived from PeriodORM ---
            periods = (
                session.query(PeriodORM)
                .filter(
                    PeriodORM.period_type.in_(
                        [PeriodType.MONTH.name, PeriodType.QUARTER.name]
                    )
                )
                .all()
            )

            memberships: list[PeriodCycleMembershipORM] = []

            for p in periods:
                year = p.first_date.year
                month = p.first_date.month

                if p.period_type == PeriodType.MONTH:
                    memberships.append(
                        PeriodCycleMembershipORM(
                            cycle_id=CYCLE_ID_CALENDAR_MONTHS,
                            period_id=p.period_id,
                            cycle_instance=year,
                            cycle_element=month,  # 1..12
                        )
                    )
                elif p.period_type == PeriodType.QUARTER:
                    q = ((month - 1) // 3) + 1  # 1..4
                    memberships.append(
                        PeriodCycleMembershipORM(
                            cycle_id=CYCLE_ID_CALENDAR_QUARTERS,
                            period_id=p.period_id,
                            cycle_instance=year,
                            cycle_element=q,
                        )
                    )

            session.add_all(memberships)

    @classmethod
    def from_config_data(
        cls,
        *,
        config: RefDataConfigData,
        session_manager: SQLSessionManager,
    ) -> "RefDataService":
        """Construct a configured RefDataService from materialised config data."""
        return cls(
            config=config,
            session_manager=session_manager,
        )

    def _validate_calendar_coverage_for_contract_initialisation(
        self,
        *,
        products: list[FuturesProduct],
        start_date: date,
        end_date: date,
    ) -> None:
        required_start = date(
            start_date.year - CONTRACT_RULE_LOOKBACK_YEARS,
            start_date.month,
            start_date.day,
        )
        required_end = date(
            end_date.year + CONTRACT_RULE_LOOKAHEAD_YEARS,
            end_date.month,
            end_date.day,
        )

        for product in products:
            calendar = TradingCalendar(product.trading_calendar)
            calendar.ensure_range_in_coverage(required_start, required_end)
