# mxm-refdata

![Version](https://img.shields.io/github/v/release/moneyexmachina/mxm-refdata)
![License](https://img.shields.io/github/license/moneyexmachina/mxm-refdata)
![Python](https://img.shields.io/badge/python-3.13+-blue)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)

Reference data and contract ontology for the Money Ex Machina (MXM) ecosystem.

`mxm-refdata` provides canonical, programmatic definitions of financial instruments and trading structures, currently focused on:

- futures products,
- futures contracts,
- lifecycle rules,
- trading calendars,
- periods and period cycles,
- and deterministic contract generation.

The package acts as the ontological reference layer for MXM systems such as `mxm-v1`.

## Purpose

`mxm-refdata` defines *what financial reference objects exist* and *how they are constructed*.

For example, a futures contract such as:

```text
cme_gbp_futures.Mar-2032
```

is treated as a deterministic construct derived from:

- product specifications,
- listing rules,
- period systems,
- and trading-calendar semantics.

This allows MXM systems to reason about financial structures independently of any specific market-data provider.

`mxm-refdata` therefore models the constructive ontology of financial instruments, while observed prices, trades, quotes, and exchange events belong to the separate market-observation layer (`mxm-marketdata`).

## Architecture

`mxm-refdata` consists of four main layers:

1. **Reference specifications**  
   Human-authored product and lifecycle specifications bundled with the package.

2. **Deterministic generation**  
   Services that construct contracts, periods, lifecycle dates, and calendar relationships.

3. **Materialised reference store**  
   SQLite database containing generated products, contracts, periods, cycles, and lifecycle state.

4. **Query and inspection interfaces**  
   Typed Python API and operational CLI.

## Installation

```bash
git clone https://github.com/moneyexmachina/mxm-refdata.git
cd mxm-refdata
poetry install
```

## Usage

Build the local reference database:

```bash
mxm-refdata build
```

Rebuild from scratch:

```bash
mxm-refdata rebuild
```

Inspect products:

```bash
mxm-refdata products
```

Inspect contract coverage:

```bash
mxm-refdata coverage
```

Run operational smoke checks:

```bash
mxm-refdata smokecheck
```

## Python API

```python
from datetime import date

from mxm.refdata.api.ref_data_api import RefDataAPI

api = RefDataAPI()

products = api.get_all_products()

contracts = api.get_contracts_for_product(
    "comex_gold_futures"
)

active_contracts = api.get_active_contracts(
    as_of_date=date(2026, 5, 1),
)
```

## Operating Modes

### Buildable mode

In buildable mode, the reference database is treated as deterministic derived state.

If missing or empty, the package may automatically:

- create the schema,
- generate contracts,
- and materialise the reference universe.

This mode supports:

- development,
- CI,
- local experimentation,
- and early-stage deployments.

### Managed mode

Managed mode treats the reference database as governed operational state.

Updates occur explicitly through controlled management and reconciliation workflows.

## Development

`mxm-refdata` is maintained as an `mxm-foundry` compliant package.

Primary development gate:

```bash
make check
```

Validate repository compliance:

```bash
mxm-foundry check .
```

Setup:

```bash
poetry install
```

## Documentation

- `docs/design.md`

## Roadmap

### v0

- Futures product specifications
- Deterministic futures contract generation
- Trading calendar integration
- Period and period-cycle models
- Materialised SQLite reference store
- Typed query API
- Operational CLI and smoke checks
- `mxm-foundry` compliance

### v1

- Broader futures product coverage
- Stronger typed lifecycle-rule models
- Explicit `TradingCalendarId` abstractions
- Improved CLI inspection and filtering
- Clearer ontology boundaries and documentation

### v2

- ETF and FX product support
- Managed reference governance
- Historical exchange rule evolution
- External reconciliation workflows
- Expanded multi-venue ontology
- Integration boundaries with `mxm-marketdata`
- Integration boundaries with future `mxm-calendar`

## License

MIT License. See [LICENSE](LICENSE).
