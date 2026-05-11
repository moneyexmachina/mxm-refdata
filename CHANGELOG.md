# Changelog

All notable changes to this project will be documented in this file.

The format is based on **Keep a Changelog**, and this project adheres to **Semantic Versioning**.

## Unreleased

### Added
- (none)

### Changed
- (none)

### Fixed
- (none)

---

## [0.3.0] - 2026-05-11

### Added

- Operational CLI interface via `mxm-refdata`.
- `build`, `rebuild`, `products`, `product`, `contracts`,
  `active`, `coverage`, and `smokecheck` CLI commands.
- `build_refdata()` and `rebuild_refdata()` bootstrap services.
- Dedicated operational smokecheck service.
- Smokecheck test suite.
- Public README documentation covering:
  - ontology boundaries,
  - constructive reference semantics,
  - CLI usage,
  - Python API usage,
  - operating modes,
  - and architecture overview.
- Explicit package development workflow documentation.
- `mxm-foundry` compliance.

### Changed

- Refactored smokecheck logic from standalone operational script
  into typed reusable service infrastructure.
- Refactored `last_trading_day` lifecycle logic into smaller typed helpers.
- Improved typing consistency across:
  - tests,
  - lifecycle logic,
  - cache management,
  - bootstrap services,
  - and CLI surfaces.
- Standardised package quality gates around `make check`.

### Fixed

- Large-scale pyright compliance issues across tests and services.
- Multiple circular import problems within model exports.
- Typing inconsistencies in lifecycle and calendar logic.
- CLI runtime issues related to unsupported `datetime.date`
  handling in Typer.
- Optional-member-access and partially-unknown typing issues
  across operational services.

### Tests

- Expanded pyright-compliant test coverage across:
  - bootstrap services,
  - smokecheck services,
  - lifecycle logic,
  - API semantics,
  - and operational database behaviour.

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

Notable changes for earlier versions have not yet been backfilled.
A future maintenance task may reconstruct earlier entries from git history and tags.
