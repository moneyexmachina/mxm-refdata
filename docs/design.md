# Design: `mxm-refdata`

## Purpose

`mxm-refdata` is the Money Ex Machina reference-data application.

It defines the internal identity, structure, and lifecycle of financial
reference objects and deterministically constructs the reference state required
by downstream MXM systems.

The current operational scope is futures.

The package answers questions such as:

```text
What futures products exist?

What contracts exist for a product?

What period does a contract represent?

When does a contract become active?

When is its last trading day?

Which contracts are active on a given date?

How are calendar months and quarters represented?

Which authoritative product specification produced this operational state?
```

Reference data is independent of observed market data.

Prices, quotes, trades, settlement observations, and vendor market-data
histories belong outside `mxm-refdata`.

# 1. System Responsibilities

`mxm-refdata` owns four related responsibilities:

```text
domain semantics
    +
deterministic generation
    +
operational materialisation
    +
read-only reference-data access
```

More concretely, it owns:

- MXM reference-data domain identities;
- futures-product definitions as operational domain values;
- periods and canonical period cycles;
- deterministic futures-contract generation;
- trading-calendar and lifecycle-date calculations;
- PostgreSQL materialisation of derived reference-data state;
- provenance linking operational products to their configured source;
- reference-data reads for downstream MXM applications;
- readiness diagnostics for the operational reference-data state.

It does not own market-data observations, execution state, portfolios, trading
logic, or external data acquisition.

# 2. Authoritative State Boundaries

There is deliberately not one database that is canonical for every kind of
reference-data information.

The architecture distinguishes between:

```text
authoritative curated source
        ↓
deterministic application logic
        ↓
operational materialised state
```

## 2.1 Curated product specifications

The authoritative curated futures-product specifications live in the
Git-controlled `mxm-refdata-source` repository.

Each product is defined by one JSON source record containing:

- product identity;
- operational product attributes;
- lifecycle rules;
- trading-calendar identity;
- valid contract periods;
- structured generation rules;
- provenance metadata.

The configured source root is supplied through the MXM runtime configuration.

`mxm-refdata` does not maintain a second embedded copy of the production source
universe.

## 2.2 Operational reference-data state

PostgreSQL is authoritative for the currently materialised operational
reference-data state.

That state is derived from:

```text
configured source revision
+ configured contract horizon
+ mxm-refdata generation semantics
+ schema migration version
```

The PostgreSQL state is therefore reproducible derived state rather than the
authoritative location of the curated product specifications.

## 2.3 Source provenance

Operational product state retains enough provenance to identify the source from
which it was produced.

Persisted provenance includes, as applicable:

- source-relative specification path;
- source content digest;
- source metadata;
- source repository revision.

The complete canonical source JSON is not duplicated into PostgreSQL.

The authoritative specification remains in `mxm-refdata-source`; PostgreSQL
stores the operational domain state and the identity required to trace it back
to that source.

# 3. Domain Model

The core domain consists of immutable reference-data values.

Important domain concepts include:

```text
FuturesProduct
FuturesContract
Period
PeriodType
PeriodCycle
PeriodCycleMembership
Currency
Unit
Month
Weekday
ReferenceEvent
```

The domain model is independent of PostgreSQL records and SQL representation.

Database adapters translate between PostgreSQL rows and domain values; database
objects are not domain objects.

## 3.1 Stable identity

MXM identities are internal identities and do not depend on a particular
external market-data provider.

A futures contract has the canonical identity:

```text
{product_id}.{period_id}
```

For example:

```text
cme_eurusd_futures.Mar-2032
```

The identity follows from the MXM product and period identities rather than
from an exchange ticker, Bloomberg identifier, or broker symbol.

External-provider identifiers may later be associated with MXM identities, but
they do not define them.

## 3.2 Immutable domain values

Reference-data domain values are represented as immutable values wherever
practical.

This supports:

- deterministic equality;
- safe reuse;
- explicit replacement rather than hidden mutation;
- stable identity semantics;
- straightforward unit testing.

Mutable operational concerns belong at application and persistence boundaries,
not inside identity-bearing domain objects.

# 4. Product Source Boundary

Product specifications enter `mxm-refdata` through an explicit source adapter.

Conceptually:

```text
configured JSON root
        ↓
source adapter
        ↓
FuturesProductSourceRecord
    ├── FuturesProduct
    └── source metadata
```

Repository revision is resolved independently from the Git-controlled source
root.

The source adapter is responsible for:

- reading source records;
- validating their structure;
- converting source representation into domain values;
- computing source content identity;
- preserving source-relative identity and provenance.

It is not responsible for:

- database writes;
- contract generation;
- runtime secret resolution;
- application composition.

# 5. Deterministic Generation

Reference-data instances are generated from domain rules rather than maintained
as manually enumerated contract catalogues.

