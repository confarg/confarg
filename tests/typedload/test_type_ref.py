# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for type[X] / type / Type[X] field support in confarg.

Covers:
- _coerce_type_ref: valid/invalid dotted paths, class-object pass-through,
  subclass validation, bare `type` (no constraint)
- construct(): dispatch to _coerce_type_ref for type-ref fields
- _serialize_leaf(): class objects serialized to 'module.qualname'
- confarg.build(): end-to-end construction for a dataclass with type[X]
- populate_parser(): argparse metavar for type-ref fields
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

import confarg
import confarg.cli.argparse as confarg_ap
from confarg._serialize import _serialize_leaf
from confarg._types import _StrToken
from confarg.exceptions import ConfargError, SymbolImportError, TypeCoercionError
from confarg.typedload._coerce import _coerce_type_ref
from confarg.typedload._construct import construct

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level helper classes
# These must live at module level so that _import_dotted can find them via
# 'tests.test_type_ref.Base' etc.
# ---------------------------------------------------------------------------


class Base:
    """Base class for type-ref constraint tests."""


class Derived(Base):
    """Subclass of Base — valid for type[Base]."""


class Unrelated:
    """Class unrelated to Base — invalid for type[Base]."""


class Impostor(Base):
    """A class whose qualified name is another class's, so its dotted path imports that one."""


Impostor.__qualname__ = "Derived"


# ---------------------------------------------------------------------------
# Helper: stable dotted paths for the classes above
# ---------------------------------------------------------------------------

_BASE_PATH = f"{Base.__module__}.{Base.__qualname__}"
_DERIVED_PATH = f"{Derived.__module__}.{Derived.__qualname__}"
_UNRELATED_PATH = f"{Unrelated.__module__}.{Unrelated.__qualname__}"


# ---------------------------------------------------------------------------
# TestCoerceTypeRef — unit tests for _coerce_type_ref
# ---------------------------------------------------------------------------


class TestCoerceTypeRef:
    """Unit tests for _coerce_type_ref(tp, value, path)."""

    # --- valid string inputs (StrToken) ---

    def test_valid_subclass_token_returns_class(self) -> None:
        """A _StrToken for a subclass dotted path returns the subclass object."""
        result = _coerce_type_ref(type[Base], _StrToken(_DERIVED_PATH))
        assert result is Derived

    def test_valid_base_class_token_returns_base(self) -> None:
        """A _StrToken for the exact bound class is accepted."""
        result = _coerce_type_ref(type[Base], _StrToken(_BASE_PATH))
        assert result is Base

    def test_bare_type_no_constraint_accepts_any_class(self) -> None:
        """Bare `type` has no constraint — any class is accepted."""
        result = _coerce_type_ref(type, _StrToken(_UNRELATED_PATH))
        assert result is Unrelated

    def test_typing_Type_constraint_accepts_subclass(self) -> None:
        """typing.Type[Base] is equivalent to type[Base] — subclass accepted."""
        result = _coerce_type_ref(type[Base], _StrToken(_DERIVED_PATH))
        assert result is Derived

    # --- class-object pass-through ---

    def test_class_object_subclass_accepted(self) -> None:
        """Passing an actual class object (not a string) that is a subclass is returned as-is."""
        result = _coerce_type_ref(type[Base], Derived)
        assert result is Derived

    def test_class_object_exact_base_accepted(self) -> None:
        """The exact bound class passed as a class object is accepted."""
        result = _coerce_type_ref(type[Base], Base)
        assert result is Base

    def test_class_object_bare_type_any_class(self) -> None:
        """Bare `type` with a class object passes through regardless of hierarchy."""
        result = _coerce_type_ref(type, Unrelated)
        assert result is Unrelated

    # --- error cases ---

    def test_subclass_violation_token_raises(self) -> None:
        """A _StrToken naming an unrelated class raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="not a subclass"):
            _coerce_type_ref(type[Base], _StrToken(_UNRELATED_PATH))

    def test_bad_dotted_path_raises(self) -> None:
        """A _StrToken with an unimportable path raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError):
            _coerce_type_ref(type[Base], _StrToken("no.such.module.Class"))

    def test_non_string_non_class_raises(self) -> None:
        """A plain int value (not a _StrToken or class) raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError):
            _coerce_type_ref(type[Base], 42)

    def test_non_subclass_class_object_raises(self) -> None:
        """Passing an actual class object that violates the constraint raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="not a subclass"):
            _coerce_type_ref(type[Base], Unrelated)

    def test_plain_str_accepted(self) -> None:
        """A plain str, what a file and from_dict() hold, imports as a token does (BUG-230)."""
        assert _coerce_type_ref(type[Base], _DERIVED_PATH) is Derived

    def test_plain_str_subclass_violation_raises(self) -> None:
        """A plain str is checked against the constraint as a token is."""
        with pytest.raises(TypeCoercionError, match="not a subclass"):
            _coerce_type_ref(type[Base], "builtins.int")


