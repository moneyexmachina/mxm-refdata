# Design Document: `mxm-refdata`

## Purpose

`mxm-refdata` provides the **canonical system of record for reference data** in the Money Machine ecosystem.  
It defines the identity, structure, and lifecycle of financial instruments (currently focused on futures) and offers deterministic, rule-driven generation of products, contracts, and periods.  

The package ensures that instrument definitions can be:
- Generated from canonical rules and configuration.
- Persisted to and queried from a database.
- Reproduced deterministically across environments.
- Integrated with trading calendars and expiry conventions.

## Ambition

The ambition of `mxm-refdata` is to be the **definitive reference data layer** for the Money Machine:

- **Canonical**: A single source of truth for product and contract definitions.  
- **Composable**: Clear separation between domain models, persistence, factories, and services.  
- **Extensible**: Initially designed for futures, but with a structure that accommodates other asset classes (ETFs, equities, FX).  
- **Deterministic**: Reference data can be recreated from configuration and rules without ambiguity.  
- **Auditable**: The lifecycle of every contract and product is explicitly defined and reproducible.  

## Feature Requirements

### Core Requirements

1. **Ontology Definition**  
   - Domain classes: `FuturesProduct`, `FuturesContract`, `ETF`, `Period`, `Currency`, `Unit`, etc.  
   - Enums and rules for settlement methods, expiry events, trading calendars.  
   - Stable internal identifiers (MXM IDs) independent of external providers.

2. **Instance Generation**  
   - Deterministic construction from CSV/JSON configs and rule logic.  
   - Generation of contracts from product rules and periods.  
   - Bootstrapping periods (years, quarters, months, weeks).

3. **External Data Ingestion**  
   - Define schemas for expected provider replies.  
   - Map replies into domain instances.  
   - Persist raw replies for audit and replay.  
   - Reconcile differences between new replies and existing state.

4. **Catalogue Management**  
   - Maintain an authoritative set of domain instances.  
   - Provide idempotent updates (same input = same state).  
   - Support queries like:  
     - “All contracts for product X.”  
     - “Expiry rule for product Y.”  
     - “MXM ID for external ticker Z.”

5. **Mapping Layer**  
   - Bidirectional mapping: external IDs ↔ MXM IDs.  
   - Example: MXM contract `Corn.Dec2025` ↔ CME `ZC Z5` ↔ Bloomberg `COZ25` ↔ IB ID.

6. **Downstream Access**  
   - Internal API for queries, expiry lookups, calendars.  
   - Downstream systems only use MXM IDs, never raw external codes.

### Non-Requirements

- **External connectors / API clients**  
  - IBKR API, CME scrapers, or justETF connectors belong outside `mxm-refdata`.  
  - This package only defines schemas and mappings.

- **Market data**  
  - Prices, quotes, and live feeds belong in `mxm-marketdata`, not `mxm-refdata`.

- **Trading logic**  
  - Execution, risk, and portfolio logic are downstream consumers.

- **Heavy persistence infra (optional)**  
  - SQLAlchemy ORM is available but may evolve toward event-sourced raw reply logs + snapshots rather than full relational persistence.

## Vision (Versioned Roadmap)

### v0 (current)
- Futures-only scope.  
- Domain models: products, contracts, periods, currencies, units, months, weekdays.  
- Persistence layer: SQLAlchemy ORM for products, contracts, and periods.  
- Mapping utilities: bidirectional conversion between domain models and ORM.  
- Factories:  
  - `PeriodFactory` – generates canonical periods.  
  - `FuturesProductFactory` – creates and caches products from CSV.  
  - `FuturesContractFactory` – generates contracts from product + period rules.  
- Services:  
  - `RefDataService` – orchestrates initialising and resetting DB contents.  
- Trading calendars: expiry rules, first-day-of-interest rules, nth-day calculations.  
- Parsing: CSV loader for futures products.  
- Utilities: cache manager, regex patterns, local config loader.

### v1 (near-term)
- **ETF ontology**:  
  - Define types for `ETFIndex`, `ETFFamily`, `ETF`.  
  - Capture attributes such as inception date, total expense ratio (TER), domicile, replication method.  
  - Support versioning of attributes (e.g. TER updates over time).  
- **ETF instance creation**:  
  - Load ETF definitions from CSV/YAML.  
  - Populate ORM-backed instances for persistence and query.  
  - Provide services to query ETFs by family, index, or attributes.  
- **Integration with futures ontology**:  
  - Maintain a unified catalogue covering both futures and ETFs.  
- **General improvements**:  
  - Replace `utils/config` with `mxm-config`.  
  - Expand test coverage to error paths, cache behaviour, ORM integrity.  
  - Clean naming conventions for ORM modules and enums.  
  - Document CSV and YAML schemas.  
  - Introduce validation (possibly Pydantic).  

### v2 (longer-term)
- Extend scope to other asset classes (cash equities, FX spot).  
- Support dynamic, config-driven generation from multiple provider sources.  
- Reconcile across vendor feeds and internal definitions.  
- Provide streaming/event-driven refdata updates.  
- Introduce higher-level APIs for cross-asset queries and analytics.  

## Current State of Implementation

- **Well-developed and tested**:  
  - Period models/factory.  
  - Futures product parsing.  
  - Trading calendar rules.  
  - Contract and product factories.  
  - Cache manager and regex utils.

- **Implemented but under-tested**:  
  - FuturesContract model.  
  - ORM mappings and persistence.  
  - FuturesProductFactory cache.  
  - RefDataService orchestration.  

- **Implemented but incomplete**:  
  - Config (to be replaced by `mxm-config`).  
  - Currencies, units, reference events (minimal coverage).  

## Design Principles

- **Domain / ORM separation**: domain models are frozen dataclasses; ORM classes are SQLAlchemy entities with conversion utilities.  
- **Singleton factories**: ensure uniqueness and reuse of products, contracts, and periods.  
- **Rule-driven lifecycle**: expiry/first-day-of-interest defined in JSON, products in CSV, config in TOML.  
- **Immutability**: domain models are frozen to ensure deterministic identity.  
- **Caching**: applied across factories and APIs; future cache invalidation strategy needed.  
- **Test-driven expansion**: implementation grows alongside an expanding test suite.

## Package Boundaries

### Inside `mxm-refdata`
- Ontology (types, enums, rules).  
- Deterministic construction from config and rules.  
- Language services: queries, calendars, lookups.  
- Mapping layer: external schema ↔ MXM domain.  

### Outside `mxm-refdata` (future `mxm-refdata-app` or service)
- Polling brokers, exchanges, and ETF providers.  
- Scraping, API requests, or subscriptions.  
- Recording raw replies and change detection.  
- Reconciling differences between providers.  
- Persisting raw logs and snapshots for audit.  
- Running as a service (daemon/API) to expose refdata externally.  

### Rationale
- Clean separation preserves testability and reusability.  
- Service-level concerns (scheduling, persistence, monitoring) don’t bloat the package.  
- Ontology evolves in the package; data collection evolves in the app.

## Next Steps

1. **Configuration** – migrate to `mxm-config`.  
2. **Coverage** – expand tests for contracts, ORMs, error paths.  
3. **Consistency** – standardise naming and enums.  
4. **Validation** – introduce schema validation for CSV/JSON.  
5. **Boundaries** – spin up `mxm-refdata-app` to handle data collection, reconciliation, and persistence.  
6. **Documentation** – publish schemas, usage examples, and integration notes.

