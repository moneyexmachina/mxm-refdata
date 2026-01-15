# Changelog

All notable changes to this project will be documented in this file.

The format is based on **Keep a Changelog**, and this project adheres to **Semantic Versioning**.

## [Unreleased]

### Added
- (placeholder)

### Changed
- (placeholder)

### Fixed
- (placeholder)

---

## [0.2.0] - 2026-01-15

### Added
- `RefDataAPI.get_active_contracts(as_of_date, *, product_id=None, product_ids=None)` to query lifecycle-active futures contracts using the internal semantics:
  `first_day_of_interest <= as_of_date <= last_trading_day`.
- `RefDataAPI.get_contract_by_id(contract_id)` for single-contract lookup.
- `RefDataAPI.get_contracts_by_id(contract_ids)` for batch contract lookup with input-order preservation.

### Changed
- `RefDataAPI.get_contracts_for_product(product_id)` now returns contracts in a deterministic order based on the associated `Period` ordering semantics (period type priority, then `first_date`), with a stable tie-break on `contract_id`.

### Fixed
- (none)

### Tests
- Added unit tests covering:
  - `get_active_contracts` semantics, scoping, and caching behaviour.
  - Deterministic ordering for `get_contracts_for_product`.
  - `get_contract_by_id` and `get_contracts_by_id` correctness and caching.

---

## Pre-changelog history

Versions prior to `0.2.0` were developed before this changelog was introduced.
Notable changes for earlier versions have not yet been backfilled. A future maintenance
task may reconstruct earlier entries from git history and tags.
