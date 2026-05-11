# Package Audit: mxm-refdata

This document records the process of re-familiarisation with the codebase by reading through the test suite and mapping observed behaviour back to modules.


## API Layer

### Module: `src/mxm/refdata/api/ref_data_api.py`
- **Test file**: `tests/unittests/api/test_ref_data_api.py`

#### Observed behaviour (from tests)
- `RefDataAPI.get_product_by_id()` retrieves a product by ID.
- `RefDataAPI.get_contracts_for_date()` retrieves contracts active on a given date.
- Caching avoids repeated DB queries for the same product.

#### Implementation
- Provides a read-only query façade for reference data.
- Methods:
  - `get_all_products()` → list all futures products.
  - `get_product_by_id(product_id)` → fetch product by ID.
  - `get_contracts_for_product(product_id)` → list contracts for product.
  - `get_contracts_for_date(date)` → contracts active during a date.
  - `get_periods()` → list all periods.
- Uses `SQLSessionManager` for DB sessions.
- Uses `orm_to_obj` to convert ORM → domain objects.
- Applies caching consistently to all queries.

#### Not covered by tests
- `get_all_products()`, `get_contracts_for_product()`, and `get_periods()`.
- Error cases (invalid product ID, date with no contracts).
- Behaviour when DB contents change after cache is populated.

#### TODOs
- Add type hints and Google-style docstrings.
- Extend test suite to cover all methods and error scenarios.
- Decide strategy for cache invalidation on DB updates.

## Database

### Module: `src/mxm/refdata/database/sql_session_manager.py`
- **Test file**: `tests/unittests/database/test_sql_session_manager.py`
#### Observed behaviour (from tests)
- Context manager `db_session_scope` opens, commits, and closes sessions correctly.
- `get_db_session` provides a valid SQLAlchemy session.
- `init_db` successfully creates schema.
- `drop_db` successfully removes schema.
- `check_db_connection` verifies connectivity.
- `get_session_factory` works with default and custom factories.

#### Implementation
- Wraps SQLAlchemy engine and session lifecycle.
- Loads DB config (`SQL_DB_URL`) via `load_config`.
- Provides:
  - `get_engine()`, `get_session_factory()`, `get_db_session()`
  - `db_session_scope()` (transactional context manager)
  - `init_db()` / `drop_db()` schema management
  - `check_db_connection()` health check
- Includes robust exception handling and logging.

#### Not covered by tests
- Failure paths for `init_db`, `drop_db`, and `check_db_connection`.
- `get_engine()` is never exercised.
- Transaction rollback behaviour inside `db_session_scope`.

#### TODOs
- Add tests for error conditions and rollback behaviour.
- Add type hints for clarity (`Engine`, `Session`, `Callable[[], Session]`).
- Add docstrings clarifying lifecycle guarantees (e.g., commit/rollback semantics).

## Mappings

### Module: `src/mxm/refdata/mappings/futures_contract_vs_orm.py`
- **Test file**: `tests/unittests/mappings/test_futures_contract_vs_orm.py`
#### Observed behaviour (from tests)
- `futures_contract_to_orm()` correctly maps a domain `FuturesContract` into a `FuturesContractORM`.
- `futures_contract_from_orm()` correctly maps a `FuturesContractORM` back into a domain `FuturesContract`.
- All attributes (IDs, contract size, unit, currency, trading calendar, first/last dates) are preserved during mapping.
- A round-trip conversion (domain → ORM → domain) produces an object equal to the original.

#### Implementation
- Provides two conversion functions:
  - `futures_contract_to_orm(contract: FuturesContract) -> FuturesContractORM`  
    Maps each field of the domain contract into an ORM instance.
  - `futures_contract_from_orm(orm: FuturesContractORM) -> FuturesContract`  
    Maps ORM fields back into a domain contract, converting `currency` and `unit` from strings into Enums.
- Ensures the separation of concerns:  
  - Domain models (`FuturesContract`) remain pure Python objects.  
  - ORM models (`FuturesContractORM`) remain SQLAlchemy entities.  
  - Conversion functions act as translators between the two layers.

#### Not covered by tests
- Behaviour when fields are missing, invalid, or `None`.
- Enum conversion edge cases (invalid currency or unit strings).
- Database-generated fields (e.g. auto IDs, timestamps) are not tested.
- Batch conversion (performance, multiple contracts at once).

#### TODOs
- Add docstrings to tests for clarity of intended mapping behaviour.
- Add negative tests for invalid/missing fields and enum mismatches.
- Consider utilities for bulk conversion (list[domain] ↔ list[ORM]).
- Extend type hints for clarity: explicit return type in round-trip scenarios.


### Module: `src/mxm/refdata/mappings/futures_product_vs_orm.py`
- **Test file**: `tests/unittests/mappings/test_futures_product_vs_orm.py`

#### Observed behaviour (from tests)
- `futures_product_to_orm()` maps a domain `FuturesProduct` into a `FuturesProductORM` object.
- `futures_product_from_orm()` maps a `FuturesProductORM` back into a domain `FuturesProduct`.
- Tests assert only a subset of attributes (`product_id`, `currency`, `unit`, `settlement`) for equality.
- Both conversion directions run without errors on a fully populated product.

#### Implementation
- Provides two conversion functions:
  - `futures_product_to_orm(product: FuturesProduct) -> FuturesProductORM`  
    Maps all attributes from the domain model into an ORM instance, including:
    - Identifiers (`product_id`, `venue`, `description`)
    - Contract details (`currency`, `unit`, `contract_size`)
    - Rules (`valid_period_rule`, `listing_rule`, `period_types`, `last_trading_rule`, `expiry_rule`)
    - Market structure (`settlement`, `trading_calendar`, `trading_hours`)
    - Tick and margin data (`tick_size`, `tick_value`, `initial_margin`, `maintenance_margin`)
  - `futures_product_from_orm(orm_instance: FuturesProductORM) -> FuturesProduct`  
    Performs the inverse mapping, reconstructing a domain object from ORM.

- The mapping is a **direct field copy** — no transformations, validation, or enum conversions are applied here.

#### Not covered by tests
- Many fields are not asserted (`description`, `venue`, rules, calendar, hours, tick/margin data).
- No round-trip test (domain → ORM → domain) to ensure information preservation.
- No validation for missing or invalid fields.
- No checks for enum/string consistency (unlike contracts mapping, where enums are handled).
- No performance tests (batch conversion of many products).

#### TODOs
- Expand test coverage to assert all fields, not just four.
- Add a round-trip test to confirm mapping is lossless.
- Introduce negative tests (invalid enum values, missing required fields).
- Consider bulk conversion utilities for efficiency when handling large product universes.
- Add detailed docstrings clarifying each attribute’s role in both domain and ORM.


### Module: `src/mxm/refdata/mappings/orm_converter.py`
- **Test file**: `tests/unittests/mappings/test_orm_converter.py`

#### Observed behaviour (from tests)
- `get_orm_class(model_class)` returns the correct ORM class for a given domain model (`FuturesProduct`, `FuturesContract`, `Period`).
  - Raises `ValueError` if no ORM class exists for the given type.
- `get_model_class(orm_class)` returns the correct domain model class for a given ORM class (`FuturesProductORM`, `FuturesContractORM`, `PeriodORM`).
  - Raises `ValueError` if no model class exists for the given type.
- `orm_to_obj(orm_instance)` correctly maps ORM objects into their domain equivalents.
- `obj_to_orm(domain_instance)` correctly maps domain objects into their ORM equivalents.
- Tests confirm full field-by-field equality when mapping a `FuturesProduct` between domain and ORM.

