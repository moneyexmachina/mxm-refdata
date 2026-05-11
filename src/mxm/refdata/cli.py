from __future__ import annotations

import datetime as dt
from datetime import date
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mxm.refdata.api.ref_data_api import RefDataAPI
from mxm.refdata.services.bootstrap import build_refdata, rebuild_refdata
from mxm.refdata.services.smokecheck import run_smokechecks

app = typer.Typer(
    add_completion=False,
    help="Inspect and materialize MXM reference data.",
)

console = Console()


def parse_cli_date(value: str) -> date:
    """Parse a CLI date in YYYY-MM-DD format."""
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as err:
        raise typer.BadParameter("Expected date in YYYY-MM-DD format.") from err


@app.command("build")
def build() -> None:
    """Build the local reference-data database."""
    build_refdata()
    console.print("[green]Reference data database built.[/]")


@app.command("rebuild")
def rebuild() -> None:
    """Destructively rebuild the local reference-data database."""
    rebuild_refdata()
    console.print("[green]Reference data database rebuilt.[/]")


@app.command("products")
def products() -> None:
    """List available futures products."""
    api = RefDataAPI()
    rows = api.get_all_products()

    table = Table(title="MXM Futures Products")
    table.add_column("Product ID")
    table.add_column("Venue")
    table.add_column("Currency")
    table.add_column("Unit")
    table.add_column("Period Types")

    for product in rows:
        table.add_row(
            product.product_id,
            product.venue,
            product.currency.value,
            product.unit.value,
            ", ".join(period_type.value for period_type in product.period_types),
        )

    console.print(table)


@app.command("product")
def product(
    product_id: Annotated[str, typer.Argument(help="Canonical product ID")],
) -> None:
    """Show one futures product."""
    api = RefDataAPI()
    product_obj = api.get_product_by_id(product_id)

    table = Table(title=f"Product: {product_obj.product_id}")
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("product_id", product_obj.product_id)
    table.add_row("venue", product_obj.venue)
    table.add_row("description", product_obj.description)
    table.add_row("currency", product_obj.currency.value)
    table.add_row("unit", product_obj.unit.value)
    table.add_row("contract_size", str(product_obj.contract_size))
    table.add_row("listing_rule", product_obj.listing_rule)
    table.add_row(
        "period_types",
        ", ".join(period_type.value for period_type in product_obj.period_types),
    )
    table.add_row("settlement", product_obj.settlement.value)
    table.add_row("last_trading_rule", product_obj.last_trading_rule)
    table.add_row("expiry_rule", product_obj.expiry_rule)
    table.add_row("trading_calendar", product_obj.trading_calendar)
    table.add_row("tick_size", str(product_obj.tick_size))
    table.add_row("tick_value", str(product_obj.tick_value))
    table.add_row("valid_period_rule", product_obj.valid_period_rule)

    console.print(table)


@app.command("contracts")
def contracts(
    product_id: Annotated[str, typer.Argument(help="Canonical product ID")],
) -> None:
    """List contracts for a futures product."""
    api = RefDataAPI()
    rows = api.get_contracts_for_product(product_id)

    table = Table(title=f"Contracts: {product_id}")
    table.add_column("Contract ID")
    table.add_column("Period")
    table.add_column("First Interest")
    table.add_column("Last Trading")

    for contract in rows:
        table.add_row(
            contract.contract_id,
            contract.period_id,
            contract.first_day_of_interest.isoformat(),
            contract.last_trading_day.isoformat(),
        )

    console.print(table)


@app.command("active")
def active(
    as_of_date: Annotated[str, typer.Argument(help="Date in YYYY-MM-DD format")],
    product_id: Annotated[str | None, typer.Option(help="Optional product ID")] = None,
) -> None:
    """List active contracts as of a date."""
    parsed_date = parse_cli_date(as_of_date)
    api = RefDataAPI()
    rows = api.get_active_contracts(parsed_date, product_id=product_id)

    table = Table(title=f"Active contracts: {parsed_date.isoformat()}")
    table.add_column("Product ID")
    table.add_column("Contract ID")
    table.add_column("Period")
    table.add_column("Last Trading")

    for contract in rows:
        table.add_row(
            contract.product_id,
            contract.contract_id,
            contract.period_id,
            contract.last_trading_day.isoformat(),
        )

    console.print(table)


@app.command("coverage")
def coverage() -> None:
    """Show contract coverage by product."""
    api = RefDataAPI()
    products = api.get_all_products()

    table = Table(title="MXM Refdata Coverage")
    table.add_column("Product ID")
    table.add_column("Venue")
    table.add_column("First Contract")
    table.add_column("Last Contract")
    table.add_column("Count", justify="right")

    for product_obj in products:
        product_contracts = api.get_contracts_for_product(product_obj.product_id)

        if not product_contracts:
            table.add_row(product_obj.product_id, product_obj.venue, "-", "-", "0")
            continue

        table.add_row(
            product_obj.product_id,
            product_obj.venue,
            product_contracts[0].contract_id,
            product_contracts[-1].contract_id,
            str(len(product_contracts)),
        )

    console.print(table)


@app.command("smokecheck")
def smokecheck() -> None:
    """Run operational smoke checks against the local refdata database."""
    report = run_smokechecks()

    console.print("[bold]MXM Refdata Smokecheck[/bold]")
    console.print(
        "Counts: "
        f"products={report.counts.products}, "
        f"periods={report.counts.periods}, "
        f"contracts={report.counts.contracts}, "
        f"cycles={report.counts.cycles}, "
        f"memberships={report.counts.memberships}"
    )

    table = Table(title="Smokecheck Results")
    table.add_column("Status")
    table.add_column("Check")
    table.add_column("Message")

    for result in report.results:
        status = "[green]PASS[/]" if result.status == "pass" else "[red]FAIL[/]"
        table.add_row(status, result.name, result.message)

    console.print(table)

    if not report.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
