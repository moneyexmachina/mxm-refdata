"""Service to create, update, and manage reference data in the database."""

import logging
from datetime import date

from mxm_refdata.database.sql_session_manager import SQLSessionManager
from mxm_refdata.mappings.orm_converter import obj_to_orm, orm_to_obj
from mxm_refdata.models.orm.futures_contracts import FuturesContractORM
from mxm_refdata.models.orm.futures_products import FuturesProductORM
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import PeriodType
from mxm_refdata.services.futures_contract_factory import FuturesContractFactory
from mxm_refdata.services.futures_product_factory import FuturesProductFactory
from mxm_refdata.services.period_factory import PeriodFactory
from mxm_refdata.utils.config import load_config
from mxm_refdata.utils.resources import futures_products_csv_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RefDataService:
    """
    Manages reference data processes including initializing, updating, and resetting futures products.
    """

    def __init__(self, session_manager: SQLSessionManager):
        """
        Initialize the RefDataService with a session manager.

        Args:
            session_manager (SQLSessionManager): The session manager handling DB connections.
        """
        self.session_manager = session_manager
        self.product_factory = FuturesProductFactory()
        self.contract_factory = FuturesContractFactory()
        self.period_factory = PeriodFactory()

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

    def is_table_empty(self, orm_model) -> bool:
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
        csv_file_path: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        """
        Perform a full instrument setup: initialise periods, products, and contracts.

        This method is a convenience function that ensures all required data is set up correctly.

        Args:
            csv_file_path (Optional[str]): Path to the CSV file for futures products.
            start_date (Optional[date]): Start date for contract generation (default: today).
            end_date (Optional[date]): End date for contract generation (default: +1 year).
        """
        logging.info("Starting full instrument setup...")

        # Ensure we have a reasonable date range if not provided
        start_date = start_date or date(2000, 1, 1)
        end_date = end_date or date(2045, 12, 31)

        # Step 1: Initialise periods (YEAR, QUARTER, MONTH)
        self.initialise_periods(start_date=start_date, end_date=end_date)

        # Step 2: Initialise futures products from CSV
        self.initialise_futures_products(csv_file_path=csv_file_path)

        # Step 3: Generate and store contracts for each product
        self.initialise_futures_contracts(start_date=start_date, end_date=end_date)

        logging.info("Full instrument setup completed successfully.")

    def initialise_futures_products(self, csv_file_path: str | None = None) -> None:
        """
        Initialize the database with futures products from a CSV file.

        Args:
            csv_file_path (Optional[str]): Path to the CSV file containing futures product definitions.
                                        If None, uses the default path from config.

        Raises:
            ValueError: If the database is not empty.
        """
        if not self.is_table_empty(FuturesProductORM):
            raise ValueError(
                "Database already contains products. Run `reset_database()` first."
            )

        if csv_file_path is None:
            cfg = load_config()
            with futures_products_csv_path(cfg) as csv_file_path:
                products = self.product_factory.initialise_from_csv(csv_file_path)
        else:
            products = self.product_factory.initialise_from_csv(csv_file_path)

        with self.session_manager.db_session_scope() as session:
            for product in products:
                product_orm = obj_to_orm(product)
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

        new_periods = []
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
                    session.add(obj_to_orm(period))  # Convert & store only new periods

    def initialise_futures_contracts(self, start_date: date, end_date: date) -> None:
        """
        Initialize futures contracts using existing products and periods in the database.

        Args:
            start_date (date): The start date for contract generation.
            end_date (date): The end date for contract generation.
        """
        with self.session_manager.db_session_scope() as session:
            # Retrieve all existing products and convert them before session closes
            products = [
                orm_to_obj(product)
                for product in session.query(FuturesProductORM).all()
            ]
            if not products:
                raise ValueError(
                    "No products found in the database. Run initialise_futures_products() first."
                )

            # Retrieve all periods within the date range
            periods = {
                p.period_id: orm_to_obj(p)
                for p in session.query(PeriodORM)
                .filter(
                    PeriodORM.first_date >= start_date, PeriodORM.last_date <= end_date
                )
                .all()
            }
            if not periods:
                raise ValueError(
                    "No periods found in the database. Run initialise_periods() first."
                )

        # Generate contracts outside of session
        contracts = []
        for product in products:
            product_contracts = self.contract_factory.create_contracts_for_product(
                product, periods
            )
            contracts.extend(product_contracts)

        # Store contracts in the database
        with self.session_manager.db_session_scope() as session:
            for contract in contracts:
                session.add(obj_to_orm(contract))
