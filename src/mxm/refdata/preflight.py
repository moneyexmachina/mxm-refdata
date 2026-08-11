"""Operational preflight checks for MXM reference data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mxm.refdata.composition import build_refdata
from mxm.runtime import RuntimeContext

__all__ = [
    "PreflightCheck",
    "PreflightReport",
    "run_preflight",
]


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


def run_preflight(
    ctx: RuntimeContext,
) -> PreflightReport:
    """Check whether the runtime environment can operate mxm-refdata.

    Preflight is strictly read-only. It verifies that the application can be
    composed, that the configured futures-product source root is available,
    and that the configured PostgreSQL database is reachable.

    It does not inspect whether reference data has already been materialised.
    Persisted-state readiness is owned by ``RefData.diagnostics()``.
    """

    checks: list[PreflightCheck] = []

    try:
        refdata = build_refdata(
            ctx,
        )
    except Exception as err:
        checks.append(
            PreflightCheck(
                name="application composed",
                passed=False,
                message=f"{type(err).__name__}: {err}",
            )
        )

        return PreflightReport(
            checks=tuple(checks),
        )

    checks.append(
        PreflightCheck(
            name="application composed",
            passed=True,
        )
    )

    source_root = Path(
        str(refdata.config["REFDATA_FUTURES_PRODUCTS_JSON_ROOT"])
    ).expanduser()

    checks.append(
        PreflightCheck(
            name="product source root available",
            passed=source_root.is_dir(),
            message=str(source_root),
        )
    )

    try:
        database_reachable = refdata.database.check_connection()
    except Exception as err:
        checks.append(
            PreflightCheck(
                name="database reachable",
                passed=False,
                message=f"{type(err).__name__}: {err}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="database reachable",
                passed=database_reachable,
            )
        )

    return PreflightReport(
        checks=tuple(checks),
    )
