"Factory for FuturesProduct instances."

import threading
from typing import Dict

from mxm_refdata.models.products.futures_product import FuturesProduct
from mxm_refdata.parsing.futures_products_from_csv import (
    parse_futures_products_csv_to_normalised_data,
)


class FuturesProductFactory:
    """Factory for creating and caching FuturesProduct instances."""

    _instance = None  # Singleton instance
    _lock = threading.Lock()  # Thread safety lock
    _cache: Dict[str, FuturesProduct] = {}  # Cache for created products

    def __new__(cls) -> "FuturesProductFactory":
        """Ensure only one instance of FuturesProductFactory."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def create_from_normalized_data(self, data: dict) -> FuturesProduct:
        """Create a FuturesProduct from normalized data."""
        product_id = data["product_id"]
        if product_id not in self._cache:
            product = FuturesProduct(**data)
            self._cache[product_id] = product
        return self._cache[product_id]

    @staticmethod
    def initialise_from_csv(csv_file_path: str) -> list[FuturesProduct]:
        normalized_data = parse_futures_products_csv_to_normalised_data(csv_file_path)
        factory = FuturesProductFactory()
        return [factory.create_from_normalized_data(data) for data in normalized_data]

    def get_product(self, product_id: str, **kwargs) -> FuturesProduct:
        """
        Retrieve a FuturesProduct from the cache, or create one if it doesn't exist.

        Args:
            product_id (str): The unique identifier of the product.
            **kwargs: Additional arguments to create a FuturesProduct if not cached.

        Returns:
            FuturesProduct: The cached or newly created product.
        """
        if product_id not in self._cache:
            self._cache[product_id] = FuturesProduct(**kwargs)
        return self._cache[product_id]
