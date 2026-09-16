# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for _import_dotted (symbol import by dotted path).

Covers dotted module paths, chained getattr, the builtins fallback for bare
names (regression: `type` fields with `--value int`), and the error path.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from typing import TYPE_CHECKING

import pytest

from confarg._import import _import_dotted
from confarg.exceptions import SymbolImportError

if TYPE_CHECKING:
    from pathlib import Path


class TestImportDotted:
    """Unit tests for _import_dotted(path)."""

    def test_bare_builtin_int(self) -> None:
        """A bare builtin name resolves against the builtins module."""
        assert _import_dotted("int") is int

    def test_bare_builtin_str(self) -> None:
        """`str` resolves to the str type."""
        assert _import_dotted("str") is str

    def test_bare_builtin_type(self) -> None:
        """`type` resolves to the type metaclass."""
        assert _import_dotted("type") is type

    def test_qualified_builtin_still_works(self) -> None:
        """An explicit `builtins.int` path still resolves (real-module route)."""
        assert _import_dotted("builtins.int") is int

    def test_dotted_module_path(self) -> None:
        """A dotted path into a real module resolves via import + getattr."""
        assert _import_dotted("collections.OrderedDict") is OrderedDict

    def test_unimportable_path_raises(self) -> None:
        """A path that is neither a module nor a builtin raises SymbolImportError."""
        with pytest.raises(SymbolImportError):
            _import_dotted("no.such.module.Class")

    def test_unknown_bare_name_raises(self) -> None:
        """A bare name that is not a builtin raises SymbolImportError."""
        with pytest.raises(SymbolImportError):
            _import_dotted("definitely_not_a_builtin_xyz")

    def test_broken_dependency_is_surfaced_not_masked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """A broken transitive dependency is surfaced, not masked (REF-5).

        A ``ModuleNotFoundError`` raised inside an importable module — here a
        missing dependency it imports — is a real error, not a typo'd path: the
        loader must not swallow it and walk down to shorter prefixes.
        """
        pkg_dir = tmp_path / "ref5_broken_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "broken.py").write_text("import ref5_missing_dependency_xyz\n")
        monkeypatch.syspath_prepend(str(tmp_path))

        pkg_name = "ref5_broken_pkg"

        def _purge() -> None:
            for key in [k for k in sys.modules if k == pkg_name or k.startswith(pkg_name + ".")]:
                sys.modules.pop(key, None)

        request.addfinalizer(_purge)

        with pytest.raises(SymbolImportError) as exc_info:
            _import_dotted("ref5_broken_pkg.broken.Thing")
        msg = str(exc_info.value)
        assert "ref5_missing_dependency_xyz" in msg
        assert "no importable module found" not in msg

    def test_import_error_inside_module_is_surfaced(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """An ImportError raised inside a module is surfaced, not masked (REF-5).

        A non-``ModuleNotFoundError`` ``ImportError`` (failed ``from x import y``,
        a circular import, an explicit ``raise ImportError``) comes from inside a
        module that does exist, so it is a real failure to report.
        """
        pkg_dir = tmp_path / "ref5_initerr_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "broken.py").write_text('raise ImportError("ref5 custom init failure")\n')
        monkeypatch.syspath_prepend(str(tmp_path))

        pkg_name = "ref5_initerr_pkg"

        def _purge() -> None:
            for key in [k for k in sys.modules if k == pkg_name or k.startswith(pkg_name + ".")]:
                sys.modules.pop(key, None)

        request.addfinalizer(_purge)

        with pytest.raises(SymbolImportError) as exc_info:
            _import_dotted("ref5_initerr_pkg.broken.Thing")
        assert "ref5 custom init failure" in str(exc_info.value)
