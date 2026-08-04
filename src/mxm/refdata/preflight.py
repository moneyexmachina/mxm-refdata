"""Operational preflight checks for MXM reference data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from mxm.config import make_view
from mxm.refdata.composition import build_refdata
from mxm.runtime import RuntimeContext


@dataclass(frozen=True)
class PreflightCheck:
    """One operational preflight result."""

    name: str
    passed: bool
    message: str = ""


@dataclass(frozen=True)
class PreflightReport:
    """Complete operational preflight result."""

    checks: tuple[PreflightCheck, ...]

    @property
    def passed(self) -> bool:
        """Return whether every preflight check passed."""
        return all(check.passed for check in self.checks)


def run_preflight(ctx: RuntimeContext) -> PreflightReport:
    """Check whether mxm-refdata can operate without changing state."""
    checks: list[PreflightCheck] = []

    config = make_view(
        ctx.config,
        "mxm_refdata",
        readonly=True,
        resolve=True,
    )
    checks.append(PreflightCheck("runtime context resolved", True))

    source_root = Path(config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"]).expanduser()

    checks.append(
        PreflightCheck(
            "product source root available",
            source_root.is_dir(),
            str(source_root),
        )
    )
    paths = ctx.paths
    if paths is None:
        checks.append(
            PreflightCheck(
                "runtime filesystem paths resolved",
                False,
                "RuntimeContext.paths is not available",
            )
        )
        return PreflightReport(tuple(checks))
    for name, path_value in (
        ("data root available", paths.data_root),
        ("artifact root available", paths.artifact_root),
        ("export root available", paths.export_root),
        ("log root available", paths.log_root),
    ):
        path = Path(path_value).expanduser()
        checks.append(
            PreflightCheck(
                name,
                path.is_dir(),
                str(path),
            )
        )

    try:
        refdata = build_refdata(ctx)
    except Exception as err:
        checks.append(
            PreflightCheck(
                "application composed",
                False,
                f"{type(err).__name__}: {err}",
            )
        )
        return PreflightReport(tuple(checks))

    checks.append(PreflightCheck("application composed", True))

    db_url = make_url(config["SQL_DB_URL"])
    is_postgresql = db_url.get_backend_name() == "postgresql"

    checks.append(
        PreflightCheck(
            "PostgreSQL selected",
            is_postgresql,
            db_url.render_as_string(hide_password=True),
        )
    )

    database_reachable = refdata.session_manager.check_db_connection()
    checks.append(
        PreflightCheck(
            "database reachable",
            database_reachable,
            db_url.render_as_string(hide_password=True),
        )
    )

    return PreflightReport(tuple(checks))