#### Implementation
- Centralizes conversion between ORM classes and internal domain models.
- Uses dictionaries:
  - `CLASS_TO_ORM_MAPPING`: direct mapping from domain class → ORM class.
  - `ORM_TO_MODEL_MAPPING`: ORM class name → conversion function (ORM → domain).
  - `MODEL_TO_ORM_MAPPING`: domain class name → conversion function (domain → ORM).
- Provides four main utilities:
  - `get_orm_class(model_class)` → ORM class
  - `get_model_class(orm_class)` → domain class
  - `orm_to_obj(orm_instance)` → domain object
  - `obj_to_orm(domain_instance)` → ORM object
- Internally delegates to specific conversion functions (`futures_product_from_orm`, `futures_contract_to_orm`, `period_to_orm`, etc.).
- Raises `ValueError` for unsupported types.

#### Not covered by tests
- Negative paths for `orm_to_obj` and `obj_to_orm` (e.g. unknown class names).
- Batch conversions (lists of objects).
- Performance considerations for repeated conversions.
- Consistency checks between mappings (i.e., ensuring mappings are symmetric and complete).
- Complex nested structures (though domain models seem mostly flat).

#### TODOs
- Add tests for unsupported types passed to `orm_to_obj` and `obj_to_orm`.
- Add round-trip tests (domain → ORM → domain, and ORM → domain → ORM) for all models, not just `FuturesProduct`.
- Consider adding bulk conversion utilities (`list[domain] ↔ list[ORM]`).
- Document clearly in docstrings that this module is the **single source of truth** for ORM/domain conversions.

### Module: `src/mxm/refdata/mappings/period_vs_orm.py`
- **Test file**: `tests/unittests/mappings/test_period_vs_orm.py`

#### Observed behaviour (from tests)
- `period_to_orm()` maps a domain `Period` into a `PeriodORM` object:
  - Preserves `period_id`, `period_type`, `first_date`, and `last_date`.
- `period_from_orm()` maps a `PeriodORM` back into a domain `Period`:
  - Reconstructs the correct `PeriodType` enum.
  - Preserves IDs and date range.
- Tests validate both conversion directions individually and confirm field-by-field equality.

#### Implementation
- Provides two mapping functions:
  - `period_to_orm(period: Period) -> PeriodORM`  
    Directly copies all fields into an ORM instance.
  - `period_from_orm(orm: PeriodORM) -> Period`  
    Copies fields back into a domain `Period`, reconstructing `PeriodType` via enum name lookup.
- The mapping is straightforward: no transformations or optional fields.
- Includes clear docstrings for both functions, describing arguments and return values.

#### Not covered by tests
- Round-trip validation (domain → ORM → domain) is not explicitly tested, though implied by the two unidirectional tests.
- Behaviour with invalid or missing fields (e.g., `None` for `first_date`).
- Behaviour with unexpected or invalid `PeriodType` values in ORM.
- No batch conversion or performance tests.

#### TODOs
- Add a round-trip test to confirm mapping is fully lossless.
- Add negative tests for invalid `PeriodType` or missing dates.
- Extend docstrings with examples to illustrate usage.
- Consider adding utilities for converting lists of periods in bulk.


## Models


### Module: `src/mxm/refdata/models/products/futures_product.py`
- **Test file**: `tests/unittests/models/products/test_futures_product.py`

#### Observed behaviour (from tests)
- `FuturesProduct` can be instantiated with all required fields:
  - `product_id`, `venue`, `description`
  - `currency`, `unit`, `contract_size`
  - `valid_period_rule`, `listing_rule`, `period_types`
  - `settlement`, `last_trading_rule`, `expiry_rule`, `trading_calendar`
- All required attributes are preserved and accessible.
- Optional fields (`trading_hours`, `tick_size`, `tick_value`, `initial_margin`, `maintenance_margin`) can be set at initialization.
- Tests confirm that optional values are correctly stored.

#### Implementation
- Defines an enum `SettlementMethod` with values: `PHYSICAL`, `FINANCIAL`, `CASH`, `OTHER`.
- Defines a frozen dataclass `FuturesProduct` with:
  - Required attributes for product identity, venue, and description.
  - Economic details: `currency`, `unit`, `contract_size`.
  - Rule strings: `valid_period_rule`, `listing_rule`, `last_trading_rule`, `expiry_rule`.
  - Structural attributes: `period_types` (single or list), `settlement` (enum), `trading_calendar`.
  - Optional fields for trading hours, tick/margin data.
- As a `frozen=True` dataclass, instances are immutable once created.
- No validation logic is applied — values are accepted as provided.

#### Not covered by tests
- Behaviour when optional fields are omitted (rely on defaults, not tested).
- Multiple `PeriodType` values (list vs single) not exercised.
- No validation of rule strings (`valid_period_rule`, `listing_rule`, etc.).
- No tests for invalid enum values or improper data types.
- No equality/immutability checks (though implied by `frozen=True`).
- No round-trip interaction with ORM layer tested here.

#### TODOs
- Add tests for:
  - Omission of optional fields (confirm defaults are `None`).
  - Multiple `PeriodType` values (list handling).
  - Invalid enum/data type inputs (should raise at instantiation).
- Consider docstrings/examples explaining usage of rule strings.
- Add type hints for all attributes in tests for stricter coverage.
- Possibly add validation or helper methods for interpreting rules.


### Module: `src/mxm/refdata/models/contracts/futures_contract.py`
- **Test file**: *(none currently implemented)*

#### Implementation
- Defines a frozen dataclass `FuturesContract` with attributes:
  - `contract_id`: Unique identifier for the contract.
  - `product_id`: ID of the associated product.
  - `period_id`: ID of the associated period.
  - `contract_size`: Numeric size of the contract.
  - `unit`: Unit of measurement (inherited from product).
  - `currency`: Currency denomination (inherited from product).
  - `trading_calendar`: Trading calendar identifier (inherited from product).
  - `first_day_of_interest`: Date when the contract becomes active for market data.
  - `last_trading_day`: Final tradable date for the contract.
- `frozen=True` → contracts are immutable once instantiated.
- No validation logic or helper methods — a pure data container.

#### Expected test coverage (based on FuturesProduct precedent)
- **Instantiation tests**:
  - Confirm that a `FuturesContract` can be created with all required attributes.
  - Verify attributes are accessible and immutable.
- **Field integrity tests**:
  - Ensure IDs and attributes are correctly set.
  - Test equality of two contracts with identical attributes.
- **Date handling**:
  - Confirm `first_day_of_interest` and `last_trading_day` accept `datetime.date` and reject invalid types.
  - Verify ordering logic in downstream services (if applicable).
- **Integration expectations**:
  - Round-trip mapping with ORM layer (`futures_contract_vs_orm`).
  - Use inside factories (`futures_contract_factory`) to confirm generated contracts match expected identifiers and dates.

#### Not covered (due to no tests yet)
- No unit tests directly validating instantiation or immutability.
- No tests for equality comparisons between contracts.
- No tests ensuring invalid inputs (e.g. string instead of date) raise appropriate errors.
- No tests confirming expected interaction with product and period IDs.

#### TODOs
- Add unit tests for basic instantiation, immutability, and equality.
- Add tests validating date field integrity and error handling.
- Add round-trip tests for ORM conversion (contracts ↔ ORM).
- Expand service/factory tests to include contract object verification.
- Add docstring examples to clarify intended use in context of product/period.

### Module: `src/mxm/refdata/models/months.py`
- **Test file**: `tests/unittests/models/test_months.py`

#### Observed behaviour (from tests)
- `Month` can be instantiated with a valid integer (1–12).
- Properties:
  - `.as_int` returns the numeric month.
  - `.as_str` returns the 3-letter abbreviation (e.g. `Jan`, `Jun`, `Dec`).
  - `.as_cme_code` returns the CME futures month code (e.g. `F`, `M`, `Z`).
