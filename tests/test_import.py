# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for _import_dotted (symbol import by dotted path).

Covers dotted module paths, chained getattr, the builtins fallback for bare
names (regression: `type` fields with `--value int`), and the error path.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest

from confarg._import import _import_dotted
from confarg.exceptions import SymbolImportError


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