Generation is stateless wherever practical.

The principal flow is:

```text
configured date horizon
        ↓
period generation
        ↓
product specification
        +
periods
        ↓
futures-contract generation
        ↓
lifecycle dates
```

There is no requirement for singleton factories or globally mutable object
registries to establish identity.

Identity follows from deterministic domain construction.

## 5.1 Period generation

The configured contract horizon produces the required canonical periods,
including:

- years;
- quarters;
- months.

Periods have stable IDs and explicit period types.

Canonical period cycles define reusable structural relationships such as:

```text
CALENDAR_MONTHS
CALENDAR_QUARTERS
```

with explicit cycle memberships.

## 5.2 Futures-contract generation

Futures contracts are generated from:

```text
FuturesProduct
+ candidate Period
+ trading-calendar semantics
+ structured contract rules
```

Generation determines whether a candidate period is valid for the product.

For valid periods, generation derives:

- contract identity;
- period identity;
- first day of interest;
- last trading day;
- other lifecycle values represented by the domain.

Generation must be deterministic for the same accepted inputs.

# 6. Trading Calendars and Lifecycle Rules

Trading-calendar calculations are an explicit domain service.

They support rule structures such as:

- nth weekday of a period;
- nth business day;
- calendar-day offsets;
- business-day offsets;
- reference events;
- first-day-of-interest rules;
- last-trading-day rules.

Calendar coverage is validated explicitly before lifecycle calculations are
accepted.

Trading-calendar semantics are part of reference-data construction.

Observed exchange events or historical market-data corrections remain separate
concerns.

# 7. Application Architecture

The application is assembled through one composition boundary.

The accepted runtime path is:

```text
RuntimeIdentity
        ↓
RuntimeContext
        ↓
mxm.refdata.composition.build_refdata(ctx)
        ↓
RefData
```

Runtime configuration and secrets are resolved only at this boundary.

Lower layers receive concrete dependencies rather than the complete
`RuntimeContext`.

This prevents source loading, generation, persistence, and read services from
independently resolving configuration or secrets.

# 8. `RefData` Application Capability

`RefData` is the complete composed reference-data application capability.

It contains:

```text
config
database
reader
```

and exposes the application operations:

```text
build()
rebuild()
diagnostics()
```

`RefData` is intentionally a thin façade.

The implementation of each capability remains in its dedicated module rather
than accumulating inside the façade.

# 9. `RefDataReader` Read Capability

`RefDataReader` is the restricted read-only reference-data capability intended
for downstream MXM applications.

A downstream application that only needs reference data should normally receive:

```text
RefDataReader
```

rather than the complete `RefData` application.

The Reader owns application-facing read semantics such as:

- required versus optional lookup behaviour;
- preservation of requested ID order;
- domain ordering;
- active-contract selection;
- cycle-element projection.

The SQL layer owns relational filtering and persistence representation.

This keeps database representation and downstream domain semantics separate.

# 10. PostgreSQL Persistence

Operational structured reference data is persisted in PostgreSQL.

The accepted persistence implementation uses:

```text
Psycopg 3
+ explicit SQL
+ version-controlled SQL migrations
```

There is no ORM in the accepted persistence path.

SQLite is not an alternative operational or development persistence
implementation.

## 10.1 Database boundary

`PostgresDatabase` is the explicit PostgreSQL infrastructure boundary.

It owns only infrastructure responsibilities:

```text
connection parameters
connection construction
transaction context
commit
rollback
connection close
schema identity
```

SQL adapters receive a connection from this boundary.

Individual persistence adapters do not independently commit transactions.

Application capabilities therefore control transaction scope explicitly.

## 10.2 Owned namespace

`mxm-refdata` owns an explicit PostgreSQL schema:

```text
refdata
```

Application SQL is schema-qualified and must not depend accidentally on
PostgreSQL's ambient search path or `public` namespace.

The operational database may contain state owned by other MXM applications.

Destructive reference-data operations must therefore be bounded to the
configured owned schema.

# 11. Schema

The current PostgreSQL schema contains the application tables:

```text
schema_migrations
periods
period_cycles
period_cycle_memberships
futures_products
futures_product_sources
futures_contracts
```

Relational representation is used where it provides operational value:

- stable identities;
- filtering;
- joins;
- referential integrity;
- uniqueness;
- lifecycle queries.

Structured nested rules may use PostgreSQL JSONB when full relational
normalisation would add complexity without improving operational semantics.

The schema should represent the domain that exists, not speculative consumers
or future asset classes.

# 12. Schema Migrations

Schema evolution is explicit and version controlled.

Migration SQL lives with the package and is applied by `MigrationRunner`.

The migration system provides:

- ordered migration discovery;
- migration identity;
- checksums;
- migration application;
- migration ledger state;
- current/pending inspection;
- safe repeat invocation.

