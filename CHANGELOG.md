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
## v0.4.1 — 2026-07-01

### Added
- Full support for sourcing futures product definitions from the dedicated `mxm-refdata-source` repository (JSON-based), replacing the previous CSV canonical source.
- Recursive JSON parsing for multiple product files, including provenance and parsed rules.
- `FuturesProductFactory` updated to initialise from JSON by default.
- Equivalence tests added to validate consistency between legacy CSV snapshots and JSON ingestion.
- CLI and Python API updated to operate on JSON-sourced reference data.

### Changed
- `RefDataConfigData` now uses `REFDATA_FUTURES_PRODUCTS_JSON_ROOT` instead of CSV path.
- Deprecated CSV ingestion path in production; CSV retained only for demos and testing.
- Refactored factory, service, and API layers to remove implicit CSV defaults.
- Updated all tests and fixtures to reflect JSON-based configuration.

### Fixed
- Resolved runtime path resolution issues by ensuring JSON root is correctly derived from config and `RuntimeContext`.
- Eliminated inconsistent object graph construction across CLI, API, and services.

## [0.4.0] - 2026-06-23

### Added

- `RefDataConfigInput` and `RefDataConfigData` configuration models.
- `normalise_refdata_config_data(...)` to materialise complete refdata configuration from partial inputs.
- `RefDataAPI.from_config_data(...)` as the primary API construction boundary.
- `RefDataService.from_config_data(...)` for configured service construction.
- `FuturesProductFactory.from_config_data(...)`.
- Trading-calendar coverage validation during futures-contract materialisation.
- Explicit CLI configuration via:
  - `--db-url`
  - `--contract-start-date`
  - `--contract-end-date`

### Changed

- Refactored the package from implicit configuration discovery to explicit dependency construction.
- `RefDataAPI` now requires fully resolved configuration and no longer discovers configuration internally.
- `SQLSessionManager` now uses explicit construction through:
  - `SQLSessionManager(...)`
  - `SQLSessionManager.from_db_url(...)`
- Refactored bootstrap services to be fully driven by `RefDataConfigData`.
- Removed bootstrap-time override parameters in favour of a single authoritative configuration object.
- Separated:
  - contract materialisation horizon
  - trading-calendar source coverage
- Renamed:
  - `REFDATA_CALENDAR_START_DATE` → `REFDATA_CONTRACT_START_DATE`
  - `REFDATA_CALENDAR_END_DATE` → `REFDATA_CONTRACT_END_DATE`
- Refactored `FuturesProductFactory` from singleton-style behaviour to explicit instance-based construction.
- Refactored `FuturesContractFactory` from singleton-style behaviour to explicit instance-based construction.
- Moved package configuration from utility-layer status to a first-class package concern.
- Updated operational CLI commands to construct services explicitly from configuration rather than relying on hidden defaults.
- Updated README and architecture documentation to reflect runtime-oriented construction patterns.

### Fixed

- Removed remaining hidden configuration-loading pathways from refdata service construction.
- Removed implicit database/session-manager construction throughout operational workflows.
- Improved consistency between CLI, API, bootstrap, and service construction paths.
- Corrected trading-calendar boundary handling and introduced explicit coverage validation.
- Eliminated a number of pyright and typing issues exposed by the runtime-integration refactor.

### Tests

- Reworked API tests around explicit configuration-driven construction.
- Added configuration normalisation test coverage.
- Added factory-construction test coverage.
- Added CLI boundary and wiring tests.
- Added trading-calendar coverage validation tests.
- Expanded service-level tests to cover the new runtime-driven construction model.

### Notes

This release completes the Session 48c runtime-integration work.

`mxm-refdata` is now a configuration-driven library designed to be constructed from resolved runtime configuration rather than discovering configuration internally. This aligns the package with the broader MXM architecture based on explicit dependency construction, `RuntimeContext`, and configuration injection.

Future work will focus on:
- externalising product specifications into a dedicated `mxm-refdata-source` repository,
- downstream integration with `mxm-runtime`,
- and PostgreSQL-backed operational deployments.
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
