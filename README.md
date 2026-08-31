# mxm-refdata

![Version](https://img.shields.io/github/v/release/moneyexmachina/mxm-refdata)
![License](https://img.shields.io/github/license/moneyexmachina/mxm-refdata)
![Python](https://img.shields.io/badge/python-3.13+-blue)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)

Reference-data generation, materialisation, and read access for the Money Ex Machina (MXM) ecosystem.

`mxm-refdata` defines deterministic futures products, contracts, periods, lifecycle dates, and trading-calendar relationships. It materialises the resulting operational reference state into PostgreSQL and exposes it through typed application and read-only interfaces.

It is intended to answer questions such as:

```text
What futures products exist?

What contracts exist for a product?

When does a contract become active?

When is its last trading day?

Which contracts are active on a given date?

Which source specification produced this operational state?
```

without depending on any market-data vendor.

For the full architectural specification, see [`docs/design.md`](docs/design.md).

## Purpose

Reference data describes the identity and lifecycle of financial instruments.

For example:

```text
cme_eurusd_futures.Mar-2032
```

is deterministically derived from:

- a futures-product specification;
- period definitions;
- valid contract months;
- trading-calendar semantics;
- first-day-of-interest rules;
- last-trading-day rules.

Observed prices, quotes, trades, settlements, and vendor histories are separate concerns and belong in packages such as `mxm-marketdata`.

## Architecture

The principal reference-data path is:

```text
mxm-refdata-source
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

Runtime construction is explicit:

```text
RuntimeIdentity
        ↓
RuntimeContext
        ↓
composition
        ↓
RefData
```

### Authoritative source

Curated futures-product specifications live in the Git-controlled `mxm-refdata-source` repository.

PostgreSQL stores the operational materialised state together with provenance such as source identity, digest, metadata, and source-repository revision.

The canonical source specification remains in `mxm-refdata-source`; it is not duplicated as a second canonical copy inside PostgreSQL.

### Generation

Period and futures-contract generation is deterministic and stateless where practical.

Contract identity follows:

```text
{product_id}.{period_id}
```

for example:

```text
cbot_10_year_us_treasury_note_futures.Dec-2046
```

### Application capabilities

`RefData` is the complete composed application capability. It exposes:

```text
build()
rebuild()
diagnostics()
reader
```

`RefDataReader` is the restricted read-only capability intended for downstream consumers.

### Persistence

Operational structured reference data is stored in PostgreSQL using:

```text
Psycopg 3
+ explicit SQL
+ version-controlled SQL migrations
```

`mxm-refdata` owns the PostgreSQL schema:

```text
refdata
```

There is no SQLAlchemy ORM or SQLite persistence path in the accepted runtime architecture.

## Materialisation lifecycle

Reference data is deterministic derived state.

### Build

```text
construct desired state
→ migrate if required
→ persist non-destructively
```

Equivalent repeated builds are idempotent and do not create duplicate authoritative state.

### Rebuild

```text
construct desired state
→ validate owned schema
→ drop owned schema
→ apply migrations
→ rematerialise
```

`rebuild` is intentionally destructive only within the owned reference-data schema.

Desired state is constructed before destructive reset.

## CLI

The CLI operates through the resolved MXM runtime context. Database credentials, source roots, and operational configuration are not passed as ad hoc command-line overrides.

Check prerequisites:

```bash
mxm-refdata preflight
```

Materialise reference data non-destructively:

```bash
mxm-refdata build
```

Recreate the owned reference-data schema from deterministic source state:

```bash
mxm-refdata rebuild
```

Run operational readiness checks:

```bash
mxm-refdata smokecheck
```

Inspect the materialised universe:

```bash
mxm-refdata products
mxm-refdata product cme_eurusd_futures
mxm-refdata contracts cme_eurusd_futures
mxm-refdata coverage
```

Inspect active contracts using the supported `active` command:

```bash
mxm-refdata active --help
```

## Python usage

Applications should obtain reference data through the normal MXM composition boundary.

Conceptually:

```text
from mxm.refdata import RefData, build_refdata

refdata: RefData = build_refdata(ctx)
```

Downstream code that needs read access only should depend on:

```text
RefDataReader
```

rather than constructing database or configuration dependencies independently.

The detailed application and composition boundaries are documented in [`docs/design.md`](docs/design.md).

## Runtime configuration

Runtime configuration is resolved through the MXM runtime and configuration systems.

The composition root resolves:

- the `mxm_refdata` configuration view;
- the authoritative futures-product source root;
- the configured contract horizon;
- the `operational_state` PostgreSQL target;
- database credentials through the runtime secrets capability.

Lower application layers receive concrete resolved dependencies and do not resolve runtime secrets or deployment configuration themselves.

## Current V1 operational scope

The current configured V1 deployment covers futures on:

```text
CBOT
CME
COMEX
NYMEX
```

The accepted V1 materialisation currently contains:

```text
products:          86
product_sources:   86
periods:           799
contracts:      31,490
cycles:              2
memberships:        752
```

The configured contract horizon is:

```text
2000–2046 inclusive
```

These counts describe the currently accepted MXM V1 deployment rather than universal package constants.

## Development

Install dependencies:

```bash
poetry install
```

Run the standard validation suite:

```bash
make check
```

This runs the tests that require neither PostgreSQL nor the private product-source repository.

### PostgreSQL integration

On `monolith`:

```bash
poetry run pytest -q -m postgres
```

These tests use real PostgreSQL, disposable schemas, and synthetic public fixtures.

They verify:

- migrations;
- schema constraints;
- SQL adapters;
- materialisation;
- Reader behaviour;
- diagnostics;
- lifecycle semantics.

### Private deployment acceptance

On `monolith`:

```bash
poetry run pytest -q -m acceptance
```

This uses the real MXM runtime, configuration, secrets, private `mxm-refdata-source`, and PostgreSQL target while materialising into a disposable acceptance schema.

It verifies the complete configured V1 universe independently from the operational `refdata` schema.

Repository compliance:

```bash
mxm-foundry check .
```

## Package boundaries

`mxm-refdata` owns:

- reference-data domain models;
- futures-product source interpretation;
- deterministic period and contract generation;
- trading-calendar lifecycle calculations;
- PostgreSQL reference-data persistence;
- materialisation lifecycle;
- read semantics;
- readiness diagnostics;
- runtime composition;
- the reference-data CLI.

It does not own:

- market data;
- broker or exchange acquisition clients;
- portfolio construction;
- signals;
- risk;
- execution;
- workflow orchestration;
- the broader MXM operation-level provenance system.

See [`docs/design.md`](docs/design.md) for the detailed boundary definitions and design principles.

## Documentation

- [`docs/design.md`](docs/design.md) — current architecture and design principles
- [`CHANGELOG.md`](CHANGELOG.md) — repository changes by release / unreleased state

## License

MIT License. See `LICENSE`.

