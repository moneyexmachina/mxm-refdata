"""Tests for refdata smokecheck reporting."""

from collections.abc import Generator
from contextlib import contextmanager

from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from mxm.refdata import diagnostics
from mxm.refdata.diagnostics import (
    RefDataCounts,
    SmokeCheckFailed,
    SmokeCheckReport,
    SmokeCheckResult,
    run_smokechecks,
)


class DummySessionManager:
    """Minimal session manager for smokecheck tests."""

    @contextmanager
    def db_session_scope(self) -> Generator[Session]:
        yield object()  # type: ignore[misc]


def _count_rows(_: Session) -> RefDataCounts:
    return RefDataCounts(
        products=1,
        periods=2,
        contracts=3,
        cycles=4,
        memberships=5,
    )


def _passing_check(_: Session) -> None:
    return None


def _failing_check(_: Session) -> None:
    raise SmokeCheckFailed("expected failure")


def test_smokecheck_report_passed_true_when_all_results_pass() -> None:
    """SmokeCheckReport.passed should be true when all checks pass."""
    report = SmokeCheckReport(
        counts=RefDataCounts(
            products=1,
            periods=1,
            contracts=1,
            cycles=1,
            memberships=1,
        ),
        results=[
            SmokeCheckResult(name="a", status="pass"),
            SmokeCheckResult(name="b", status="pass"),
        ],
    )

    assert report.passed is True


def test_smokecheck_report_passed_false_when_any_result_fails() -> None:
    """SmokeCheckReport.passed should be false when any check fails."""
    report = SmokeCheckReport(
        counts=RefDataCounts(
            products=1,
            periods=1,
            contracts=1,
            cycles=1,
            memberships=1,
        ),
        results=[
            SmokeCheckResult(name="a", status="pass"),
            SmokeCheckResult(name="b", status="fail", message="broken"),
        ],
    )

    assert report.passed is False


def test_run_smokechecks_records_passes_and_failures(
    monkeypatch: MonkeyPatch,
) -> None:
    """run_smokechecks should record failures without raising."""
    monkeypatch.setattr(diagnostics, "count_refdata_rows", _count_rows)
    monkeypatch.setattr(
        diagnostics,
        "SMOKE_CHECKS",
        (
            ("passing check", _passing_check),
            ("failing check", _failing_check),
        ),
    )

    report = run_smokechecks(DummySessionManager())  # type: ignore[arg-type]

    assert report.counts == RefDataCounts(
        products=1,
        periods=2,
        contracts=3,
        cycles=4,
        memberships=5,
    )
    assert report.results == [
        SmokeCheckResult(name="passing check", status="pass"),
        SmokeCheckResult(
            name="failing check",
            status="fail",
            message="expected failure",
        ),
    ]
    assert report.passed is False