# ---------------------------------------------------------------------------
# TestConstruct — type-ref dispatch inside construct()
# ---------------------------------------------------------------------------


class TestConstruct:
    """Tests for construct() dispatching to _coerce_type_ref for type-ref fields."""

    def test_construct_type_ref_with_token(self) -> None:
        """construct() on type[Base] with a _StrToken returns the class."""
        result = construct(type[Base], _StrToken(_DERIVED_PATH))
        assert result is Derived

    def test_construct_bare_type_with_token(self) -> None:
        """construct() on bare `type` with a _StrToken returns the class."""
        result = construct(type, _StrToken(_UNRELATED_PATH))
        assert result is Unrelated

    def test_construct_type_ref_class_passthrough(self) -> None:
        """construct() on type[Base] with an actual class object returns it."""
        result = construct(type[Base], Derived)
        assert result is Derived

    def test_construct_type_ref_violation_raises(self) -> None:
        """construct() raises TypeCoercionError when the class violates the constraint."""
        with pytest.raises(TypeCoercionError):
            construct(type[Base], _StrToken(_UNRELATED_PATH))


# ---------------------------------------------------------------------------
# TestSerializeLeaf — _serialize_leaf for class objects
# ---------------------------------------------------------------------------


class TestSerializeLeaf:
    """Tests for _serialize_leaf serializing class objects to dotted strings."""

    def test_serialize_subclass_to_dotted_path(self) -> None:
        """A class object is serialized to 'module.qualname'."""
        result = _serialize_leaf(type[Base], Derived)
        assert result == _DERIVED_PATH

    def test_serialize_base_class(self) -> None:
        """Bare `type` serializes the class to its dotted path."""
        result = _serialize_leaf(type, Base)
        assert result == _BASE_PATH

    def test_serialize_unrelated_class(self) -> None:
        """Any class serialized via _serialize_leaf yields 'module.qualname'."""
        result = _serialize_leaf(type, Unrelated)
        assert result == _UNRELATED_PATH

    def test_serialize_builtin_class(self) -> None:
        """Builtin classes are serialized using their __module__ and __qualname__."""
        result = _serialize_leaf(type, int)
        assert result == "builtins.int"


# ---------------------------------------------------------------------------
# TestBuildRoundtrip — confarg.build end-to-end
# ---------------------------------------------------------------------------


@dataclass
class ConfigWithTypeRef:
    """Dataclass with a type[Base] field for end-to-end tests."""

    worker: type[Base]


@dataclass
class ConfigWithBareType:
    """Dataclass with a bare `type` field."""

    klass: type


