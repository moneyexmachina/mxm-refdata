# mxm-refdata

Canonical reference data package for the [Money Ex Machina](https://moneyexmachina.com) ecosystem.  
Provides identifiers, metadata, and lifecycle rules for instruments such as **futures contracts** and (planned) **ETFs**, ensuring consistency across MXM modules.

---

## Features

- **Futures Reference Data (implemented)**  
  - Define futures products via CSV specifications.  
  - Generate all contracts programmatically using rules for:  
    - First day of interest  
    - Last trading day  
  - Bundled demo dataset: six futures products + JSON rule sets.  

- **ETF Reference Data (planned)**  
  - Universe definition from curated ETF categories.  
  - CSV import + `ETFProduct` domain model.  
  - Consistency checks and enrichment via external providers.  

- **Other Components**  
  - Trading calendar utilities (built on `exchange-calendars`).  
  - ORM + database integration (SQLAlchemy).  
  - Caching and config helpers.  

## Installation

```bash
# clone and install locally
git clone https://github.com/mxm-org/mxm-refdata.git
cd mxm-refdata
poetry install
```


## Quickstart

```python
from mxm_refdata.services.ref_data_service import RefDataService

service = RefDataService()

# list available futures products (demo set)
print(service.list_products())

# generate contracts for a product
contracts = service.generate_contracts("comex_gold_futures")
for c in contracts[:3]:
    print(c.symbol, c.first_trade_date, c.last_trade_date)
```


## Documentation

- [Design Document](docs/design.md): Architecture, scope, and roadmap.  
- API reference: To be generated as part of v0 cleanup.  


## Development

### Setup
```bash
poetry install
poetry run pytest
```

### Code Quality
```bash
poetry run black .
poetry run isort .
poetry run ruff check .
poetry run pyright
```

### Contribution
- Add type hints + Google-style docstrings.  
- Keep tests green (`pytest`).  
- Document new features in `docs/design.md`.  

## Roadmap

- **v0**: Consolidate futures functionality, type hints, docstrings, docs.  
- **v1**: Add ETF universe (CSV import, ETFProduct model, services).  
- **v2**: External reconciliation with providers (Bloomberg, Refinitiv, JustETF).  