- Invalid initialization (e.g. `0`, `13`) raises `ValueError`.
- `Month.from_str()` correctly maps valid abbreviations (`Jan`, `Feb`, `Dec`) to instances.
- Invalid abbreviation in `from_str` raises `ValueError`.

#### Implementation
- Provides a frozen dataclass `Month` with an integer field `month` (1–12).
- Validates input in `__post_init__`, raising `ValueError` outside range.
- Defines constants:
  - `CME_MONTH_CODES`: standard CME futures month codes (1 → `F`, 12 → `Z`).
  - `MONTH_STRINGS`: three-letter month abbreviations.
  - `MONTH_STRINGS_REVERSE`: reverse lookup for `from_str`.
- Exposes properties:
  - `.as_int`, `.as_str`, `.as_cme_code`.
- Classmethod:
  - `.from_str()` → builds `Month` from abbreviation, validates input.

#### Not covered by tests
- Exhaustive coverage of all months (tests spot-check Jan, Jun, Dec, but not all 12).
- Error messages for invalid inputs are partially checked (only `Foo`, not empty string, wrong case, etc.).
- Equality and hashing of `Month` objects (provided by frozen dataclass, not tested).
- No integration tests (e.g. using `Month` inside `FuturesContract`).

#### TODOs
- Add parameterized tests to cover all 12 months for both `.as_str` and `.as_cme_code`.
- Add negative tests for edge cases (`None`, non-string, lowercase like `"jan"`).
- Add equality/hash tests to confirm immutability and usability in sets/dicts.
- Extend docstrings with examples of CME codes and abbreviations.


### Module: `src/mxm/refdata/models/currencies.py`
- **Test file**: *(none currently implemented)*

#### Implementation
- Defines an `Enum` class `Currency` for ISO 4217-style currency codes.
- Members include major currencies:  
  `AUD`, `CAD`, `CHF`, `EUR`, `GBP`, `HKD`, `INR`, `JPY`, `MXN`,  
  `NOK`, `NZD`, `SEK`, `SGD`, `USD`, `BRL`, `CNY`.
- Each enum entry maps the ISO code (name) → full string description (value).  
  - Example: `Currency.USD.value == "US Dollar"`.  
  - Example: `Currency.EUR.name == "EUR"`.

#### Observed behaviour
- Provides a standardized enumeration for referencing currencies across models (e.g. `FuturesProduct`, `FuturesContract`).
- Designed for immutability and type safety when specifying currency fields.

#### Not covered by tests
- No dedicated test file exists.
- No verification that all required ISO codes are present.
- No test for string conversion (`str(Currency.USD)`), equality, or error handling on invalid values.

#### TODOs
- Add minimal tests to ensure:
  - Correct number of entries.
  - Enum names/values match expected codes and descriptions.
  - Membership checks work (`Currency["USD"] == Currency.USD`).
- Add documentation/example usage in context of products/contracts.
- Consider extending coverage to all ISO 4217 currencies (currently only a subset).

### Module: `src/mxm/refdata/models/periods.py`
- **Test file**: `tests/unittests/models/test_period.py`

#### Observed behaviour (from tests)
- `Period` can be instantiated with valid dates and a `PeriodType`.
- `to_daterange()` returns a `pandas.DatetimeIndex` spanning from `first_date` to `last_date`.
- Immutability enforced by `frozen=True`: attempts to modify fields raise `AttributeError`.
- Single-day periods produce a 1-day date range.
- Invalid date ordering (`first_date > last_date`) raises `ValueError`.
- Equality (`==`) works for identical periods; inequality (`!=`) works for distinct ones.
- `Period` objects are hashable and usable as dict keys.
- String and repr representations return human-readable and debug-friendly formats.
- Sorting:
  - Defined by `PeriodType` priority (Year < Quarter < Month < Week < Day).
  - Ties are resolved by comparing `first_date`.
  - Sorting produces the expected hierarchy in test cases.

#### Implementation
- Defines an `Enum` `PeriodType` with members: `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAY`.
- Defines `PERIOD_PRIORITY` mapping enum values to numeric priorities for ordering.
- `Period` dataclass:
  - Attributes: `period_id`, `period_type`, `first_date`, `last_date`.
  - Validation in `__post_init__` ensures `first_date <= last_date`.
  - `__str__` and `__repr__` provide clean formatting.
  - `__lt__` implements custom sorting using `PERIOD_PRIORITY` + start date.
  - `to_daterange()` uses `pandas.date_range` to expand period to daily index.
- Decorated with `@total_ordering`, so all comparison operators (`<`, `<=`, `>`, `>=`) are supported once `__lt__` and `__eq__` are defined.

#### Not covered by tests
- Edge cases in sorting:
  - Comparing periods of the same type with identical `first_date` (tie-breaking not explicitly tested).
  - Comparing `Period` against non-`Period` object (should return `NotImplemented`).
- Performance on very large date ranges (not critical, but untested).
- Enum completeness validation (ensuring all `PeriodType` values are supported in `PERIOD_PRIORITY`).
- No integration tests with contracts/products (though clearly designed for that).

#### TODOs
- Add tests for:
  - Sorting ties with identical start dates.
  - Comparison with non-`Period` object (should not crash).
  - Very large periods (e.g. multi-decade `YEAR`).
- Add usage docstring examples for each `PeriodType`.
- Consider adding helper constructors (`Period.from_year(2024)`, `Period.from_month(2024, 1)`).
- Explore extending `PeriodType` with trading-specific categories (if required by business logic).

### Module: `src/mxm/refdata/models/weekdays.py`
- **Test file**: `tests/unittests/models/test_weekdays.py`

#### Observed behaviour (from tests)
- `Weekday` can be created directly from an integer (0–6 → Monday–Sunday).
- `Weekday.from_str()` can parse:
  - Full names (`"Monday"`, `"Tuesday"`, …).
  - Abbreviations (`"Mon"`, `"Tue"`, …).
  - Lowercased inputs (`"mon"`, `"tue"`, …).
- Properties:
  - `.as_int` returns the numeric index (0–6).
  - `.as_str` returns the full name.
  - `.as_abbr` returns the three-letter abbreviation.
- Invalid inputs raise `ValueError`:
  - Out-of-range integers (`-1`, `7`).
  - Invalid names/abbreviations (`"Funday"`, `"Tuesd"`).

#### Implementation
- Defines constants for weekday representations:
  - `WEEKDAY_STRINGS` → integer → full name.
  - `WEEKDAY_STRINGS_ABBR` → integer → abbreviation.
  - `WEEKDAY_LOOKUP` → reverse lookup for case-insensitive names/abbreviations.
- `Weekday` dataclass:
  - Immutable (`frozen=True`).
  - Validates input range in `__post_init__`.
  - Properties `.as_int`, `.as_str`, `.as_abbr`.
  - Classmethod `.from_str()` performs reverse lookup and raises `ValueError` on invalid inputs.

#### Not covered by tests
- Equality and hashing of `Weekday` instances (provided by dataclass).
- String conversion (`str(Weekday(0))`) and `repr` output.
- Iteration across all 7 weekdays (tests cover all individually, but not parameterized “all 7 in one run”).
- Integration with other models (e.g., in `nth_weekday_of_period` trading calendar rules).

#### TODOs
- Add tests for equality, hashing, and repr/str behaviour.
- Add parameterized test to iterate across all weekdays 0–6 in one pass.
- Extend docstrings with usage examples for `.from_str()`.
- Consider adding helper functions (`Weekday.monday()`, `Weekday.sunday()`) for readability.

