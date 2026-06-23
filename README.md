# mxm-refdata

![Version](https://img.shields.io/github/v/release/moneyexmachina/mxm-refdata)
![License](https://img.shields.io/github/license/moneyexmachina/mxm-refdata)
![Python](https://img.shields.io/badge/python-3.13+-blue)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)

Reference-data ontology and contract-generation framework for the Money Ex Machina (MXM) ecosystem.

`mxm-refdata` provides deterministic definitions of futures products, futures contracts, periods, lifecycle dates, and trading-calendar relationships. It materialises these definitions into a queryable reference-data store and exposes them through a typed Python API.

The package is intended to answer questions such as:

```text
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

```text
cme_gbp_futures.Mar-2032
```

is not stored as a static object.

Instead it is deterministically derived from:

- a product specification,
- listing rules,
- period definitions,
- period-cycle membership,
- trading-calendar semantics,
- and lifecycle rules.

This allows downstream systems to reason about contracts independently of any particular data vendor.

Observed prices, quotes, trades, and exchange events belong to separate packages such as `mxm-marketdata`.

## Architecture

`mxm-refdata` consists of four conceptual layers.

### Product specifications

Human-authored definitions describing:

- products,
- contract sizes,
- listing rules,
- lifecycle rules,
- trading calendars,
- and valid period structures.

Currently these specifications are sourced from bundled CSV files.

Future versions are expected to source them from a dedicated `mxm-refdata-source` repository.

### Deterministic generation

Generation services construct:

- periods,
- period cycles,
- futures products,
- futures contracts,
- first day of interest,
- and last trading day.

### Materialised reference store

Generated entities are persisted into a reference-data database.

Current implementation:

```text
SQLite
```

Future deployments may use PostgreSQL through the same service layer.

### Query API

The materialised reference universe is exposed through:

- `RefDataAPI`
- operational CLI commands
- downstream MXM services

## Design Principles

### Explicit construction

`mxm-refdata` no longer discovers configuration implicitly.

Services are constructed from fully resolved configuration data.

```python
config = normalise_refdata_config_data(...)
api = RefDataAPI.from_config_data(config)
```

rather than:

```python
api = RefDataAPI()
```

### Derived state

The reference database is deterministic derived state.

Given:

- product specifications,
- lifecycle rules,
- trading-calendar semantics,
- and a contract materialisation horizon,

the database can be recreated from scratch.

### Separation of concerns

The package distinguishes between:

```text
Product definitions
Contract generation
Trading-calendar access
Reference-data storage
Query APIs
```

while exposing a unified operational interface.

## Installation

```bash
git clone https://github.com/moneyexmachina/mxm-refdata.git
cd mxm-refdata
poetry install
```

## CLI Usage

The CLI is intentionally explicit.

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

Future MXM applications are expected to provide higher-level runtime configuration so that users can invoke commands without repeatedly specifying database locations.

## Python API

```python
from datetime import date

from mxm.refdata import RefDataAPI

api = RefDataAPI.from_config_data(
    {
        "SQL_DB_URL": "sqlite:////tmp/mxm-refdata.db",
    }
)

products = api.get_all_products()

contracts = api.get_contracts_for_product(
    "cme_gbp_futures",
)

active_contracts = api.get_active_contracts(
    as_of_date=date(2026, 5, 1),
)
```

## Configuration

The primary configuration fields are:

```text
SQL_DB_URL

REFDATA_DB_MODE

REFDATA_CONTRACT_START_DATE
REFDATA_CONTRACT_END_DATE
```

### Buildable mode

In buildable mode:

```text
REFDATA_DB_MODE=buildable
```

the database is treated as deterministic derived state.

If the database is empty, `mxm-refdata` may automatically materialise the configured reference universe.

This mode is intended for:

- development,
- CI,
- local experimentation,
- and bootstrap workflows.

### Managed mode

In managed mode:

```text
REFDATA_DB_MODE=managed
```

automatic materialisation is disabled.

The reference database must be created and maintained explicitly.

This mode is intended for operational deployments.

## Development

Install dependencies:

```bash
poetry install
```

Run the full validation suite:

```bash
make check
```

Repository compliance:

```bash
mxm-foundry check .
```

## Documentation

```text
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
