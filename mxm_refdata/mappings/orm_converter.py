"""Handles conversion between ORM models and internal business models."""

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
from mxm_refdata.models.orm import FuturesContractORM, FuturesProductORM, PeriodORM
from mxm_refdata.models.periods import Period
from mxm_refdata.models.products.futures_product import FuturesProduct

# Dictionary to dynamically map ORM models to conversion functions
ORM_TO_MODEL_MAPPING = {
    "FuturesProductORM": futures_product_from_orm,
    "FuturesContractORM": futures_contract_from_orm,
    "PeriodORM": period_from_orm,
}

MODEL_TO_ORM_MAPPING = {
    "FuturesProduct": futures_product_to_orm,
    "FuturesContract": futures_contract_to_orm,
    "Period": period_to_orm,
}

CLASS_TO_ORM_MAPPING = {
    FuturesProduct: FuturesProductORM,
    FuturesContract: FuturesContractORM,
    Period: PeriodORM,
}


def get_orm_class(model_class):
    """
    Get the corresponding ORM class for a given model class.

    Args:
        model_class (type): The internal business model class.

    Returns:
        type: The corresponding ORM class.
    """
    orm_class = CLASS_TO_ORM_MAPPING.get(model_class)

    if orm_class is None:
        raise ValueError(f"No ORM class for {model_class}")

    return orm_class


def get_model_class(orm_class):
    """
    Get the corresponding internal model class for a given ORM class.

    Args:
        orm_class (type): The SQLAlchemy ORM class.

    Returns:
        type: The corresponding internal business model class.
    """
    model_class = {v: k for k, v in CLASS_TO_ORM_MAPPING.items()}.get(orm_class)

    if model_class is None:
        raise ValueError(f"No model class for {orm_class}")

    return model_class


def orm_to_obj(orm_obj):
    """
    Convert an ORM object to its internal model representation.

    Args:
        orm_obj (Base): An SQLAlchemy ORM instance.

    Returns:
        The corresponding internal business model instance.
    """
    orm_class_name = orm_obj.__class__.__name__
    conversion_func = ORM_TO_MODEL_MAPPING.get(orm_class_name)

    if conversion_func is None:
        raise ValueError(f"No ORM-to-model conversion function for {orm_class_name}")

    return conversion_func(orm_obj)


def obj_to_orm(model_obj):
    """
    Convert an internal model object to its ORM representation.

    Args:
        model_obj (BaseModel): An internal business model instance.

    Returns:
        The corresponding SQLAlchemy ORM instance.
    """
    model_class_name = model_obj.__class__.__name__
    conversion_func = MODEL_TO_ORM_MAPPING.get(model_class_name)

    if conversion_func is None:
        raise ValueError(f"No model-to-ORM conversion function for {model_class_name}")

    return conversion_func(model_obj)