### Modules: ORM Models
- `src/mxm/refdata/models/orm/futures_contracts.py`
- `src/mxm/refdata/models/orm/futures_products.py`
- `src/mxm/refdata/models/orm/periods.py`
- `src/mxm/refdata/models/orm/base.py`

#### Implementation
- **`Base`**
  - Provides the SQLAlchemy declarative base for all ORM models.

- **`FuturesContractORM`**
  - Table: `futures_contracts`.
  - Columns:
    - `contract_id` (PK, string).
    - `product_id` (FK → `futures_products.product_id`).
    - `period_id` (FK → `periods.period_id`).
    - `contract_size` (float).
    - `currency` (enum → `Currency`).
    - `unit` (enum → `ProductUnit`).
    - `trading_calendar` (string).
    - `first_day_of_interest` (string).
    - `last_trading_day` (string).
  - Relationships:
    - `product` ↔ `FuturesProductORM.contracts`.
    - `period` ↔ `PeriodORM.contracts`.

- **`FuturesProductORM`**
  - Table: `futures_products`.
  - Columns:
    - Identifiers: `product_id` (PK, string), `venue` (string), `description` (text).
    - Economics: `currency` (enum), `unit` (enum), `contract_size` (float).
    - Rules: `valid_period_rule`, `listing_rule`, `last_trading_rule`, `expiry_rule` (all text).
    - Period support: `period_types` (enum → `PeriodType`).
    - Settlement: `settlement` (enum → `SettlementMethod`).
    - Market details: `trading_calendar` (string), `trading_hours` (optional text).
    - Market microstructure: `tick_size`, `tick_value` (floats).
    - Risk parameters: `initial_margin`, `maintenance_margin` (floats).
  - Relationships:
    - `contracts` ↔ `FuturesContractORM.product` (cascade delete-orphan).

- **`PeriodORM`**
  - Table: `periods`.
  - Columns:
    - `period_id` (PK, string).
    - `period_type` (enum → `PeriodType`).
    - `first_date`, `last_date` (dates).
  - Relationships:
    - `contracts` ↔ `FuturesContractORM.period`.

#### Observed behaviour
- Provide persistent storage for core reference data entities (Products, Contracts, Periods).
- Mirror the structure of domain models in `mxm.refdata.models`, enabling bidirectional mapping via `orm_converter`.
- Enforce referential integrity (contracts link to products and periods).

#### Not covered by tests
- No direct unit tests exist for ORM classes.
- Integrity constraints are not explicitly validated in tests (e.g., foreign key enforcement).
- No tests confirm cascade delete-orphan behaviour on products → contracts.
- No tests check enum persistence and retrieval (currency, unit, period type, settlement).
- No round-trip tests (domain → ORM → DB → ORM → domain).

#### TODOs
- Rename module files to _orm.py
- Add integration tests to confirm:
  - Schema creation and table relationships.
  - Cascade delete-orphan works correctly.
  - Enum values persist to DB and reload properly.
  - Contracts cannot exist without valid product and period.
- Add docstrings/examples for each ORM class clarifying its relationship to the domain model.
- Consider naming convention review:
  - Current files are plural (`futures_contracts.py`) but classes are singular (`FuturesContractORM`).
  - To avoid confusion, renaming files to singular (`futures_contract_orm.py`, `futures_product_orm.py`, `period_orm.py`) would better match the class names and conventions.

### Module: `/src/mxm/refdata/models/units.py`
- **Test file**: *(none currently implemented)*

#### Implementation
- Defines an `Enum` class `ProductUnit` for physical units used in financial contracts.
- Covers a wide range of unit categories:
  - General: `LOT`, `CONTRACT`, `NOTIONAL`.
  - Securities: `SHARE`, `BOND`.
  - Commodities: `BARREL`, `TONNE`, `BUSHEL`, `TROY_OUNCE`, `OUNCE`, `GRAM`, `LITER`, `METRIC_TON`.
  - Energy: `MWH`, `GALLON`, `CUBIC_METER`, `MMBTU`.
  - FX/financial: `CURRENCY_UNIT`, `GBP`.
  - Index-based: `INDEX_POINT`.
- Each enum member maps a symbolic name (e.g. `ProductUnit.TONNE`) to a descriptive string (e.g. `"Tonne"`).

#### Observed behaviour
- Provides a controlled vocabulary of units to ensure consistency across `FuturesProduct` and `FuturesContract`.
- Intended for immutability and type safety in product/contract specifications.

#### Not covered by tests
- No verification that enum contains expected members.
- No tests for string conversion (`str(ProductUnit.TONNE)` → `"ProductUnit.TONNE"`).
- No tests for equality, membership, or error handling on invalid keys.
- Overlap/redundancy not validated (e.g., `TONNE` vs `METRIC_TON`, `CURRENCY_UNIT` vs `GBP`).

#### TODOs
- Add minimal unit tests to confirm:
  - Correct number of entries.
  - Membership resolution (`ProductUnit["TONNE"] == ProductUnit.TONNE`).
  - String/value equality (`ProductUnit.TROY_OUNCE.value == "Troy Ounce"`).
- Add docstring examples showing integration with `FuturesProduct`.
- Consider rationalizing overlapping entries (`TONNE` vs `METRIC_TON`) to avoid ambiguity.
- Decide whether currency units like `GBP` belong here or exclusively in `currencies.py` (possible cleanup task).


### Module: `src/mxm/refdata/models/reference_events.py`
- **Test file**: *(none currently implemented)*

#### Implementation
- Defines an `Enum` class `ReferenceEvent` representing categories of reference events used in last trading day rules.
- Members:
  - `BUSINESS_DAY_OF_PERIOD` → `"business_day_of_period"`.
  - `CALENDAR_DAY_OF_PERIOD` → `"calendar_day_of_period"`.
  - `WEEKDAY_OF_PERIOD` → `"weekday_of_period"`.
- Docstring clarifies its purpose: a controlled set of valid reference events for trading calendar rules.

#### Observed behaviour
- Provides standard identifiers for reference-day logic, ensuring consistency when constructing or parsing rules.
- Enum values are lowercase strings suitable for serialization (e.g., JSON configs).

#### Not covered by tests
- No verification that enum members match the expected set of strings.
- No test for string conversion (`str(ReferenceEvent.BUSINESS_DAY_OF_PERIOD)`).
- No integration test showing use of these values inside rule-evaluating modules (e.g. `trading_calendars/`).

#### TODOs
- Add a minimal test file:
  - Verify enum contains exactly three members.
  - Assert name/value mapping consistency.
- Add usage examples in docstrings (e.g. how `ReferenceEvent.WEEKDAY_OF_PERIOD` integrates with last trading day rules).
- Consider extending if future reference events are required (e.g. holidays, exchange-specific cutoffs).

## Parsing

### Module: `src/mxm/refdata/parsing/futures_products_from_csv.py`
- **Test file**: `tests/unittests/parsing/test_futures_products_from_csv.py`

#### Observed behaviour (from tests)
- Parsing a valid CSV file returns a list of normalized futures product dictionaries.
- Required fields (`product_id`, `venue`, `description`, `currency`, `unit`, `contract_size`, `valid_period_rule`, `listing_rule`, `period_types`, `settlement`, `last_trading_rule`, `expiry_rule`, `trading_calendar`, `trading_hours`, `tick_size`, `tick_value`) must all be present:
  - If missing → raises `ValueError`.
- Optional fields (`initial_margin`, `maintenance_margin`) may be omitted:
  - If missing → returned as `None`.
