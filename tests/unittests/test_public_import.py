# tests/unittests/test_public_import.py

"""Tests for the public mxm.refdata package API."""

import mxm.refdata as refdata
from mxm.refdata import (
    RefData,
    RefDataLookupError,
    RefDataReader,
    build_refdata,
)
from mxm.refdata.composition import build_refdata as composition_build_refdata
from mxm.refdata.reader import (
    RefDataLookupError as ReaderRefDataLookupError,
    RefDataReader as ReaderRefDataReader,
)
from mxm.refdata.runtime import RefData as RuntimeRefData


def test_public_imports_resolve_to_canonical_objects() -> None:
    assert RefData is RuntimeRefData
    assert RefDataReader is ReaderRefDataReader
    assert RefDataLookupError is ReaderRefDataLookupError
    assert build_refdata is composition_build_refdata


def test_public_api_is_explicit() -> None:
    assert set(refdata.__all__) == {
        "RefData",
        "RefDataLookupError",
        "RefDataReader",
        "build_refdata",
    }
