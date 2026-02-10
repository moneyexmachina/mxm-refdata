from __future__ import annotations

from typing import Any, Callable, Dict, Type, TypeVar, Union

from mxm_refdata.mappings.futures_contract_vs_orm import (
    futures_contract_from_orm,
    futures_contract_to_orm,
)
from mxm_refdata.mappings.futures_product_vs_orm import (
    futures_product_from_orm,
    futures_product_to_orm,
)
from mxm_refdata.mappings.period_vs_orm import period_from_orm, period_to_orm
from mxm_refdata.models.contracts.futures_contract import FuturesContract
from mxm_refdata.models.orm.futures_contracts import FuturesContractORM
from mxm_refdata.models.orm.futures_products import FuturesProductORM
from mxm_refdata.models.orm.periods import PeriodORM
from mxm_refdata.models.periods import Period
from mxm_refdata.models.products.futures_product import FuturesProduct

# -------------------------
# Types
# -------------------------

Model = Union[FuturesProduct, FuturesContract, Period]
Orm = Union[FuturesProductORM, FuturesContractORM, PeriodORM]

M = TypeVar("M", bound=Model)
O = TypeVar("O", bound=Orm)

# Concrete converter function types (so the dicts are not "Callable[[Any], Any]")
FProdFrom = Callable[[FuturesProductORM], FuturesProduct]
FConFrom = Callable[[FuturesContractORM], FuturesContract]
PerFrom = Callable[[PeriodORM], Period]

FProdTo = Callable[[FuturesProduct], FuturesProductORM]
FConTo = Callable[[FuturesContract], FuturesContractORM]
PerTo = Callable[[Period], PeriodORM]


# -------------------------
# Mappings (type-keyed, but kept specific)
# -------------------------

# We keep three dicts with concrete key/value types to avoid Unknown/Any leakage.
_FUTURES_PRODUCT_FROM: Dict[Type[FuturesProductORM], FProdFrom] = {
    FuturesProductORM: futures_product_from_orm
}
_FUTURES_CONTRACT_FROM: Dict[Type[FuturesContractORM], FConFrom] = {
    FuturesContractORM: futures_contract_from_orm
}
_PERIOD_FROM: Dict[Type[PeriodORM], PerFrom] = {PeriodORM: period_from_orm}

_FUTURES_PRODUCT_TO: Dict[Type[FuturesProduct], FProdTo] = {
    FuturesProduct: futures_product_to_orm
}
_FUTURES_CONTRACT_TO: Dict[Type[FuturesContract], FConTo] = {
    FuturesContract: futures_contract_to_orm
}
_PERIOD_TO: Dict[Type[Period], PerTo] = {Period: period_to_orm}

CLASS_TO_ORM_MAPPING: Dict[Type[Any], Type[Any]] = {
    FuturesProduct: FuturesProductORM,
    FuturesContract: FuturesContractORM,
    Period: PeriodORM,
}


def get_orm_class(model_class: Type[M]) -> Type[Any]:
    orm_class = CLASS_TO_ORM_MAPPING.get(model_class)
    if orm_class is None:
        raise ValueError(f"No ORM class for {model_class}")
    return orm_class


def get_model_class(orm_class: Type[O]) -> Type[Any]:
    inv: Dict[Type[Any], Type[Any]] = {v: k for k, v in CLASS_TO_ORM_MAPPING.items()}
    model_class = inv.get(orm_class)
    if model_class is None:
        raise ValueError(f"No model class for {orm_class}")
    return model_class


def orm_to_obj(orm_obj: Orm) -> Model:
    """
    Convert an ORM object to its internal model representation.

    Uses isinstance narrowing rather than overloads to keep pyright happy and strict.
    """
    if isinstance(orm_obj, FuturesProductORM):
        conv = _FUTURES_PRODUCT_FROM[FuturesProductORM]
        return conv(orm_obj)

    if isinstance(orm_obj, FuturesContractORM):
        conv = _FUTURES_CONTRACT_FROM[FuturesContractORM]
        return conv(orm_obj)

    if isinstance(orm_obj, PeriodORM):
        conv = _PERIOD_FROM[PeriodORM]
        return conv(orm_obj)

    # Defensive: should be unreachable given Orm union
    raise ValueError(f"Unsupported ORM type: {type(orm_obj)!r}")


def obj_to_orm(model_obj: Model) -> Orm:
    """
    Convert an internal model object to its ORM representation.

    Uses isinstance narrowing rather than overloads to keep pyright happy and strict.
    """
    if isinstance(model_obj, FuturesProduct):
        conv = _FUTURES_PRODUCT_TO[FuturesProduct]
        return conv(model_obj)

    if isinstance(model_obj, FuturesContract):
        conv = _FUTURES_CONTRACT_TO[FuturesContract]
        return conv(model_obj)

    if isinstance(model_obj, Period):
        conv = _PERIOD_TO[Period]
        return conv(model_obj)

    # Defensive: should be unreachable given Model union
    raise ValueError(f"Unsupported model type: {type(model_obj)!r}")