- Values are normalized into correct types:
  - `currency` → `Currency` enum.
  - `unit` → `ProductUnit` enum.
  - `period_types` → `PeriodType` enum.
  - `settlement` → `SettlementMethod` enum.
  - Numeric fields (`contract_size`, `tick_size`, `tick_value`, margins) cast to `float`.
- Tests check field-by-field equality for both a gold futures and corn futures example.

#### Implementation
- Uses Python’s `csv.DictReader` to read the file into rows.
- For each row:
  - Validates presence of all required fields.
  - Constructs a normalized dictionary with explicit type conversions.
  - Handles optional numeric fields by returning `None` if missing.
- Returns a list of normalized product dictionaries.

#### Not covered by tests
- Behaviour with malformed CSV (extra/unexpected columns, bad formatting).
- Invalid enum values (e.g. currency `XYZ`, settlement `FOO`) — would raise `KeyError` but untested.
- Invalid numeric values (non-float strings in `contract_size`, `tick_size`, etc.).
- Handling of duplicate products (no deduplication or error expected, not tested).
- Performance on very large CSVs (not critical, untested).

#### TODOs
- Add negative tests for:
  - Invalid enum values.
  - Non-numeric strings in numeric fields.
  - Empty or malformed CSV files.
- Add parameterized tests covering each enum field (currency, unit, period type, settlement).
- Extend docstring with a CSV schema specification and example.
- Consider stricter schema enforcement (e.g. via Pydantic models for row validation).
- Investigate integration tests with ORM/domain models (ensuring parsed data feeds correctly into `FuturesProduct` objects).

## Services / Factories

### Module: `src/mxm/refdata/services/futures_contract_factory.py`
- **Test file**: `tests/unittests/services/test_futures_contract_factory.py`

#### Observed behaviour (from tests)
- `create_contracts_for_product` generates `FuturesContract` objects for valid periods of a product.
- Three product cases covered:
  - **All months product** → 12 contracts (Jan–Dec).
  - **Partial months product** → contracts only in months specified by `valid_period_rule` (`GJNV` → Feb, Apr, Jul, Nov).
  - **Quarterly product** → contracts only in Mar, Jun, Sep, Dec (`HMUZ`).
- Tests confirm:
  - Number of contracts matches expectation.
  - Generated contract IDs match the `product_id.period_id` pattern.
- Patches mock rule sets (`TRADING_RULES` and `FIRST_DAY_OF_INTEREST_RULES`) to enable deterministic calculation of trading dates.

#### Implementation
- `FuturesContractFactory` is a **singleton** (thread-safe via lock).
- Maintains an internal cache (`_cache`) keyed by contract ID to avoid re-creating contracts.
- Key methods:
  - `create_contracts_for_product(product, available_periods)`:  
    Iterates over available periods, filters by product’s `period_types` and `valid_period_rule`, creates contract IDs, and either retrieves from cache or generates new contracts.
  - `_is_valid_period(product, period)`:  
    Validates whether a period matches the product’s valid CME month codes.
  - `_create_contract_id(product_id, period_id)`:  
    Constructs a unique ID (`Product.Period`).
  - `create_contract(product, period)`:  
    Builds a `FuturesContract` object by:
    - Initializing a `TradingCalendar`.
    - Computing `last_trading_day` via `calculate_last_trading_day`.
    - Computing `first_day_of_interest` via `calculate_first_day_of_interest`.
    - Passing all relevant product/period details into the contract.
  - `clear_cache()`: clears cached contracts.

#### Not covered by tests
- Cache behaviour:
  - No test ensures that repeated contract creation reuses cached objects rather than instantiating new ones.
- Multi-threaded access not tested (singleton + lock not stressed).
- Validation fallback:
  - Non-monthly period types (`WEEK`, `DAY`, `YEAR`) not covered.
- Edge cases:
  - Products with empty `valid_period_rule`.
  - Periods with invalid IDs or misaligned dates.
- Correctness of trading date calculations:
  - Mocked in tests — actual integration with `TradingCalendar` not validated.

#### TODOs
- Add tests for:
  - Cache reuse (`create_contracts_for_product` called twice → same object reused).
  - Non-monthly period types (should default to `True` in `_is_valid_period`).
  - Edge cases: empty/invalid `valid_period_rule`.
  - Invalid/missing trading rules (should raise error).
- Add integration test without patched rules (real trading rules).
- Document caching behaviour explicitly in docstrings.
- Consider exposing `get_contract_by_id` for external cache access.

### Module: `src/mxm/refdata/services/futures_product_factory.py`
- **Test file**: *(none currently implemented)*

#### Implementation
- Provides a **singleton factory** for creating and caching `FuturesProduct` objects.
- Key features:
  - **Singleton pattern**:
    - `__new__` ensures only one instance is created.
    - Protected by a threading lock for thread safety.
  - **Internal cache** (`_cache`):
    - Dict keyed by `product_id`.
    - Ensures repeated requests for the same product return the cached instance.
  - **Methods**:
    - `create_from_normalized_data(data: dict)`:
      - Builds a `FuturesProduct` from normalized dictionary (likely parsed via CSV).
      - Caches and reuses by `product_id`.
    - `initialise_from_csv(csv_file_path: str)`:
      - Parses a CSV into normalized data (`parse_futures_products_csv_to_normalised_data`).
      - Creates and caches all products via the factory.
    - `get_product(product_id, **kwargs)`:
      - Retrieves a product from cache, or builds it from provided kwargs if not already cached.

#### Expected behaviour
- Ensures uniqueness: each `product_id` corresponds to exactly one cached `FuturesProduct`.
- Supports bulk initialization from CSV.
- Provides both explicit (`create_from_normalized_data`) and fallback (`get_product`) creation pathways.
- Thread-safe instantiation, though caching itself is not guarded by locks.

#### Not covered by tests
- No validation that:
  - Singleton behaviour works (only one instance exists).
  - Cache reuses objects instead of creating duplicates.
  - `initialise_from_csv` correctly loads multiple products.
- No tests for cache misses with `get_product` (kwargs path).
- No negative tests for invalid or incomplete data.
- Thread-safety of cache access is untested.

#### TODOs
- Add tests for:
  - Singleton behaviour (two factory instances are identical).
  - Cache reuse (calling twice with same `product_id` returns same object).
  - Bulk load via `initialise_from_csv`.
  - Edge cases: missing fields in normalized data, duplicate rows in CSV.
- Consider locking around cache writes (`_cache`) for thread safety beyond singleton instantiation.
- Add docstring examples for CSV initialization and cache usage.


### Module: `src/mxm/refdata/services/period_factory.py`
- **Test file**: `tests/unittests/services/test_period_factory.py`

#### Observed behaviour (from tests)
- `get_period`:
  - Retrieves a `Period` by `period_id` or by `date` + `PeriodType`.
  - Caches results: repeated calls with same input return the same object (identity check passes).
  - Invalid `period_id` raises `ValueError`.
- `calculate_period_dates`:
  - Correctly computes `first_date` and `last_date` for `YEAR`, `MONTH`, `QUARTER`, and `WEEK`.
  - Handles leap years (Feb-2024 ends on 29th).
  - Raises `ValueError` for unsupported types or malformed IDs.
- `shift_date_by_n_periods`:
  - Shifts dates forward/backward by given number of periods (year, month, quarter, week).
  - Handles negative shifts correctly.
  - Raises `ValueError` for unsupported types.
- `shift_period_by_n`:
  - Shifts a `Period` object itself (not just a date) forward/backward.
  - Tested for months, quarters, years, and weeks.
  - Raises `TypeError` if `n` is not an integer.
- `get_next_n_periods`:
  - Returns a sequence of `n` consecutive periods starting at a given date.
  - Optionally includes or excludes the current period.