class TestBuildRoundtrip:
    """End-to-end tests: build() constructs a dataclass with type[X] fields."""

    def test_build_type_ref_field(self) -> None:
        """build() constructs ConfigWithTypeRef, resolving the dotted path."""
        result = confarg.build(ConfigWithTypeRef, {"worker": _StrToken(_DERIVED_PATH)})
        assert result.worker is Derived

    def test_build_bare_type_field(self) -> None:
        """build() constructs ConfigWithBareType without a constraint."""
        result = confarg.build(ConfigWithBareType, {"klass": _StrToken(_UNRELATED_PATH)})
        assert result.klass is Unrelated

    def test_build_bare_type_field_bare_builtin(self) -> None:
        """build() resolves a bare builtin name ('int') for a bare `type` field."""
        result = confarg.build(ConfigWithBareType, {"klass": _StrToken("int")})
        assert result.klass is int

    def test_build_type_ref_base_class(self) -> None:
        """build() accepts the exact bound class as the field value."""
        result = confarg.build(ConfigWithTypeRef, {"worker": _StrToken(_BASE_PATH)})
        assert result.worker is Base

    def test_build_type_ref_violation_raises(self) -> None:
        """build() raises TypeCoercionError for a class that violates type[Base]."""
        with pytest.raises(TypeCoercionError):
            confarg.build(ConfigWithTypeRef, {"worker": _StrToken(_UNRELATED_PATH)})

    def test_dump_round_trip(self) -> None:
        """dump() serializes the class object back to its dotted-path string."""
        instance = ConfigWithTypeRef(worker=Derived)
        serialized = confarg.dump(instance)
        assert serialized == {"worker": _DERIVED_PATH}

    def test_a_class_its_path_does_not_import_back_as_cannot_be_dumped(self) -> None:
        """A class defined in a function, or a shadowed name, is refused at dump(), not on read-back.

        Its dotted path holds ``<locals>``, or imports another class (BUG-193).
        """

        class Local(Base):
            pass

        for cls in (Local, Impostor):
            with pytest.raises(ConfargError, match=r"does not import back as it"):
                confarg.dump(ConfigWithTypeRef(worker=cls))

    def test_dump_and_build_roundtrip(self) -> None:
        """Invariant: dump then build() round-trips to the same class, from the plain dump (BUG-230)."""
        instance = ConfigWithTypeRef(worker=Derived)
        restored = confarg.build(ConfigWithTypeRef, confarg.dump(instance))
        assert restored.worker is instance.worker

    def test_a_file_sets_a_type_field(self, tmp_path: Path) -> None:
        """A dump_file() of a type field loads back from the file (BUG-230)."""
        path = tmp_path / "config.json"
        confarg.dump_file(ConfigWithTypeRef(worker=Derived), path)
        assert confarg.load(ConfigWithTypeRef, argv=[], env={}, files=[path]).worker is Derived

    def test_a_file_sets_a_list_of_types(self) -> None:
        """Each element of a list[type] reads a plain str (BUG-230)."""

        @dataclass
        class Holder:
            kinds: list[type]

        assert confarg.from_dict(Holder, {"kinds": ["builtins.int", _DERIVED_PATH]}).kinds == [int, Derived]


class TestBrokenModuleInAUnion:
    """A module that exists but fails while importing stops the union rather than becoming text (BUG-230)."""

    def test_a_broken_module_propagates_past_the_str_variant(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """`type | str` refuses the path of a broken module instead of holding it as a string."""
        pkg_dir = tmp_path / "bug230_union_broken_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "broken.py").write_text("import bug230_union_missing_dependency\n")
        monkeypatch.syspath_prepend(str(tmp_path))

        def _purge() -> None:
            for key in [k for k in sys.modules if k.startswith("bug230_union_broken_pkg")]:
                sys.modules.pop(key, None)

        request.addfinalizer(_purge)
        for value in ("bug230_union_broken_pkg.broken.Thing", _StrToken("bug230_union_broken_pkg.broken.Thing")):
            with pytest.raises(SymbolImportError, match="bug230_union_missing_dependency"):
                construct(type | str, value)
        assert construct(type | str, "bug230_union_broken_pkg.nope") == "bug230_union_broken_pkg.nope"


# ---------------------------------------------------------------------------
# TestArgparseIntegration — populate_parser registers correct metavar
# ---------------------------------------------------------------------------


class TestArgparseIntegration:
    """Tests for populate_parser registering type-ref fields with correct metavar."""

    def test_type_ref_field_registered_with_dotted_metavar(self) -> None:
        """populate_parser registers --worker with metavar 'DOTTED.CLASS.PATH'."""
        parser = argparse.ArgumentParser()
        confarg_ap.populate_parser(ConfigWithTypeRef, parser)
        actions = {a.dest: a for a in parser._actions if hasattr(a, "dest")}
        assert "worker" in actions
        action = actions["worker"]
        assert action.metavar == "DOTTED.CLASS.PATH"

    def test_bare_type_field_registered_with_dotted_metavar(self) -> None:
        """populate_parser registers --klass with metavar 'DOTTED.CLASS.PATH'."""
        parser = argparse.ArgumentParser()
        confarg_ap.populate_parser(ConfigWithBareType, parser)
        actions = {a.dest: a for a in parser._actions if hasattr(a, "dest")}
        assert "klass" in actions
        action = actions["klass"]
        assert action.metavar == "DOTTED.CLASS.PATH"

    def test_parse_args_produces_str_token_in_build(self) -> None:
        """Parsing --worker via argparse then calling build() resolves the class."""
        parser = argparse.ArgumentParser()
        confarg_ap.populate_parser(ConfigWithTypeRef, parser)
        argv = ["--worker", _DERIVED_PATH]
        ns = parser.parse_args(argv)
        # Simulate what confarg.load does: namespace → nested dict → build()
        result = confarg_ap.from_namespace(ConfigWithTypeRef, ns, argv=argv, env_prefix=None)
        assert result.worker is Derived