Migration state is part of operational readiness.

No undocumented manual SQL should be required to create an accepted
`mxm-refdata` schema.

# 13. Desired-State Materialisation

Materialisation is based on explicit desired-state construction.

The high-level process is:

```text
config
+ product source
+ source revision
        ↓
construct complete desired state
        ↓
migrate schema if required
        ↓
persist complete desired state
```

Desired state includes:

```text
periods
period cycles
cycle memberships
products
product provenance
futures contracts
```

The desired state is constructed before database mutation where possible.

This separates deterministic construction failures from persistence failures and
is particularly important for destructive rebuild semantics.

# 14. Persistence Transaction

Complete materialisation is persisted in one application transaction.

The persistence order is explicit:

```text
periods
→ period cycles
→ cycle memberships
→ futures products
→ futures-product provenance
→ futures contracts
```

The transaction commits only after the complete persistence operation succeeds.

A later persistence failure rolls back earlier mutations from the same
materialisation attempt.

Persistence adapters do not hide per-row commits.

# 15. Build Semantics

`build` is the normal non-destructive materialisation operation.

Conceptually:

```text
construct desired state
→ migrate if required
→ persist desired state
```

Equivalent repeated input must produce equivalent accepted state.

A repeated build must not create duplicate:

- products;
- product-source records;
- periods;
- contracts;
- cycles;
- memberships.

Mutable provenance may be updated when the stable product identity and
authoritative operational product state remain compatible.

Conflicting immutable reference-data state fails explicitly rather than being
silently overwritten.

# 16. Rebuild Semantics

`rebuild` is an explicitly destructive operation within the owned reference-data
schema.

Conceptually:

```text
construct desired state
        ↓
validate destructive target
        ↓
drop owned schema
        ↓
bootstrap
        ↓
apply migrations
        ↓
persist desired state
```

The desired state is constructed before the existing schema is dropped.

The destructive target is validated and bounded.

`rebuild` must not:

- drop the database;
- modify unrelated schemas;
- depend on unqualified destructive SQL.

Its purpose is reproducible replacement of deterministic derived state.

# 17. Diagnostics and Readiness

Reference-data readiness is inspected through application diagnostics.

Diagnostics combine:

```text
migration inspection
+ relational row counts
+ RefDataReader semantic checks
```

Current readiness includes checks for:

- schema initialisation;
- migration currency;
- populated core reference data;
- complete product provenance;
- populated period cycles;
- valid `CALENDAR_MONTHS`;
- valid `CALENDAR_QUARTERS`.

Diagnostics are read-only.

Operational CLI rendering is provided through:

```text
mxm-refdata smokecheck
```

# 18. Preflight

`mxm-refdata preflight` validates prerequisites before operational mutation.

Preflight covers the resolved runtime environment, including:

- runtime identity;
- product-source availability;
- configured filesystem roots;
- application composition;
- PostgreSQL selection;
- PostgreSQL connectivity.

Preflight does not materialise reference data.

Its purpose is to distinguish environmental/configuration failure from
application materialisation failure.

# 19. Runtime Configuration

Application runtime configuration is supplied through the MXM runtime and
configuration systems.

The composition root obtains the resolved `mxm_refdata` configuration view and
the configured operational database dependency.

Database credentials are resolved through the runtime secrets capability at the
composition boundary.

Lower application layers do not receive:

- unresolved secret references;
- secret APIs;
- raw deployment configuration trees;
- `RuntimeContext`.

This preserves an explicit dependency boundary between deployment concerns and
application logic.

# 20. Testing Boundaries

Tests are organised according to the architectural boundary they prove.

## Unit and standard application tests

These test:

- domain semantics;
- source conversion;
- generation;
- SQL construction/decoding;
- Reader semantics;
- migration logic;
- materialisation orchestration;
- diagnostics policy;
- composition;
- preflight;
- CLI behaviour.

They do not require PostgreSQL or the private production source repository.

## PostgreSQL integration

PostgreSQL integration tests use:

- real PostgreSQL;
- disposable generated schemas;
- synthetic public source fixtures;
- production SQL/source/application paths.

They prove two distinct boundaries:

```text
SQL adapter
↔ PostgreSQL schema
```

and:

```text
application capability
↔ real PostgreSQL infrastructure
```

The integration suite must not depend on the private production product
universe.

## Deployment acceptance

The private MXM acceptance lane uses:

```text
real RuntimeContext
+ real MXM configuration
+ real secrets
+ real mxm-refdata-source
+ real PostgreSQL target
+ disposable acceptance schema
```

Its purpose is different from generic integration testing.

It establishes that the actual configured MXM deployment can materialise and
read the complete accepted reference-data universe.

# 21. Package Boundaries

## Inside `mxm-refdata`

`mxm-refdata` owns:

- reference-data domain models;
- source-schema interpretation;
- deterministic period generation;
- deterministic futures-contract generation;
- trading-calendar lifecycle calculations;
- PostgreSQL reference-data schema;
- plain-SQL persistence;
- materialisation lifecycle;
- Reader semantics;
- readiness diagnostics;
- runtime composition;
- CLI operations for the reference-data application.

## Outside `mxm-refdata`

The following concerns belong elsewhere:

### Market data

- prices;
- quotes;
- trades;
- settlements;
- market-data histories;
- vendor observations.

These belong in `mxm-marketdata` or equivalent downstream data systems.

### External acquisition

- broker APIs;
- exchange scrapers;
- third-party downloads;
- subscription clients;
- raw-provider reply acquisition.

The reference-data package may consume curated source definitions but does not
own the acquisition process that produced them.

### Trading and portfolios

- signal generation;
- portfolio construction;
- risk;
- order generation;
- execution;
- P&L.

These consume reference data but are not reference-data responsibilities.

### Workflow orchestration

Prefect or another scheduler may invoke `mxm-refdata` operations.

Orchestration must consume an already functioning application capability rather
than becoming part of the reference-data domain or persistence implementation.

### Operation-level provenance

The broader MXM semantic attempt system will own operation-level linkage across:

```text
code revision
configuration revision
source-data revision
runtime identity
operation arguments
outputs
acceptance state
```

`mxm-refdata` owns only the source and persistence provenance necessary to
explain its reference-data state.

# 22. Design Principles

## One composition root

Application dependencies are assembled once through the accepted runtime
composition boundary.

Entry points do not independently reconstruct configuration, secrets,
databases, or source dependencies.

## Explicit dependencies

Lower layers receive the dependencies they need directly.

Hidden global infrastructure state should be avoided.

## Deterministic generation

The same accepted source, rules, configuration, and date horizon should produce
the same reference-data identities and lifecycle state.

## Immutable domain semantics

Identity-bearing domain values should be immutable where practical.

Operational mutation belongs at persistence/application boundaries.

## Stateless generation over factories

Generation should normally be expressed as pure or stateless functions.

Factories, registries, and caches should exist only where they solve a concrete
problem rather than as the mechanism establishing domain identity.

## Plain SQL over persistence magic

Reference-data persistence is deliberately explicit.

SQL, schema constraints, transaction scope, ordering, and conflict semantics
should remain inspectable.

## Application-owned transactions

Repository functions do not independently commit application state.

The application capability defines the atomic operation.

## Construct before destruct

A destructive rebuild should not destroy accepted state before replacement
desired state has been successfully constructed.

## Bounded destructive operations

`mxm-refdata` owns a schema, not the whole PostgreSQL database.

Destructive operations must be explicitly limited to that ownership boundary.

## Source provenance without duplicate authority

Operational materialisation must be traceable to its source.

Traceability should not require maintaining competing canonical copies of the
same product specification.

## Tests follow architectural ownership

Each behaviour should be tested at the layer that owns it.

Unit tests prove local semantics.

PostgreSQL integration proves database behaviour.

Deployment acceptance proves the configured private MXM system.

Tests should not duplicate the same semantics merely because multiple layers
exist.

# 23. Current Scope

The accepted operational scope is futures reference data.

The architecture currently supports:

- futures products;
- futures contracts;
- periods;
- calendar-month and calendar-quarter cycles;
- lifecycle rules;
- trading calendars;
- PostgreSQL materialisation;
- provenance;
- application reads;
- operational diagnostics.

Other asset classes should be added only when there is a concrete MXM
requirement and should reuse the architectural principles here where those
principles remain appropriate.

The current design does not require speculative cross-asset abstractions.

# 24. Explicit Non-Goals

The current design does not attempt to provide:

- a general-purpose financial security master;
- a vendor symbology reconciliation platform;
- market-data ingestion;
- exchange scraping;
- broker integration;
- live reference-data streaming;
- trading or portfolio logic;
- a cross-MXM generic ORM or database framework;
- a public copy of the private curated futures universe;
- a second SQLite implementation;
- an alternative ORM persistence path.

A standalone public/demo source universe, if required, should use deliberate
synthetic data in the current accepted source format rather than preserving
legacy production-format fixtures.

# 25. Architectural Invariant

The principal reference-data path is:

```text
Git-controlled product specifications
        ↓
source adapter
        ↓
FuturesProduct + provenance
        ↓
deterministic generation
        ↓
desired reference-data state
        ↓
plain-SQL PostgreSQL materialisation
        ↓
RefDataReader
        ↓
downstream MXM applications
```

Runtime construction surrounds this path:

```text
RuntimeIdentity
        ↓
RuntimeContext
        ↓
composition
        ↓
RefData
```

This is the architecture to preserve until a concrete downstream or operational
requirement demonstrates that one of its boundaries is insufficient.