- `get_periods_in_range`:
  - Returns all periods between `start_date` and `end_date`.
  - Can include/exclude partial final periods.

#### Implementation
- **Singleton with caching**:
  - Ensures only one `PeriodFactory` instance exists.
  - Flyweight pattern: `Period` objects are cached by `period_id` and reused.
  - Cache is class-level (`_period_cache`).
- **Parsing and construction**:
  - `_period_type_from_period_id`: infers `PeriodType` from regex patterns (`PERIOD_TYPE_PARSING_MAP`).
  - `_create_from_date`: constructs a `Period` from a date and type.
  - Dedicated calculators for year, month, quarter, and week boundaries.
- **Date shifting utilities**:
  - Implemented separately for year, month, quarter, week.
  - Ensure arithmetic consistency (month rollovers, leap years).
- **Enums for configuration**:
  - `HandleCurrentPeriod` and `HandlePartialEndPeriod` define explicit options for inclusion/exclusion logic.

#### Not covered by tests
- Edge case: shifting a date like `31-Jan` forward by one month (day overflow).
- Sorting/comparison of returned periods (delegated to `Period`, but integration not tested).
- Cache eviction or memory growth (cache only grows; no tests on long-running usage).
- Thread safety: singleton creation is protected, but cache writes are not tested under concurrency.
- Period types beyond `YEAR`, `MONTH`, `QUARTER`, `WEEK` (e.g. `DAY`) are not supported — but lack explicit negative tests for requests of type `DAY`.

#### TODOs
- Add tests for:
  - Edge case date shifts (`31-Jan` forward/backward).
  - Concurrency (two threads requesting same period simultaneously).
  - Cache growth behaviour (does not evict).
- Consider extending support for `DAY` periods.
- Document explicitly that caching means identical `Period` objects are reused (flyweight).
- Add docstring usage examples for shifting and range generation.


### Module: `src/mxm/refdata/services/ref_data_service.py`
- **Test file**: `tests/unittests/services/test_ref_data_service_initialisation.py`

#### Observed behaviour (from tests)
- `initialise_periods`:
  - Populates `PeriodORM` table with periods for a given date range.
  - Ensures months (and other period types) are correctly created.
  - Verified with queries against the in-memory DB.
- `initialise_futures_products`:
  - Uses `FuturesProductFactory.initialise_from_csv` to load products.
  - Inserts them into `FuturesProductORM`.
  - Test confirms product ID and description are persisted.
- `initialise_futures_contracts`:
  - Requires periods and products to be present.
  - Uses `FuturesContractFactory.create_contracts_for_product` to generate contracts.
  - Inserts them into `FuturesContractORM`.
  - Test confirms contract ID, product ID, and period ID match expectations.
- `setup_instruments`:
  - High-level orchestration method: initialises periods → products → contracts.
  - Verified that all three tables contain expected entities.
- `reset_database`:
  - Drops and re-initialises DB.
  - Verified that all tables are empty afterwards.

#### Implementation
- **Role**: orchestrator service that ties together factories and the database.
- Depends on:
  - `SQLSessionManager` (DB sessions).
  - `FuturesProductFactory` and `FuturesContractFactory` (object creation).
  - `PeriodFactory` (time dimension management).
  - `orm_converter` for object ↔ ORM conversions.
- Key methods:
  - `reset_database`: drops & re-initialises schema.
  - `_is_database_empty`: internal helper, checks all main tables.
  - `is_table_empty`: table-specific emptiness check.
  - `setup_instruments`: convenience function for full setup (date range + CSV).
  - `initialise_futures_products`: loads products (from CSV or config default).
  - `initialise_periods`: generates periods for range/types, inserts into DB.
  - `initialise_futures_contracts`: generates contracts for existing products & periods, inserts into DB.
- Logging is integrated to track lifecycle stages.

#### Not covered by tests
- `_is_database_empty` is not directly tested.
- `is_table_empty` is only indirectly tested.
- Error conditions:
  - Attempting to initialise products/contracts when DB is not empty.
  - Running `initialise_contracts` without periods or products.
  - Invalid/missing CSV file path in `initialise_futures_products`.
- Integration of real CSV parsing and contract generation (tests patch factories).
- Multi-table consistency (e.g. referential integrity between products/contracts/periods).

#### TODOs
- Add tests for:
  - `_is_database_empty` and `is_table_empty`.
  - Negative paths (re-initialisation without reset, missing data dependencies).
  - Real (non-patched) CSV and contract factory runs.
- Consider enforcing referential integrity explicitly (e.g. cascade deletes).
- Improve logging: include counts of inserted products/contracts/periods.
- Align config handling with `mxm-config` (currently `load_config` is used directly).

## Trading Calendars

### Module: `src/mxm/refdata/trading_calendars/first_day_of_interest.py`
- **Test file**: `tests/unittests/trading_calendars/test_first_day_of_interest.py`

#### Observed behaviour (from tests)
- `calculate_first_day_of_interest(product_id, period, trading_calendar)`:
  - For valid rules, returns the correct first day of interest (business day).
  - Handles product-specific month shift rules from JSON.
  - Tested with several futures products (gold, corn, GBP, S&P 500, natural gas).
  - Invalid cases:
    - Non-existent `product_id` → raises `ValueError`.
    - Invalid `period_type` (not `MONTH`) → raises `ValueError`.
    - Missing month in JSON rules → raises `KeyError`.

#### Implementation
- Loads rules from JSON (`first_day_of_interest_rule.json`) at import time.
- For a given product and period:
  - Validates product exists in rules.
  - Ensures period type is `MONTH`.
  - Looks up month-specific shift (`n_shift` mapping) from rules.
  - Shifts the period backwards using `PeriodFactory.shift_period_by_n`.
  - Applies a `reference_rule` to determine base date:
    - `"next_b_day_after_last_trading_day_of_december"` → uses `calculate_last_trading_day` of December.
    - `"next_b_day_after_period"` → uses shifted period’s last date.
    - Any other → raises `ValueError`.
  - Returns the first business day after the reference date, using the product’s trading calendar.

#### Not covered by tests
- Reference rule validation:
  - No test for invalid `reference_rule` (would raise `ValueError`).
- Integration with real-world trading calendars:
  - Tests mock expected outcomes but don’t validate actual calendars.
- Boundary cases:
  - Leap-year December dates.
  - Contracts with shift values beyond dataset coverage.
- JSON loading:
  - No test for missing or malformed `first_day_of_interest_rule.json`.

#### TODOs
- Add tests for:
  - Invalid `reference_rule` values.
  - Leap-year handling (December 31 in leap vs non-leap years).
  - Extreme shifts (very large `n_shift` values).
- Improve error handling for JSON loading (currently raises at import if file missing).
- Consider lazy loading of rules instead of global import.
- Add docstring usage example for how rules are defined in JSON and applied.


### Module: `src/mxm/refdata/trading_calendars/last_trading_day.py`
- **Test file**: `tests/unittests/trading_calendars/test_last_trading_day.py`

#### Observed behaviour (from tests)
- `calculate_last_trading_day(product_id, period, trading_calendar)`:
  - Computes contract termination dates using product-specific rules loaded from JSON (`last_trading_rule.json`).
  - Handles different rule types:
    - **Business day rule**: e.g., gold futures terminate on the 3rd last business day of June.
    - **Business day of prior month**: e.g., natural gas terminates on 3rd last business day of May.
    - **Calendar day rule**: e.g., corn futures terminate 1 business day before June 15.
    - **Weekday rule**: e.g., GBP futures terminate 2 business days before the 3rd Wednesday.
    - **Direct weekday**: e.g., S&P 500 E-mini expires on the 3rd Friday.
  - Raises:
    - `KeyError` if product ID not found in rules.
    - `ValueError` if rule is malformed (e.g., missing `"weekday"` key for weekday rules).

