import logging
from datetime import date
from typing import Any

from mxm.refdata.database.sql_session_manager import SQLSessionManager
from mxm.refdata.mappings import (
    futures_contract_from_orm,
    futures_product_from_orm,
    period_cycle_from_orm,
    period_cycle_membership_from_orm,
    period_from_orm,
)
from mxm.refdata.models.contracts.futures_contract import FuturesContract
from mxm.refdata.models.orm.futures_contracts import FuturesContractORM
from mxm.refdata.models.orm.futures_products import FuturesProductORM
from mxm.refdata.models.orm.period_cycles import (
    PeriodCycleMembershipORM,
    PeriodCycleORM,
)
from mxm.refdata.models.orm.periods import PeriodORM
from mxm.refdata.models.period_cycles import PeriodCycle, PeriodCycleMembership
from mxm.refdata.models.periods import Period, PeriodType
from mxm.refdata.models.products.futures_product import FuturesProduct
from mxm.refdata.services.bootstrap import ensure_refdata_ready
from mxm.refdata.utils.cache_manager import CacheManager
from mxm.refdata.utils.config import load_config


class RefDataLookupError(KeyError):
    """
    Raised when a required reference data object cannot be found.

    This error signals a violation of an invariant: the caller assumed that
    the requested object exists in the curated reference dataset, but it
    was not present.

    Typical causes:
    - contract_id not part of the prepared reference data universe
    - reference data not built for the requested product/time range
    - upstream data preparation incomplete or inconsistent

    This is not a transient error and should not be silently ignored.
    """


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
        self.cache: CacheManager[Any] = CacheManager(
            maxsize=10000
        )  # Add caching for faster access
        self.logger = logging.getLogger(__name__)

    def maybe_get_contract_by_id(self, contract_id: str) -> FuturesContract | None:
        """
        Retrieve a FuturesContract by its contract_id, if available.

        This method performs a best-effort lookup against the curated reference
        dataset. It is intended for boundary layers where partial coverage is
        expected and must be handled explicitly.

        The result may be None if the contract_id is not present in the current
        reference dataset.

        Args:
            contract_id:
                Canonical contract identifier.

        Returns:
            FuturesContract if found, otherwise None.

        Usage:
            Use this method when exploring or validating coverage, e.g.:
            - checking whether a product universe has been prepared
            - probing availability across time ranges
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
            if contract is not None:
                result = futures_contract_from_orm(contract)
                self.cache.set(cache_key, result)
                return result

        return None

    def get_contract_by_id(self, contract_id: str) -> FuturesContract:
        """
        Retrieve a FuturesContract by its contract_id, enforcing existence.

        This method assumes that the requested contract_id is valid and present
        in the curated reference dataset. If the contract cannot be found, a
        RefDataLookupError is raised.

        This is the preferred method for use within typed execution code where
        contract identities are already validated or constructed by the system.

        Args:
            contract_id:
                Canonical contract identifier.

        Returns:
            FuturesContract (guaranteed to be present).

        Raises:
            RefDataLookupError:
                If the contract_id is not found in the reference dataset.

        Usage:
            Use this method in invariant-bearing code paths, e.g.:
            - execution, pricing, and PnL logic
            - synthetic asset construction
            - any context where missing contracts indicate a system error
        """
        contract = self.maybe_get_contract_by_id(contract_id)

        if contract is None:
            raise RefDataLookupError(
                f"FuturesContract not found for contract_id='{contract_id}'. "
                "This indicates missing or incomplete reference data."
            )

        return contract

    def get_contracts_by_id(self, contract_ids: list[str]) -> list[FuturesContract]:
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
        product_ids: list[str] | None = None,
    ) -> list[FuturesContract]:
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

    def get_all_products(self) -> list[FuturesProduct]:
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
    ) -> list[FuturesContract]:
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
        else:
            try:
                pt = PeriodType(period_type)
            except Exception as e:
                raise ValueError(f"Unknown period_type {period_type!r}") from e

        cache_key = (
            f"contracts_for_product:{product_id}:"
            f"period_type={pt.value if pt is not None else '*'}"
        )
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            contracts_orm = (
                session.query(FuturesContractORM).filter_by(product_id=product_id).all()
            )
            contracts: list[FuturesContract] = [
                futures_contract_from_orm(c) for c in contracts_orm
            ]

        if not contracts:
            self.cache.set(cache_key, [])
            return []

        # Bulk period lookup via API helper (cached internally)
        period_ids = [c.period_id for c in contracts]
        periods = self.get_periods_by_id(period_ids)

        # Build mapping for filtering / ordering.
        # Note: get_periods_by_id preserves input order and ignores missing IDs;
        # we must still map by id for joins.
        period_by_id: dict[str, Period] = {p.period_id: p for p in periods}

        # Drop contracts whose period_id is missing from refdata (should be impossible,
        # but we keep it explicit and non-silent in behaviour: missing periods => excluded).
        contracts = [c for c in contracts if c.period_id in period_by_id]

        # Optional filter by Period.period_type (authoritative)
        if pt is not None:
            contracts = [
                c for c in contracts if period_by_id[c.period_id].period_type == pt
            ]

        # Deterministic ordering: by Period (as defined in Period.__lt__), then contract_id
        contracts.sort(key=lambda c: (period_by_id[c.period_id], c.contract_id))

        self.cache.set(cache_key, contracts)
        return contracts

    def get_contracts_for_date(self, target_date: date) -> list[FuturesContract]:
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

    def get_periods(self) -> list[Period]:
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

    def get_period_by_id(self, period_id: str) -> Period | None:
        """
        Retrieve a single Period by its period_id, with caching.

        Returns:
            Period if found, otherwise None.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"period:{period_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            period = session.query(PeriodORM).filter_by(period_id=period_id).first()
            if period:
                result = period_from_orm(period)
                self.cache.set(cache_key, result)
                return result

        return None

    def get_periods_by_id(self, period_ids: list[str]) -> list[Period]:
        """
        Retrieve multiple Periods by their period_id values.

        Semantics:
          - Returns only periods that are found (missing IDs are ignored).
          - Preserves the input order of `period_ids`.
          - Uses caching to avoid redundant DB queries.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        if not period_ids:
            return []

        ordered_ids = list(period_ids)
        unique_ids = list(dict.fromkeys(period_ids))

        cache_key = f"periods:ids:{','.join(unique_ids)}"
        if cached := self.cache.get(cache_key):
            by_id = {p.period_id: p for p in cached}
            return [by_id[pid] for pid in ordered_ids if pid in by_id]

        with self.session_manager.db_session_scope() as session:
            periods = (
                session.query(PeriodORM)
                .filter(PeriodORM.period_id.in_(unique_ids))
                .all()
            )
            result = [period_from_orm(p) for p in periods]

        self.cache.set(cache_key, result)

        by_id = {p.period_id: p for p in result}
        return [by_id[pid] for pid in ordered_ids if pid in by_id]

    def get_cycles(self) -> list[PeriodCycle]:
        """
        Retrieve all available PeriodCycle definitions.

        Cached as a whole-list artifact; cycles are few and essentially static for a DB build.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = "all_period_cycles"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            cycles = (
                session.query(PeriodCycleORM)
                .order_by(PeriodCycleORM.cycle_id.asc())
                .all()
            )
            result = [period_cycle_from_orm(c) for c in cycles]

        self.cache.set(cache_key, result)
        return result

    def get_cycle_by_id(self, cycle_id: str) -> PeriodCycle | None:
        """
        Retrieve a single PeriodCycle by cycle_id, with caching.

        Returns:
            PeriodCycle if found, otherwise None.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"period_cycle:{cycle_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            c = session.query(PeriodCycleORM).filter_by(cycle_id=cycle_id).first()
            if c:
                result = period_cycle_from_orm(c)
                self.cache.set(cache_key, result)
                return result

        return None

    def get_cycle_memberships(self, cycle_id: str) -> list[PeriodCycleMembership]:
        """
        Retrieve all memberships for a given cycle_id.

        Semantics:
          - Deterministically ordered by (cycle_instance, cycle_element, period_id).
          - Cached by cycle_id.

        This is primarily an inspection/audit surface. Selection logic should usually use
        `get_cycle_elements(...)` for targeted lookup.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"period_cycle_memberships:{cycle_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            rows = (
                session.query(PeriodCycleMembershipORM)
                .filter(PeriodCycleMembershipORM.cycle_id == cycle_id)
                .order_by(
                    PeriodCycleMembershipORM.cycle_instance.asc(),
                    PeriodCycleMembershipORM.cycle_element.asc(),
                    PeriodCycleMembershipORM.period_id.asc(),
                )
                .all()
            )
            result = [period_cycle_membership_from_orm(r) for r in rows]

        self.cache.set(cache_key, result)
        return result

    def get_cycle_elements(
        self,
        period_ids: list[str],
        *,
        cycle_id: str,
    ) -> dict[str, int]:
        """
        Batch lookup: map period_id -> cycle_element for the given cycle.

        This is the key surface needed by MXM V1 contract selection:
            contract.period_id -> cycle element (e.g. month number, quarter number)

        Semantics:
          - Returns only found period_ids (missing IDs are omitted).
          - Input order is not preserved (dict output); caller can re-order if needed.
          - Cached by (cycle_id, unique(sorted(period_ids))).
          - Deterministic query ordering, but the returned mapping is inherently unordered.

        Returns:
            Dict[str, int] mapping period_id -> cycle_element
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        if not period_ids:
            return {}

        unique_ids = sorted(set(period_ids))
        cache_key = f"period_cycle_elements:{cycle_id}:pids:{','.join(unique_ids)}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            rows = (
                session.query(
                    PeriodCycleMembershipORM.period_id,
                    PeriodCycleMembershipORM.cycle_element,
                )
                .filter(
                    PeriodCycleMembershipORM.cycle_id == cycle_id,
                    PeriodCycleMembershipORM.period_id.in_(unique_ids),
                )
                .order_by(PeriodCycleMembershipORM.period_id.asc())
                .all()
            )

        result: dict[str, int] = {pid: int(elem) for (pid, elem) in rows}
        self.cache.set(cache_key, result)
        return result

    def get_cycle_element(
        self,
        period_id: str,
        *,
        cycle_id: str,
    ) -> int | None:
        """
        Convenience wrapper: lookup a single period_id -> cycle_element for a cycle.

        Uses caching; implemented via a direct ORM query (not via get_cycle_elements)
        to avoid building large cache keys for singleton usage.
        """
        ensure_refdata_ready(self.session_manager, self.cfg)

        cache_key = f"period_cycle_element:{cycle_id}:{period_id}"
        if cached := self.cache.get(cache_key):
            return cached

        with self.session_manager.db_session_scope() as session:
            row = (
                session.query(PeriodCycleMembershipORM.cycle_element)
                .filter(
                    PeriodCycleMembershipORM.cycle_id == cycle_id,
                    PeriodCycleMembershipORM.period_id == period_id,
                )
                .first()
            )

        if row is None:
            return None

        elem = int(row[0])
        self.cache.set(cache_key, elem)
        return elem
