# mxm-refdata

**Reference data library for the Money Ex Machina (MXM) ecosystem.**

`mxm-refdata` provides a canonical, programmatic definition of financial instruments—currently focused on **futures products and contracts**—including identifiers, metadata, and lifecycle rules.  
It is designed to be **imported as a library by MXM applications** (for example `mxm-v1`), while also offering internal services and scripts for building and maintaining its reference database.

## What this package is (and is not)

### It *is*
- A **library package** intended to be imported by other applications.
- The canonical definition of:
  - futures products (from CSV specifications),
  - contract generation rules,
  - trading calendars and lifecycle logic.
- A provider of a **query API** over a materialised reference database.

### It is *not*
- A standalone trading application.
- The owner of application-level configuration or state placement.
- A black-box data dump.

Application-specific concerns (where state lives, how refdata is shared between components, how updates are governed) belong **above** this package.

## Architecture overview

`mxm-refdata` deliberately separates **three layers**.

### 1. Reference specifications (source of truth)

Small, human-authored files bundled with the package:

- `data/futures_products.csv`
- JSON rule sets for:
  - first day of interest
  - last trading day

These files define *what exists* and *how contracts are generated*.  
They are stable, version-controlled, and part of the package distribution.

### 2. Materialised reference database (derived state)

From the specifications, `mxm-refdata` can materialise a SQLite database containing:

- futures products
- all generated contracts
- periods and lifecycle dates
- indices for efficient querying

This database is **derived state**:
- it can be rebuilt from the specifications,
- but it may later become **managed and curated** (see modes below).

The database exists to avoid regenerating tens or hundreds of thousands of contracts on every run.

### 3. Public query API (“shopwindow”)

The public entrypoint for consumers is the **read-only API**:

- `mxm_refdata.api.RefDataAPI`

It provides cached, high-level queries such as:
- list all products
- retrieve contracts for a product
- resolve active contracts on a given date

Consumers should use this API rather than internal services.

## Operating modes

`mxm-refdata` supports two conceptual modes of operation.  
Only **Buildable mode** is expected to be used during early development and MVP work.

### Buildable mode (default)

- The reference database is treated as a **materialised cache**.
- If the database does not exist or is empty, it may be **automatically created** from the packaged specifications.
- Suitable for:
  - development
  - CI
  - local experimentation
  - early MXM MVP integration

This mode prioritises *usability and reproducibility*.

### Managed mode (planned / opt-in)

- The reference database is treated as **authoritative state**.
- Automatic creation or rebuilding is **forbidden**.
- Updates must be performed explicitly via management services or scripts.
- Intended for:
  - curated reference data
  - reconciliation against external providers
  - audited, long-lived deployments

Managed mode will be enabled via configuration once governance workflows are in place.

## Installation

```bash
# clone and install locally
git clone https://github.com/mxm-org/mxm-refdata.git
cd mxm-refdata
poetry install
```


## Quickstart (library usage)

The recommended entrypoint for consumers is the **query API**.

```python
from mxm.refdata.api.ref_data_api import RefDataAPI

api = RefDataAPI()

# list available futures products (demo dataset)
products = api.get_all_products()
for p in products:
    print(p.product_id, p.exchange, p.currency)
```

On first use, in *buildable mode*, the reference database will be materialised automatically from the packaged specifications.

Subsequent calls reuse the existing database.

## Internal services (advanced / maintenance)

The package also contains **internal services** for building and maintaining the reference database:

- `mxm_refdata.services.RefDataService`
- CLI-style scripts under `mxm_refdata/scripts/`

These are intended for:
- explicit initialisation
- rebuilding reference data
- future reconciliation workflows

They are **not** the recommended entrypoint for application code.

## Configuration

For now, `mxm-refdata` ships with a minimal internal configuration layer.

Key settings include:
- database location (SQLite URL)
- operating mode (`buildable` vs `managed`)
- optional overrides for specification file paths

In the MXM ecosystem, these concerns will eventually be owned by a higher-level configuration system (for example `mxm-config`), with `mxm-refdata` behaving purely as a configurable library.

## Documentation

- `docs/design.md` — architecture, scope, and roadmap
- `docs/package_audit.md` — technical audit and known limitations

## Development

### Setup

```bash
poetry install
poetry run pytest
```

### Code quality

```bash
poetry run black .
poetry run isort .
poetry run ruff check .
poetry run pyright
```

### Contribution guidelines

- Keep `mxm-refdata` usable as an imported library.
- Avoid import-time side effects.
- Add tests for any behaviour that creates or mutates durable state.
- Document architectural decisions in `docs/design.md`.

## Roadmap

- **v0**: Stabilise futures reference data, packaging, and query API.
- **v1**: Introduce ETF universe definitions and models.
- **v2**: External reconciliation, governance, and managed refdata workflows.