#### Implementation
- Loads trading rules from JSON file at import time (`./data/last_trading_rule.json`).
- For a given product + period:
  1. Looks up product’s trading rule in `TRADING_RULES`.
  2. Applies `period_offset` to shift period if necessary.
  3. Determines **reference event** (`BUSINESS_DAY_OF_PERIOD`, `CALENDAR_DAY_OF_PERIOD`, `WEEKDAY_OF_PERIOD`).
     - Business day → calls `get_nth_business_day_of_period`.
     - Calendar day → calls `get_nth_calendar_day_of_period`.
     - Weekday → calls `get_nth_weekday_of_period` with explicit weekday parsing.
  4. Applies optional `business_day_offset` to adjust final result.
  5. Returns final `last_trading_day` as `datetime.date`.

#### Not covered by tests
- Malformed JSON rules:
  - Invalid `reference_event` string.
  - Missing required keys (`n_reference`, `period_offset`).
- Negative offsets (e.g., `business_day_offset = -1`).
- Edge cases:
  - Leap years (e.g., Feb 29 expiry).
  - Period boundaries crossing into holidays/weekends.
- File handling errors: missing or corrupted `last_trading_rule.json`.

#### TODOs
- Add tests for:
  - Invalid `reference_event` → should raise `ValueError`.
  - Negative `business_day_offset`.
  - Leap-year expiries (Feb contracts).
  - Holiday/weekend handling near expiry date.
- Improve robustness of JSON loading:
  - Currently hard-coded relative path `./data/last_trading_rule.json`.
  - Should integrate with `mxm-config` for flexible config paths.
- Add explicit logging for rule parsing (useful for debugging mis-specified rules).
- Consider lazy loading of rules to allow dynamic configuration.


### Module: `src/mxm/refdata/trading_calendars/nth_business_day.py`
- **Test file**: `tests/unittests/trading_calendars/test_nth_business_day_of_period.py`

#### Observed behaviour (from tests)
- `get_nth_business_day_of_period(period, n, trading_calendar)`:
  - Returns the N-th business day within a given period.
  - Supports:
    - Positive indexing: `n=1` → first business day, `n=5` → fifth business day.
    - Negative indexing: `n=-1` → last business day, `n=-5` → fifth-last business day.
  - Works for both **monthly periods** (e.g. `Jun-2025`) and **quarterly periods** (e.g. `2025-Q3`).
  - Raises `ValueError` if `n` is out of range (e.g. requesting 25th business day in a shorter month).

#### Implementation
- Uses `Period.to_daterange()` to expand the period into all days.
- Filters those days through the `TradingCalendar.get_sessions_in_range` to get valid business days.
- Selects the correct business day using:
  - `business_days[n-1]` for positive indices.
  - `business_days[n]` for negative indices.
- Returns as a `datetime.date`.
- Raises `ValueError` if the requested index does not exist.

#### Not covered by tests
- Edge cases with very short months (e.g., February with <20 business days).
- Handling of holidays and half-days in `TradingCalendar` (assumed correct but untested here).
- Invalid `n=0` (would currently raise `business_days[-1]` silently, not explicitly tested).
- Non-standard `PeriodType` (e.g., `WEEK` or `DAY`) not exercised.

#### TODOs
- Add tests for:
  - `n=0` to confirm intended behaviour (should raise `ValueError` explicitly).
  - February periods, especially in leap years.
  - Weeks and days as `PeriodType`, not only months/quarters.
- Extend docstring with examples for negative indexing.
- Add validation for `n=0` (raise `ValueError` instead of silently returning last business day).
- Consider optimization for long date ranges (though not critical).


### Module: `src/mxm/refdata/trading_calendars/nth_calendar_day_of_period.py`
- **Test file**: `tests/unittests/trading_calendars/test_nth_calendar_day_of_period.py`

#### Observed behaviour (from tests)
- `get_nth_calendar_day_of_period(period, n)`:
  - Returns the N-th **calendar day** of the given period.
  - Supports positive and negative indexing:
    - Positive: `n=1` → first day of the period, `n=15` → 15th day.
    - Negative: `n=-1` → last day of the period, `n=-5` → 5th last day.
  - Works for both **months** (e.g. `Jun-2025`) and **quarters** (e.g. `2025-Q3`).
  - Raises `ValueError` when `n` is out of range (too large or too negative).

#### Implementation
- Expands the period into all days using `Period.to_daterange()`.
- Applies indexing logic:
  - `all_days[n-1]` for positive `n`.
  - `all_days[n]` for negative `n`.
- Wraps `IndexError` in a `ValueError` with descriptive message.
- Returns result as a `datetime.date`.

#### Not covered by tests
- Edge cases:
  - `n=0` (currently would incorrectly map to last day, not explicitly checked).
  - Periods with unusual lengths (e.g., leap-year February).
- Invalid inputs:
  - Non-integer `n` (e.g. `None`, float).
  - Invalid or malformed `Period` object.
- Performance for very large ranges (not critical here).
- Integration with higher-level modules (e.g. `last_trading_day.py`).

#### TODOs
- Add test for `n=0` to confirm behaviour (should raise `ValueError`).
- Add leap-year test case (e.g., Feb-2024 with 29 days).
- Add type validation for `n` (explicitly enforce integer).
- Extend docstring examples with both month and quarter use cases.
- Consider parameterized tests for all 12 months to guarantee robustness.


### Module: `src/mxm/refdata/trading_calendars/nth_weekday_of_period.py`
- **Test file**: `tests/unittests/trading_calendars/test_nth_weekday_of_period.py`

#### Observed behaviour (from tests)
- `get_nth_weekday_of_period(period, weekday, n)`:
  - Accepts `weekday` as int (0–6), full name (`"Monday"`), or abbreviation (`"Mon"`).
  - `n > 0`: returns the N-th weekday from the start of the period.
    - Example: 2nd Wednesday of June 2025 → June 11.
  - `n < 0`: returns the N-th weekday counting backwards from the end.
    - Example: -2 Wednesday of June 2025 → June 18.
  - Works for both months and quarters.
  - Raises `ValueError` if the requested N-th weekday does not exist (e.g., 6th Thursday in a 4-week month).

#### Implementation
- Converts weekday strings into integers via `Weekday.from_str()`.
- Iterates over all dates in the period (`Period.to_daterange()`), filters those matching the target weekday.
- Uses standard Python indexing:
  - `dates[n-1]` for positive indices.
  - `dates[n]` for negative indices.
- Wraps `IndexError` into `ValueError` with descriptive message.

#### Not covered by tests
- Edge case: `n=0` (would incorrectly map to `dates[-1]` instead of raising).
- Case sensitivity for weekday strings (`"monday"` vs `"Monday"`) not explicitly tested (though `.from_str()` likely handles).
- Behaviour for unusual periods:
  - `WEEK` or `DAY` period types (tests only cover month/quarter).
- Performance for long periods (not critical here).

#### TODOs
- Add explicit check for `n=0` → raise `ValueError`.
- Add tests for:
  - Lowercase weekday names (`"monday"`, `"fri"`).
  - Non-month/quarter periods (e.g. `PeriodType.WEEK`).
- Add integration tests with `last_trading_day.py` to confirm weekday rules resolve correctly in expiry logic.
- Extend docstrings with examples for both forward and reverse indexing.

### Module: `src/mxm/refdata/trading_calendars/trading_calendar.py`
- **Test file**: `tests/unittests/trading_calendars/test_trading_calendar.py`

