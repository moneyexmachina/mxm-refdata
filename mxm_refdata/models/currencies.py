"""This module defines the Currency Enum for ISO 4217 currency codes."""

from enum import Enum


class Currency(Enum):
    """Currency Enum for ISO 4217 currency codes."""

    AUD = "Australian Dollar"
    CAD = "Canadian Dollar"
    CHF = "Swiss Franc"
    EUR = "Euro"
    GBP = "Pound Sterling"
    HKD = "Hong Kong Dollar"
    INR = "Indian Rupee"
    JPY = "Yen"
    MXN = "Mexican Peso"
    NOK = "Norwegian Krone"
    NZD = "New Zealand Dollar"
    SEK = "Swedish Krona"
    SGD = "Singapore Dollar"
    USD = "US Dollar"
    BRL = "Brazilian Real"
    CNY = "Yuan Renminbi"
