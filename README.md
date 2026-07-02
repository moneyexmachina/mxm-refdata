# mxm-refdata

![Version](https://img.shields.io/github/v/release/moneyexmachina/mxm-refdata)
![License](https://img.shields.io/github/license/moneyexmachina/mxm-refdata)
![Python](https://img.shields.io/badge/python-3.13+-blue)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)

Reference-data ontology and contract-generation framework for the Money Ex Machina (MXM) ecosystem.

`mxm-refdata` provides deterministic definitions of futures products, futures contracts, periods, lifecycle dates, and trading-calendar relationships. It materialises these definitions into a queryable reference-data store and exposes them through a typed Python API.

The package is intended to answer questions such as:

```
What futures products exist?

What contracts should exist for a given product?

When does a contract become active?

When is the last trading day?

Which contract is active on a given date?
```

without depending on any market-data vendor.

## Purpose

`mxm-refdata` defines financial reference objects and the rules by which they are constructed.

For example:

```
cme_gbp_futures.Mar-2032
```

is not stored as a static object. Instead it is deterministically derived from:

- a product specification,
- listing rules,
- period definitions,
- period-cycle membership,
- trading-calendar semantics,
- and lifecycle rules.

This allows downstream systems to reason about contracts independently of any particular data vendor. Observed prices, quotes, trades, and exchange events belong to separate packages such as `mxm-marketdata`.

## Architecture

`mxm-refdata` consists of three conceptual layers.

### Product specifications

Human-authored definitions describing:

- products,
- contract sizes,
- listing rules,
- lifecycle rules,
- trading calendars,
- and valid period structures.

**Canonical source:** All specifications are now sourced from the dedicated **`mxm-refdata-source`** repository as JSON files, one per product, each containing full provenance metadata and parsed rules.

**Legacy CSV snapshots** are retained only for demonstration and testing purposes; they are not used in the production pipeline.

### Composition and object graph

The **composition layer** constructs the in-memory object graph representing the MXM reference data system:

- factories,
- registries,
- DB connections,
- caches,
- and query interfaces.

This object graph is encapsulated in the `RefData` class and is the canonical runtime representation of the system. The composition layer is implemented in `composition.py` (or similar) and receives a fully resolved `RuntimeContext` from `mxm-runtime`.

### Application entrypoints

Applications invoke the composition layer to operate the system:

- `cli.py` for command-line interaction
- `api.py` as a query façade (read-only access)
- future batch or service scripts

Each entrypoint leverages the same composed `RefData` object graph; the graph is never independently reconstructed per entrypoint.

## Deterministic generation

Generation services construct:

- periods,
- period cycles,
- futures products,
- futures contracts,
- first day of interest,
- and last trading day.

The generation pipeline consumes JSON definitions from `mxm-refdata-source`, ensuring reproducibility and determinism.

## Materialised reference store

Generated entities are persisted into a reference-data database.

- Current implementation: **SQLite**
- Future deployments: PostgreSQL through the same service layer

## CLI Usage

Create a reference database:

```bash
mxm-refdata rebuild \
  --db-url sqlite:////tmp/mxm-refdata.db \
  --contract-start-date 2024-01-01 \
  --contract-end-date 2026-12-31
```

List products:

```bash
mxm-refdata products \
  --db-url sqlite:////tmp/mxm-refdata.db
```

Inspect contract coverage:

```bash
mxm-refdata coverage \
  --db-url sqlite:////tmp/mxm-refdata.db
```

Run operational smoke checks:

```bash
mxm-refdata smokecheck \
  --db-url sqlite:////tmp/mxm-refdata.db
```

> The CLI operates on the JSON-sourced reference universe. CSVs are used only for demos or testing.

## Python API

```python
from datetime import date
from mxm.refdata import RefDataAPI

api = RefDataAPI.from_config_data(
    {
        "SQL_DB_URL": "sqlite:////tmp/mxm-refdata.db",
        "REFDATA_FUTURES_PRODUCTS_JSON_ROOT": "/home/mxm/mxm-refdata-source/products/futures",
    }
)

products = api.get_all_products()

contracts = api.get_contracts_for_product("cme_gbp_futures")

active_contracts = api.get_active_contracts(as_of_date=date(2026, 5, 1))
```

## Configuration

Primary configuration fields:

```
SQL_DB_URL
REFDATA_DB_MODE
REFDATA_FUTURES_PRODUCTS_JSON_ROOT
REFDATA_CONTRACT_START_DATE
REFDATA_CONTRACT_END_DATE
```

### Buildable mode

```
REFDATA_DB_MODE=buildable
```

- Database treated as deterministic derived state
- Automatic materialisation allowed if empty
- Intended for development, CI, local experimentation, bootstrap

### Managed mode

```
REFDATA_DB_MODE=managed
```

- Automatic materialisation disabled
- Reference database must be created and maintained explicitly
- Intended for operational deployments

## Development

Install dependencies:

```bash
poetry install
```

Run full validation suite:

```bash
make check
```

Repository compliance:

```bash
mxm-foundry check .
```

## Documentation

```
docs/design.md
```

## Roadmap

### v0

- Futures product definitions
- Deterministic futures contract generation
- Trading-calendar integration
- Period and period-cycle models
- Materialised reference-data store
- Typed Python API
- Operational CLI
- Smoke-check framework

### v1

- Expanded futures coverage
- Richer lifecycle-rule models
- Explicit calendar abstractions
- Stronger operational tooling
- Improved ontology documentation

### v2

- ETF support
- FX support
- Historical rule evolution
- Governance and reconciliation workflows
- Integration with future MXM calendar services
- Multi-venue reference-data management

## License

MIT License. See `LICENSE`.

