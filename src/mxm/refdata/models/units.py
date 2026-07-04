"""Physical Units for Product and Contract denomination."""

from enum import Enum


class ProductUnit(Enum):
    """Enumeration of units for financial products and contracts."""

    LOT = "Lot"
    NOTIONAL = "Notional Value"
    SHARE = "Share"
    BOND = "Bond"
    CONTRACT = "Contract"

    # Financial quotation / index units
    INDEX_POINT = "Index Point"
    INDEX_POINTS = "Index Points"
    IMM_INDEX = "IMM Index"
    USD_FACE_VALUE = "USD Face Value"

    # Currency units, used mostly for FX futures contract denomination
    CURRENCY_UNIT = "Currency Unit"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CHF = "CHF"
    CAD = "CAD"
    AUD = "AUD"
    NZD = "NZD"
    MXN = "MXN"
    BRL = "BRL"
    NOK = "NOK"
    SEK = "SEK"
    INR = "INR"
    CNH = "CNH"

    # Crypto units
    BITCOIN = "Bitcoin"
    ETHER = "Ether"

    # Energy / volume units
    BARREL = "Barrel"
    GALLON = "Gallon"
    LITER = "Liter"
    CUBIC_METER = "Cubic Meter"
    MWH = "Megawatt-hour"
    MMBTU = "MMBtu"

    # Mass / agricultural / metals units
    POUND = "Pound"
    OUNCE = "Ounce"
    TROY_OUNCE = "Troy Ounce"
    GRAM = "Gram"
    TONNE = "Tonne"
    METRIC_TON = "Metric Ton"
    SHORT_TON = "Short Ton"
    BUSHEL = "Bushel"
    HUNDREDWEIGHT = "Hundredweight"
    BOARD_FOOT = "Board Foot"
