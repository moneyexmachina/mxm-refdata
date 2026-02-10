"""Mapping FututesProduct instances to and from FuturesProductORM instances."""

from mxm_refdata.models.orm import FuturesProductORM
from mxm_refdata.models.products.futures_product import FuturesProduct
from mxm_refdata.utils.period_types_codec import (
    decode_period_types,
    encode_period_types,
)


def futures_product_to_orm(product: FuturesProduct) -> FuturesProductORM:
    """Map a FuturesProduct to a FuturesProductORM instance."""
    return FuturesProductORM(
        product_id=product.product_id,
        venue=product.venue,
        description=product.description,
        currency=product.currency,
        unit=product.unit,
        contract_size=product.contract_size,
        valid_period_rule=product.valid_period_rule,
        listing_rule=product.listing_rule,
        period_types=encode_period_types(product.period_types),
        settlement=product.settlement,
        last_trading_rule=product.last_trading_rule,
        expiry_rule=product.expiry_rule,
        trading_calendar=product.trading_calendar,
        trading_hours=product.trading_hours,
        tick_size=product.tick_size,
        tick_value=product.tick_value,
        initial_margin=product.initial_margin,
        maintenance_margin=product.maintenance_margin,
    )


def futures_product_from_orm(orm_instance: FuturesProductORM) -> FuturesProduct:
    """Map a FuturesProductORM instance to a FuturesProduct."""
    return FuturesProduct(
        product_id=orm_instance.product_id,
        venue=orm_instance.venue,
        description=orm_instance.description,
        currency=orm_instance.currency,
        unit=orm_instance.unit,
        contract_size=orm_instance.contract_size,
        valid_period_rule=orm_instance.valid_period_rule,
        listing_rule=orm_instance.listing_rule,
        period_types=decode_period_types(orm_instance.period_types),
        settlement=orm_instance.settlement,
        last_trading_rule=orm_instance.last_trading_rule,
        expiry_rule=orm_instance.expiry_rule,
        trading_calendar=orm_instance.trading_calendar,
        trading_hours=orm_instance.trading_hours,
        tick_size=orm_instance.tick_size,
        tick_value=orm_instance.tick_value,
        initial_margin=orm_instance.initial_margin,
        maintenance_margin=orm_instance.maintenance_margin,
    )
