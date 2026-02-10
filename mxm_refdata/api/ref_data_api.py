import logging
from datetime import date
from typing import Dict, List

from mxm_refdata.database.sql_session_manager import SQLSessionManager
from mxm_refdata.mappings import (
    futures_contract_from_orm,
    futures_product_from_orm,
    period_from_orm,
)
from mxm_refdata.models.contracts.futures_contract import FuturesContract
from mxm_refdata.models.orm.futures_contracts import FuturesContractORM
from mxm_refdata.models.orm.futures_products import FuturesProductORM
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import Period, PeriodType
from mxm_refdata.models.products.futures_product import FuturesProduct
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

    def get_contract_by_id(self, contract_id: str) -> FuturesContract | None:
        """
        Retrieve a single FuturesContract by its contract_id, with caching.

        Returns:
            FuturesContract if found, otherwise None.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"contract:{contract_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            contract = (
                session.query(FuturesContractORM)
                .filter_by(contract_id=contract_id)
                .first()
            )
            if contract:
                result = futures_contract_from_orm(contract)
                self.cache.set(cache_key, result)
                return result

        return None

    def get_contracts_by_id(self, contract_ids: List[str]) -> List[FuturesContract]:
        """
        Retrieve multiple FuturesContracts by their contract_id values.

        Semantics:
          - Returns only contracts that are found (missing IDs are ignored).
          - Preserves the input order of `contract_ids`.
          - Uses caching to avoid redundant DB queries.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        if not contract_ids:
            return []

        # Preserve input order while deduplicating for the query
        ordered_ids = list(contract_ids)
        unique_ids = list(dict.fromkeys(contract_ids))

        cache_key = f"contracts:ids:{','.join(unique_ids)}"
        if cached := self.cache.get(cache_key):
            # Preserve caller order
            by_id = {c.contract_id: c for c in cached}
            return [by_id[cid] for cid in ordered_ids if cid in by_id]

        with self.session_manager.db_session_scope() as session:
            contracts = (
                session.query(FuturesContractORM)
                .filter(FuturesContractORM.contract_id.in_(unique_ids))
                .all()
            )
            result = [futures_contract_from_orm(contract) for contract in contracts]

        # Cache the unordered result set (content-stable)
        self.cache.set(cache_key, result)

        # Return in the caller-specified order
        by_id = {c.contract_id: c for c in result}
        return [by_id[cid] for cid in ordered_ids if cid in by_id]

    def get_active_contracts(
        self,
        as_of_date: date,
        *,
        product_id: str | None = None,
        product_ids: List[str] | None = None,
    ) -> List[FuturesContract]:
        """
        Retrieve contracts that are "active" (in MXM sense) on a given date, defined as:

            FuturesContract.first_day_of_interest <= as_of_date <= FuturesContract.last_trading_day

        Optionally restrict scope by a single product_id or a list of product_ids.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        if product_id is not None and product_ids is not None:
            raise ValueError("Provide only one of product_id or product_ids, not both.")

        pid_part = (
            f"pid:{product_id}"
            if product_id is not None
            else (
                f"pids:{','.join(sorted(product_ids))}"
                if product_ids is not None
                else "pid:ALL"
            )
        )
        cache_key = f"active_contracts:{as_of_date.isoformat()}:{pid_part}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            q = session.query(FuturesContractORM).filter(
                FuturesContractORM.first_day_of_interest <= as_of_date,
                FuturesContractORM.last_trading_day >= as_of_date,
            )

            if product_id is not None:
                q = q.filter(FuturesContractORM.product_id == product_id)
            elif product_ids is not None:
                if len(product_ids) == 0:
                    return []
                q = q.filter(FuturesContractORM.product_id.in_(product_ids))

            contracts = q.order_by(
                FuturesContractORM.product_id.asc(),
                FuturesContractORM.last_trading_day.asc(),
                FuturesContractORM.contract_id.asc(),
            ).all()

            result = [futures_contract_from_orm(contract) for contract in contracts]

        self.cache.set(cache_key, result)
        return result

    def get_all_products(self) -> List[FuturesProduct]:
        """Retrieve all futures products, with caching."""

        ensure_refdata_ready(self.session_manager, self.cfg)
        cache_key = "all_products"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            products = session.query(FuturesProductORM).all()
            result = [futures_product_from_orm(product) for product in products]

        self.cache.set(cache_key, result)
        return result

    def get_product_by_id(self, product_id: str) -> FuturesProduct:
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
                product = futures_product_from_orm(product)

        if product:
            self.cache.set(cache_key, product)
        return product

    def get_contracts_for_product(
        self,
        product_id: str,
        *,
        period_type: PeriodType | str | None = None,
    ) -> List[FuturesContract]:
        """
        Retrieve all contracts for a given product, optionally filtered by period_type.

        Semantics
        ---------
        - Always returns a deterministically ordered list:
            by Period (as defined in Period.__lt__), then contract_id
        - If period_type is provided, only contracts whose Period.period_type matches
          are returned.
        - Results are cached (cache key includes period_type).
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        pt: PeriodType | None
        if period_type is None:
            pt = None
        elif isinstance(period_type, PeriodType):
            pt = period_type
        elif isinstance(period_type, str):
            try:
                pt = PeriodType(period_type)
            except Exception as e:
                raise ValueError(f"Unknown period_type {period_type!r}") from e
        else:
            raise TypeError(
                f"period_type must be PeriodType | str | None, got {type(period_type).__name__}"
            )
        cache_key = f"contracts_for_product:{product_id}:period_type={pt.value if pt is not None else '*'}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            contracts_orm = (
                session.query(FuturesContractORM).filter_by(product_id=product_id).all()
            )
            contracts: List[FuturesContract] = [
                futures_contract_from_orm(c) for c in contracts_orm
            ]

            if not contracts:
                self.cache.set(cache_key, [])
                return []

            period_ids = {c.period_id for c in contracts}

            periods_orm = (
                session.query(PeriodORM)
                .filter(PeriodORM.period_id.in_(sorted(period_ids)))
                .all()
            )
            period_by_id: Dict[str, Period] = {
                p.period_id: period_from_orm(p) for p in periods_orm
            }

            # Optional filter by Period.period_type (authoritative)

            if pt is not None:
                contracts = [
                    c
                    for c in contracts
                    if c.period_id in period_by_id
                    and period_by_id[c.period_id].period_type == pt
                ]

            # Deterministic ordering: by Period (as defined in Period.__lt__), then contract_id
            contracts.sort(key=lambda c: (period_by_id[c.period_id], c.contract_id))

        self.cache.set(cache_key, contracts)
        return contracts

    def get_contracts_for_date(self, target_date: date) -> List[FuturesContract]:
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
            result = [futures_contract_from_orm(contract) for contract in contracts]

        self.cache.set(cache_key, result)
        return result

    def get_periods(self) -> List[Period]:
        """Retrieve all available periods."""
        ensure_refdata_ready(self.session_manager, self.cfg)
        cache_key = "all_periods"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            periods = session.query(PeriodORM).all()
            result = [period_from_orm(period) for period in periods]

        self.cache.set(cache_key, result)
        return result
