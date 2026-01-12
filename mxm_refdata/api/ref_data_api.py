import logging
from datetime import date
from typing import List

from mxm_refdata.database.sql_session_manager import SQLSessionManager
from mxm_refdata.mappings.orm_converter import orm_to_obj
from mxm_refdata.models.orm.futures_contracts import FuturesContractORM
from mxm_refdata.models.orm.futures_products import FuturesProductORM
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.services.bootstrap import ensure_refdata_ready
from mxm_refdata.utils.cache_manager import CacheManager
from mxm_refdata.utils.config import load_config


class RefDataAPI:
    """
    API interface to access reference data stored in the database.
    Provides optimized querying and caching.
    """

    def __init__(self, session_manager: SQLSessionManager | None = None):
        """
        Initialize the RefDataAPI with a session manager.

        Args:
            session_manager (SQLSessionManager): Manages database connections.
        """
        self.cfg = load_config()
        self.session_manager = session_manager or SQLSessionManager(
            db_url=self.cfg.SQL_DB_URL
        )
        self.cache = CacheManager(maxsize=10000)  # Add caching for faster access
        self.logger = logging.getLogger(__name__)

    def get_all_products(self) -> List:
        """Retrieve all futures products, with caching."""

        ensure_refdata_ready(self.session_manager, self.cfg)
        cache_key = "all_products"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            products = session.query(FuturesProductORM).all()
            result = [orm_to_obj(product) for product in products]

        self.cache.set(cache_key, result)
        return result

    def get_product_by_id(self, product_id: str):
        """Retrieve a specific futures product by its ID, with caching."""
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"product:{product_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            product = (
                session.query(FuturesProductORM)
                .filter_by(product_id=product_id)
                .first()
            )
            if product:
                product = orm_to_obj(product)

        if product:
            self.cache.set(cache_key, product)
        return product

    def get_contracts_for_product(self, product_id: str) -> List:
        """Retrieve all contracts for a given product."""
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"contracts_for_product:{product_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            contracts = (
                session.query(FuturesContractORM).filter_by(product_id=product_id).all()
            )
            result = [orm_to_obj(contract) for contract in contracts]

        self.cache.set(cache_key, result)
        return result

    def get_contracts_for_date(self, target_date: date) -> List:
        """Retrieve contracts that are in their delivery period on a given date."""
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"contracts_for_date:{target_date.isoformat()}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            contracts = (
                session.query(FuturesContractORM)
                .join(PeriodORM, FuturesContractORM.period_id == PeriodORM.period_id)
                .filter(
                    PeriodORM.first_date <= target_date,
                    PeriodORM.last_date >= target_date,
                )
                .all()
            )
            result = [orm_to_obj(contract) for contract in contracts]

        self.cache.set(cache_key, result)
        return result

    def get_periods(self) -> List:
        """Retrieve all available periods."""
        ensure_refdata_ready(self.session_manager, self.cfg)
        cache_key = "all_periods"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            periods = session.query(PeriodORM).all()
            result = [orm_to_obj(period) for period in periods]

        self.cache.set(cache_key, result)
        return result