#### Observed behaviour (from tests)
- `TradingCalendar("CME")` fixture creates an exchange calendar.
- Supported operations:
  - `get_sessions_in_range(start, end)` → returns sessions as `DatetimeIndex`.
  - `shift_sessions(session, offset)` → shifts by ±N sessions, preserves naive `pd.Timestamp`.
  - `get_session_dates_in_range(start, end)` → returns session dates as Python `date` list.
  - `shift_session_date(date, offset)` → shifts business dates correctly.
  - `get_session_open(session)` / `get_session_close(session)` → returns open/close times.
  - `is_trading_day(date)` → `True` for trading days, `False` for weekends.
  - `get_last_prior_session_date(date)`:
    - Returns same day if valid trading day.
    - For weekends/holidays → returns last trading day before.
    - Raises `DateOutOfBounds` if before first session.
  - `get_nth_business_day_relative_to_date(date, n)`:
    - Handles positive/negative offsets.
    - Handles weekends/holidays by snapping to last valid session before.
    - `n=0` returns same day if business day, or last valid business day otherwise.

#### Implementation
- Wraps around `exchange_calendars` library (`xcals.get_calendar`).
- Handles optional `start` and `end` bounds for loaded calendar.
- Methods:
  - Query sessions and their open/close times directly from `calendar.schedule`.
  - Convert sessions to `date` for higher-level usage.
  - Logic for `get_last_prior_session_date`: decrements by one day until a valid session is found; raises `ValueError` if before `first_session`.
  - `get_nth_business_day_relative_to_date`: adjusts `n` if starting from a non-trading day.

#### Not covered by tests
- Initialization edge cases:
  - Invalid calendar name (should raise `ValueError`).
  - Using `start`/`end` parameters explicitly.
- Error handling:
  - `get_last_prior_session_date` in implementation raises `ValueError`, while tests expect `DateOutOfBounds`. Potential mismatch.
- Timezones:
  - Open/close times are returned in UTC; behaviour if calendar has local session times is untested.
- Extreme boundaries:
  - Shifting sessions near calendar start/end.
  - Multi-year ranges in `get_sessions_in_range`.

#### TODOs
- Add tests for:
  - Invalid `calendar_name` → raises `ValueError`.
  - Calendars with custom start/end bounds.
  - `get_last_prior_session_date` edge mismatch (decide on consistent exception type).
  - Timezone handling (assert explicitly UTC vs local).
- Improve error consistency:
  - Align exception type with tests (`DateOutOfBounds` vs `ValueError`).
- Integration: ensure this wrapper plays cleanly with other rule calculators (`nth_business_day`, `last_trading_day`, etc.).
- Add richer docstrings with examples (daily, weekly, quarterly use cases).


## Utils

### Module: `src/mxm/refdata/utils/cache_manager.py`
- **Test file**: `tests/unittests/utils/test_cache_manager.py`

#### Observed behaviour (from tests)
- Decorator `@CacheManager.cached_function(expire_after=...)`:
  - Wraps a function to provide memoization with optional expiry.
  - When called repeatedly with the same arguments:
    - Returns cached value if within expiry.
    - Recomputes value if expired.
  - Cache is keyed by `(function, args, kwargs)`.
- `CacheManager.clear_cache()`:
  - Empties all cached results.
- `CacheManager.get_cache()`:
  - Exposes current cache contents for inspection.

#### Implementation
- Class-level cache implemented as `cachetools.TTLCache`.
  - Default `maxsize=1024`.
  - TTL controlled by decorator argument (`expire_after`).
- `cached_function`:
  - Wraps the function with `cachetools.cached` and `TTLCache`.
  - Uses a new TTLCache instance per wrapped function.
- `clear_cache`:
  - Resets `_caches` dict, clearing all function caches.
- `get_cache`:
  - Returns internal `_caches` dict for debugging or monitoring.

#### Not covered by tests
- Cache eviction when `maxsize` exceeded.
- Behaviour under concurrency (thread safety of `cachetools`).
- Using decorator on methods (bound `self` argument).
- Error handling:
  - Decorating non-callables.
  - Misconfigured TTL values (e.g., negative).

#### TODOs
- Add tests for:
  - Cache eviction (over 1024 entries).
  - Negative/zero `expire_after`.
  - Usage on class methods (ensure proper caching by instance).
- Consider allowing `maxsize` configuration per function.
- Improve introspection: expose per-function hit/miss statistics.
- Extend docstring examples for monitoring cache contents.


### Module: `src/mxm/refdata/utils/config.py`
- **Test file**: `tests/unittests/utils/test_config.py`

#### Observed behaviour (from tests)
- `load_config(file_path: str)`:
  - Loads configuration from a TOML file.
  - Returns the parsed config as a `Config` object (Pydantic-based).
  - Raises `FileNotFoundError` if the file does not exist.
- `Config` model:
  - Pydantic `BaseSettings` subclass.
  - Accepts fields such as `database_url`, `csv_path`, `log_level`.
  - Validates required fields are present and of correct type.

#### Implementation
- Uses `pydantic_settings.BaseSettings` for configuration.
- `Config` class declares typed attributes with defaults where applicable.
- `load_config`:
  - Reads TOML via `tomllib`.
  - Instantiates `Config` with parsed values.
- Designed for local/static configuration management.

#### Not covered by tests
- Validation failures:
  - Malformed TOML structure.
  - Wrong data types (e.g., non-string `database_url`).
- Environment variable overrides (Pydantic supports this).
- Default values not explicitly tested.
- No tests for logging configuration integration.

#### TODOs
- Add tests for:
  - Malformed TOML (syntax errors).
  - Invalid field types.
  - Environment variable overrides.
- Document supported fields more clearly in README.
- **Replace this module with `mxm-config`:**
  - Delegate all configuration parsing/validation to `mxm-config`.
  - This avoids duplicate configuration logic across MXM packages.
  - Mark current module as deprecated once migration complete.


### Module: `src/mxm/refdata/utils/regex_patterns.py`
- **Test file**: `tests/unittests/utils/test_regex_patterns.py`

#### Observed behaviour (from tests)
- Provides precompiled regex patterns used across the package:
  - `YEAR_PATTERN` → matches 4-digit years (e.g., `"2025"`).
  - `MONTH_PATTERN` → matches month abbreviations (e.g., `"Jan"`, `"Dec"`).
  - `PERIOD_ID_PATTERN` → matches compound IDs like `"2025-Q1"`, `"2025M06"`.
  - `CONTRACT_ID_PATTERN` → matches contract IDs like `"ESZ5"` (product + month + year).
- Tests confirm:
  - Valid strings are matched.
  - Invalid strings are rejected (do not match).
  - Edge cases (e.g., lower/upper case) behave as expected.

#### Implementation
- Centralises regex definitions for consistency across parsing modules.
- Patterns are compiled at import for performance.
- Intended to be imported and reused by factories, parsers, and ORMs to enforce consistent ID formats.

#### Not covered by tests
- Boundary cases:
  - Year range validity (e.g., `"9999"`, `"0000"`).
  - Invalid but regex-matching cases (e.g., `"2025-Q5"` — valid regex, invalid quarter).
- Case sensitivity of month matching (`"jun"` vs `"Jun"`).
- Contract codes with unusual product identifiers (multi-character, numeric).
- Integration with actual object creation (factories/parsers assume regex success but don’t revalidate).

#### TODOs
- Add tests for:
  - Edge values (`"0000"`, `"9999"`).
  - Invalid but regex-passing quarter/month codes.
  - Lowercase month abbreviations.
- Consider stricter regexes or post-validation to catch semantically invalid matches.
- Improve docstrings to show example usage in product/contract parsing.

