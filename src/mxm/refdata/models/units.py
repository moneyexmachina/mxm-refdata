"""Physical Units for Product (and Contract) denomination."""

from enum import Enum


class ProductUnit(Enum):
    """Enumeration of physical units for various financial contracts."""

    LOT = "Lot"  # General unit for futures or contracts representing multiple shares, bonds, or other assets
    NOTIONAL = "Notional Value"  # Used to represent the face value for bond contracts
    SHARE = "Share"  # Used when trading the underlying equity (e.g., spot transactions)
    BOND = "Bond"  # Spot trading of a single bond (typically unusual; bonds are often traded in lots)
    BARREL = "Barrel"  # Oil and other liquid commodities
    TONNE = "Tonne"  # Bulk commodities like metals, grains
    BUSHEL = "Bushel"  # Agricultural commodities
    TROY_OUNCE = "Troy Ounce"  # Precious metals (e.g., gold, silver)
    MWH = "Megawatt-hour"  # Electricity
    GALLON = "Gallon"  # Energy products (e.g., gasoline)
    CUBIC_METER = "Cubic Meter"  # Natural gas
    CONTRACT = "Contract"  # General for options, swaps, and other derivatives
    OUNCE = "Ounce"  # General mass unit (e.g., for agricultural products)
    GRAM = "Gram"  # For precious metals and small-scale commodities
    LITER = "Liter"  # Volume-based commodities
    METRIC_TON = "Metric Ton"  # Alternative to tonne
    CURRENCY_UNIT = "Currency Unit"  # For FX contracts (e.g., USD, EUR)
    INDEX_POINT = "Index Point"  # For index-based contracts
    MMBTU = "MMBtu"  # Natural gas
    GBP = "GBP"  # British Pound Sterling (FX Futures)
