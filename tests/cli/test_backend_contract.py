# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests: every CLI integration must behave exactly like ``confarg.load()``.

All tests here run against the parametrised ``loader`` fixture (vanilla,
argparse, click, cyclopts) or one of its subsets.  Behavior shared by the
integrations belongs here, written once; only genuinely framework-specific
behavior (help text, registration idioms, completion) stays in the per-backend
test directories.

List-field CLI syntax intentionally differs between integrations and stays
visible: ``TestListSpaceSeparated`` runs on vanilla/argparse/cyclopts and
``TestListRepeatedFlags`` on click/cyclopts.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import warnings
from collections.abc import (
    Callable,  # noqa: TC003  # used in a runtime dataclass annotation confarg resolves via get_type_hints
)
from dataclasses import dataclass
from dataclasses import field as dataclasses_field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple
from uuid import UUID

import pytest

import confarg
import confarg.cli._build as build_mod
from confarg._files import INCLUDE_KEY
from confarg._merge import DICT_DELETE
from confarg.cli._build import build_static_flags
from confarg.exceptions import ConfargError, ConfargWarning, MissingFieldError, TypeCoercionError, UnknownArgumentError
from tests._loaders import ArgparseLoader, ClickLoader, CycloptsLoader, TyperLoader, VanillaLoader
from tests.conftest import AppConfig, CacheConfig, DbConfig, WithCollections, make_target

if TYPE_CHECKING:
    from collections.abc import Generator

    from tests._loaders import ConfargLoader

# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Simple:
    """Simple flat dataclass with defaults."""

    host: str = "localhost"
    port: int = 8080


@dataclass
class Nested:
    """Dataclass with a nested struct field."""

    db: Simple = dataclasses.field(default_factory=Simple)
    debug: bool = False


@dataclass
class WithCsvRows:
    """Dataclass whose list field is populated from a CSV include."""

    db: list[Simple] = dataclasses.field(default_factory=list)


@dataclass
class WithList:
    """Dataclass with a list field."""

    tags: list[str] = dataclasses.field(default_factory=list)


@dataclass
class _WithSetTags:
    """Dataclass whose varlen collection is a set."""

    tags: set[str] = dataclasses.field(default_factory=set)


@dataclass
class _WithVarTuple:
    """Dataclass whose varlen collection is a homogeneous tuple."""

    tags: tuple[str, ...] = ()


@dataclass
class _WithTagsAndName:
    """A varlen collection with a scalar neighbour, to check what a bare flag consumes."""

    tags: list[str] = dataclasses.field(default_factory=list)
    name: str = "default"


@dataclass
class WithOptional:
    """Dataclass with an optional field."""

    name: str = "default"
    label: str | None = None


class Color(Enum):
    """Color enumeration for enum tests."""

    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@dataclass
class WithEnum:
    """Dataclass with an Enum field."""

    color: Color = Color.RED


@dataclass
class WithLiteral:
    """Dataclass with a Literal field."""

    level: Literal["debug", "info", "warning"] = "info"


@dataclass
class _WithStrFloat:
    input: str | float


@dataclass
class _WithStrBool:
    input: str | bool


class _StealMarker:
    """Module-level class used as a dotted-path target for str | type stealing tests."""


@dataclass
class _WithStrType:
    value: str | type


@dataclass
class _WithIntFloat:
    value: int | float = 0


@dataclass
class _WithIntDecimal:
    value: int | Decimal = 0


@dataclass
class _PlainCastScalars:
    """Scalar leaf fields of each castable type, for plain-field force-cast tests (BUG-72)."""

    host: str = "h"
    port: int = 1
    ratio: float = 0.5
    enabled: bool = False


@dataclass
class _OptionalScalar:
    note: str | None = None


@dataclass
class _NestedPlainCast:
    inner: _PlainCastScalars = dataclasses_field(default_factory=_PlainCastScalars)


class _Point(NamedTuple):
    """Fixed-length sequence with named fields."""

    x: int
    y: int


@dataclass
class _WithIntPair:
    pair: tuple[int, int] = (0, 0)


@dataclass
class _WithMixedPair:
    pair: tuple[int, str] = (0, "zero")


@dataclass
class _WithPoint:
    pair: _Point = dataclasses_field(default_factory=lambda: _Point(0, 0))


@dataclass
class _PointScale:
    """A namedtuple field beside a scalar an expression over it fills."""

    pair: _Point = dataclasses_field(default_factory=lambda: _Point(0, 0))
    scale: int = 0


@dataclass
class _WithOptionalPoint:
    pair: _Point | None = None


@dataclass
class _WithOptionalIntPair:
    pair: tuple[int, int] | None = None


class _Inner(NamedTuple):
    """A namedtuple nested inside another namedtuple's field."""

    a: int = 0
    b: str = "x"


@dataclass
class _InnerStruct:
    """A struct nested inside a namedtuple's field."""

    a: int = 0


class _PtNested(NamedTuple):
    """A namedtuple one of whose fields is itself structured (BUG-68)."""

    inner: _Inner | None = None
    x: int = 0


@dataclass
class _WithNestedPoint:
    pt: _PtNested = dataclasses_field(default_factory=_PtNested)


class _PtPlainNested(NamedTuple):
    """The same shape without Optional, whose field's flag is a fixed-arity one (BUG-68)."""

    inner: _Inner = _Inner(0, "w")
    x: int = 0


@dataclass
class _WithPlainNestedPoint:
    pt: _PtPlainNested = dataclasses_field(default_factory=_PtPlainNested)


class _PtStructField(NamedTuple):
    """A namedtuple whose structured field is a struct, not a namedtuple (BUG-68)."""

    inner: _InnerStruct = _InnerStruct()
    x: int = 0


@dataclass
class _WithStructFieldPoint:
    pt: _PtStructField = dataclasses_field(default_factory=_PtStructField)


class _PtOptionalStructField(NamedTuple):
    """The same struct field under Optional, whose union has no sequence variant (BUG-68)."""

    inner: _InnerStruct | None = None
    x: int = 0


@dataclass
class _WithOptionalStructFieldPoint:
    pt: _PtOptionalStructField = dataclasses_field(default_factory=_PtOptionalStructField)


class _DefPoint(NamedTuple):
    """A namedtuple whose fields all default, so one sub-flag can fill the rest (BUG-80)."""

    x: int = 0
    y: int = 0


@dataclass
class _WithDefPoint:
    pair: _DefPoint = dataclasses_field(default_factory=_DefPoint)


@dataclass
class _WithOptionalIntList:
    input: list[int] | None = None


@dataclass
class _WithStrTuple:
    input: str | tuple[str, str]


@dataclass
class _WithStrList:
    input: str | list[str]


@dataclass
class _WithIntList:
    input: int | list[int]


@dataclass
class _WithBoolList:
    input: bool | list[str]


@dataclass
class _WithStrBoolList:
    values: list[str | bool] = dataclasses.field(default_factory=list)


@dataclass
class _WithIntNoneList:
    values: list[int | None] = dataclasses.field(default_factory=list)


@dataclass
class _BaseDB:
    """Abstract base database config (inheritance dispatch)."""


@dataclass
class _SQLiteDB(_BaseDB):
    dbpath: str


@dataclass
class _ServerDB(_BaseDB):
    host: str
    port: int


@dataclass
class _NestedDB:
    """Struct whose field is a base class with subclasses (nested inheritance dispatch)."""

    db: _BaseDB = dataclasses.field(default_factory=_BaseDB)


@dataclass
class _DiamondBase:
    """Base whose subclasses form a diamond: _DiamondJoin inherits two paths to it."""


@dataclass
class _DiamondLeft(_DiamondBase):
    left: int = 0


@dataclass
class _DiamondRight(_DiamondBase):
    right: int = 1


@dataclass
class _DiamondJoin(_DiamondLeft, _DiamondRight):
    join: int = 2


@dataclass
class _RootSQLite:
    """SQLite config for union-root tests."""

    dbpath: str


@dataclass
class _RootDBServer:
    """DB server config for union-root tests."""

    host: str
    port: int
    name: str


_RootDBConfig: Any = _RootSQLite | _RootDBServer


@dataclass
class _RootMariaDBTyped:
    """MariaDB variant with a Literal discriminator."""

    type: Literal["mariadb"] = "mariadb"
    host: str = ""


@dataclass
class _RootPostgreTyped:
    """PostgreSQL variant with a Literal discriminator."""

    type: Literal["postgres"] = "postgres"
    host: str = ""


_RootTypedDBConfig: Any = _RootMariaDBTyped | _RootPostgreTyped


@dataclass
class _WithAnyField:
    """A field the two-gate JSON magic can't reach — only ``.json`` decodes it."""

    data: Any = None


@dataclass
class _WithJsonNamedField:
    """A field literally named ``json`` (a cast word): the real field must win."""

    json: int = 0


@dataclass
class _InnerJson:
    json: int = 0


@dataclass
class _OuterInner:
    inner: _InnerJson = dataclasses.field(default_factory=_InnerJson)


@dataclass
class _WithDictField:
    d: dict[str, int] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loading basics
# ---------------------------------------------------------------------------


class TestLoadContract:
    """Core load behavior every integration must share."""

    def test_scalar_values(self, loader: ConfargLoader) -> None:
        """CLI values are coerced to the field types."""
        cfg = loader.load(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        assert cfg.host == "myhost"
        assert cfg.port == 9090

    def test_defaults_used_when_not_provided(self, loader: ConfargLoader) -> None:
        """Omitted options fall back to dataclass defaults."""
        cfg = loader.load(Simple, argv=[], env={})
        assert cfg.host == "localhost"
        assert cfg.port == 8080

    def test_only_cli_values_override_defaults(self, loader: ConfargLoader) -> None:
        """Provided options override defaults; omitted ones keep them."""
        cfg = loader.load(Simple, argv=["--host", "explicit"], env={})
        assert cfg.host == "explicit"
        assert cfg.port == 8080

    def test_nested(self, loader: ConfargLoader) -> None:
        """Dotted options are nested into the correct sub-struct."""
        cfg = loader.load(Nested, argv=["--db.host", "db1", "--debug", "true"], env={})
        assert cfg.db.host == "db1"
        assert cfg.debug is True

    def test_missing_required_raises(self, loader: ConfargLoader) -> None:
        """A required field absent from all sources raises MissingFieldError."""
        with pytest.raises(MissingFieldError):
            loader.load(DbConfig, argv=[], env={})

    def test_optional_field_absent(self, loader: ConfargLoader) -> None:
        """Optional fields default to None when absent."""
        cfg = loader.load(WithOptional, argv=[], env={})
        assert cfg.name == "default"
        assert cfg.label is None

    def test_optional_field_provided(self, loader: ConfargLoader) -> None:
        """Optional fields are set when provided."""
        cfg = loader.load(WithOptional, argv=["--label", "hello"], env={})
        assert cfg.label == "hello"

    def test_enum_by_value(self, loader: ConfargLoader) -> None:
        """Enum fields accept enum values (not just names)."""
        cfg = loader.load(WithEnum, argv=["--color", "blue"], env={})
        assert cfg.color is Color.BLUE

    def test_literal_field(self, loader: ConfargLoader) -> None:
        """Literal fields accept their member values."""
        cfg = loader.load(WithLiteral, argv=["--level", "warning"], env={})
        assert cfg.level == "warning"

    def test_env_vars(self, loader: ConfargLoader) -> None:
        """Environment variables are merged at lower priority than CLI."""
        cfg = loader.load(
            Simple,
            argv=[],
            env={"MYAPP_HOST": "envhost", "MYAPP_PORT": "1234"},
            env_prefix="MYAPP_",
        )
        assert cfg.host == "envhost"
        assert cfg.port == 1234

    def test_cli_overrides_env(self, loader: ConfargLoader) -> None:
        """CLI values have higher priority than env vars."""
        cfg = loader.load(
            Simple,
            argv=["--host", "clihost"],
            env={"MYAPP_HOST": "envhost"},
            env_prefix="MYAPP_",
        )
        assert cfg.host == "clihost"

    def test_env_disabled_by_default(self, loader: ConfargLoader) -> None:
        """Env vars are ignored when env_prefix is None (the default)."""
        cfg = loader.load(Simple, argv=[], env={"HOST": "envhost", "PORT": "9999"})
        assert cfg.host == "localhost"
        assert cfg.port == 8080


# ---------------------------------------------------------------------------
# List syntax — intentionally split per convention
# ---------------------------------------------------------------------------


class TestListSpaceSeparated:
    """Space-separated list values (vanilla, argparse, cyclopts)."""

    def test_list_field(self, space_sep_loader: ConfargLoader) -> None:
        """--tags a b c collects into a list."""
        cfg = space_sep_loader.load(WithList, argv=["--tags", "a", "b", "c"], env={})
        assert cfg.tags == ["a", "b", "c"]


class TestListRepeatedFlags:
    """Repeated-flag list values (click, cyclopts)."""

    def test_list_field(self, repeated_loader: ConfargLoader) -> None:
        """--tags a --tags b collects into a list."""
        cfg = repeated_loader.load(WithList, argv=["--tags", "x", "--tags", "y"], env={})
        assert cfg.tags == ["x", "y"]


# ---------------------------------------------------------------------------
# Repeating a multi-token flag means the same thing everywhere
# ---------------------------------------------------------------------------


class TestRepeatedFlagAccumulationContract:
    """A repeated multi-token flag accumulates its tokens, in every front-end.

    Which *spelling* a framework accepts diverges; what repeating a flag *means* does
    not. ``--tags x --tags y`` is a second spelling of ``--tags x y`` everywhere, so
    these cases use the repeated form every front-end accepts. Regression guard: the
    two answers drifted apart unnoticed, vanilla and argparse keeping only the last
    occurrence (BUG-37).
    """

    def test_varlen_list_repeated(self, loader: ConfargLoader) -> None:
        """--tags x --tags y accumulates into ['x', 'y']."""
        cfg = loader.load(WithList, argv=["--tags", "x", "--tags", "y"], env={})
        assert cfg.tags == ["x", "y"]

    def test_varlen_list_repeated_three_times(self, loader: ConfargLoader) -> None:
        """Every occurrence contributes, in argv order."""
        cfg = loader.load(WithList, argv=["--tags", "x", "--tags", "y", "--tags", "z"], env={})
        assert cfg.tags == ["x", "y", "z"]

    def test_union_seq_repeated_builds_the_sequence(self, loader: ConfargLoader) -> None:
        """--input 1 --input 2 fills the list variant of int | list[int]."""
        cfg = loader.load(_WithIntList, argv=["--input", "1", "--input", "2"], env={})
        assert cfg.input == [1, 2]

    def test_repeated_json_array_tokens_are_items(self, loader: ConfargLoader) -> None:
        """An inline JSON array is a single-token spelling: repeated, the tokens are items."""
        cfg = loader.load(WithList, argv=["--tags", '["a","b"]', "--tags", '["c"]'], env={})
        assert cfg.tags == ['["a","b"]', '["c"]']

    def test_repetition_replaces_the_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Repetition accumulates within the CLI channel; the list it builds replaces the file."""
        base = tmp_yaml("tags: [alice, bob]\n")
        cfg = loader.load(WithList, argv=["--config", str(base), "--tags", "x", "--tags", "y"], env={})
        assert cfg.tags == ["x", "y"]

    def test_merged_dict_matches_vanilla(self, loader: ConfargLoader) -> None:
        """The raw merged dict is byte-identical across every front-end."""
        merged = loader.merge(WithList, argv=["--tags", "x", "--tags", "y"], env={})
        assert merged == {"tags": ["x", "y"]}

    def test_mixed_spellings_accumulate(self, space_sep_loader: ConfargLoader) -> None:
        """A space-separated occurrence and a repeated one add up (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(WithList, argv=["--tags", "x", "y", "--tags", "z"], env={})
        assert cfg.tags == ["x", "y", "z"]

    def test_json_array_token_beside_a_plain_one(self, space_sep_loader: ConfargLoader) -> None:
        """Two tokens are two items, so the '[' one is not decoded (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(WithList, argv=["--tags", '["a","b"]', "z"], env={})
        assert cfg.tags == ['["a","b"]', "z"]


# ---------------------------------------------------------------------------
# A bare varlen collection flag clears the collection, in every front-end
# ---------------------------------------------------------------------------


class TestBareVarlenFlagContract:
    """``--<collection>`` with nothing after it empties the collection, everywhere.

    A varlen collection flag consumes greedily and is content with zero tokens, so the
    bare form is a legal command that *clears* the collection rather than a missing
    value.  Regression guard: click and typer answered ``Option '--tags' requires an
    argument.`` and cyclopts asserted the moment a bare occurrence stood beside a valued
    one (BUG-38).
    """

    def test_bare_list_flag_yields_the_empty_list(self, loader: ConfargLoader) -> None:
        """--tags alone builds the empty list."""
        cfg = loader.load(WithList, argv=["--tags"], env={})
        assert cfg.tags == []

    def test_bare_list_flag_clears_a_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The clear is what a lower-priority source makes audible."""
        base = tmp_yaml("tags: [alice, bob]\n")
        cfg = loader.load(WithList, argv=["--config", str(base), "--tags"], env={})
        assert cfg.tags == []

    def test_bare_set_flag_clears_a_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A set is the same varlen family, so the bare form empties it too."""
        base = tmp_yaml("tags: [alice, bob]\n")
        cfg = loader.load(_WithSetTags, argv=["--config", str(base), "--tags"], env={})
        assert cfg.tags == set()

    def test_bare_varlen_tuple_flag_clears_a_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``tuple[str, ...]`` is varlen, not fixed-arity: the bare form empties it."""
        base = tmp_yaml("tags: [alice, bob]\n")
        cfg = loader.load(_WithVarTuple, argv=["--config", str(base), "--tags"], env={})
        assert cfg.tags == ()

    def test_bare_union_seq_flag_yields_the_empty_list(self, loader: ConfargLoader) -> None:
        """A union with a varlen sequence variant takes the bare form as the empty list."""
        cfg = loader.load(_WithIntList, argv=["--input"], env={})
        assert cfg.input == []

    def test_bare_optional_varlen_flag_yields_the_empty_list(self, loader: ConfargLoader) -> None:
        """``list[int] | None`` takes the bare form as the empty list too (BUG-61)."""
        cfg = loader.load(_WithOptionalIntList, argv=["--input"], env={})
        assert cfg.input == []

    def test_bare_union_without_a_varlen_variant_is_rejected(self, loader: ConfargLoader) -> None:
        """``str | tuple[str, str]`` has no empty value to store, so the bare form is an error.

        The gate is the multi-token *shape*, not "is there something to clear": the bare
        occurrence is honored as far as the empty value, and the fixed-arity variant is
        what refuses it -- with confarg's own error, in every front-end.
        """
        with pytest.raises(ConfargError):
            loader.load(_WithStrTuple, argv=["--input"], env={})

    def test_bare_flag_does_not_swallow_the_next_flag(self, loader: ConfargLoader) -> None:
        """The flag after a bare occurrence is still a flag, not its item."""
        cfg = loader.load(_WithTagsAndName, argv=["--tags", "--name", "bob"], env={})
        assert cfg.tags == []
        assert cfg.name == "bob"

    def test_valued_then_bare_keeps_the_value(self, loader: ConfargLoader) -> None:
        """A bare occurrence beside a valued one adds nothing rather than colliding."""
        cfg = loader.load(WithList, argv=["--tags", "x", "--tags"], env={})
        assert cfg.tags == ["x"]

    def test_bare_then_valued_keeps_the_value(self, loader: ConfargLoader) -> None:
        """Order does not matter: the bare occurrence contributes no item either way."""
        cfg = loader.load(WithList, argv=["--tags", "--tags", "x"], env={})
        assert cfg.tags == ["x"]

    def test_bare_twice_is_still_the_empty_list(self, loader: ConfargLoader) -> None:
        """Two bare occurrences clear the list once, rather than reading as a repeat."""
        cfg = loader.load(WithList, argv=["--tags", "--tags"], env={})
        assert cfg.tags == []

    def test_merged_dict_matches_vanilla(self, loader: ConfargLoader) -> None:
        """The raw merged dict records the clear identically in every front-end."""
        merged = loader.merge(WithList, argv=["--tags"], env={})
        assert merged == {"tags": []}

    def test_dashed_item_is_still_an_item(self, loader: ConfargLoader) -> None:
        """The filter asks vanilla's own flag/value split, so ``-8`` is an item, not nothing."""
        cfg = loader.load(_WithIntList, argv=["--input", "-8"], env={})
        assert cfg.input == -8

    def test_equals_escape_is_never_a_bare_occurrence(self, loader: ConfargLoader) -> None:
        """``--tags=--a`` carries its item by construction and is left alone."""
        cfg = loader.load(WithList, argv=["--tags=--a"], env={})
        assert cfg.tags == ["--a"]

    def test_equals_escape_beside_a_bare_occurrence(self, loader: ConfargLoader) -> None:
        """The ``=`` occurrence names ``tags=--a``, so the read-back must not overwrite its item."""
        cfg = loader.load(WithList, argv=["--tags=--a", "--tags"], env={})
        assert cfg.tags == ["--a"]

    def test_bare_flag_under_a_cli_prefix(self, loader: ConfargLoader) -> None:
        """The read-back reads the prefix-stripped argv, so ``--app.tags`` clears ``tags``."""
        cfg = loader.load(WithList, argv=["--app.tags"], env={}, cli_prefix="app")
        assert cfg.tags == []


# ---------------------------------------------------------------------------
# Fixed-length sequences: tuple and namedtuple spell alike
# ---------------------------------------------------------------------------


class TestFixedSequenceContract:
    """A namedtuple takes the CLI spellings a same-arity ``tuple`` takes, everywhere.

    A namedtuple is a fixed-length sequence, so every front-end consumes exactly its
    arity in positional tokens -- the same count a ``tuple[int, int]`` field consumes --
    and the per-field and per-index flags refine it
    (docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption).
    """

    def test_tuple_positional(self, loader: ConfargLoader) -> None:
        """--pair 13 42 fills a tuple[int, int] field."""
        assert loader.load(_WithIntPair, argv=["--pair", "13", "42"], env={}).pair == (13, 42)

    def test_namedtuple_positional(self, loader: ConfargLoader) -> None:
        """--pair 13 42 fills a namedtuple field the same way."""
        assert loader.load(_WithPoint, argv=["--pair", "13", "42"], env={}).pair == _Point(x=13, y=42)

    def test_tuple_positional_elements_are_coerced(self, loader: ConfargLoader) -> None:
        """A tuple's positional tokens reach the merged dict as their element types (BUG-59).

        Eager coercion is what makes a merged dict carry the same types whichever channel
        filled it, so ``merge()`` -- not the ``load()`` that ``build()`` rescues afterwards --
        is the contract under test.
        """
        assert loader.merge(_WithIntPair, argv=["--pair", "13", "42"], env={}) == {"pair": [13, 42]}

    def test_mixed_tuple_positional_elements_are_coerced_per_position(self, loader: ConfargLoader) -> None:
        """Each positional token is coerced by its own element type, not a shared one (BUG-59)."""
        assert loader.merge(_WithMixedPair, argv=["--pair", "13", "hi"], env={}) == {"pair": [13, "hi"]}

    def test_namedtuple_positional_elements_are_coerced(self, loader: ConfargLoader) -> None:
        """A namedtuple's positional tokens reach the merged dict as its field types (BUG-59)."""
        assert loader.merge(_WithPoint, argv=["--pair", "13", "42"], env={}) == {"pair": [13, 42]}

    def test_optional_namedtuple_positional(self, space_sep_loader: ConfargLoader) -> None:
        """Optionality does not change the spelling (10-design-decisions.md)."""
        assert space_sep_loader.load(_WithOptionalPoint, argv=["--pair", "13", "42"], env={}).pair == _Point(x=13, y=42)

    def test_optional_namedtuple_positional_repeated(self, loader: ConfargLoader) -> None:
        """The click idiom spells the same run one token per occurrence (BUG-79).

        Under Optional the field is a union with a sequence variant, so its flag is a
        multi-token one and joins the list-syntax divergence: click and typer take the
        repeated spelling, exactly as they already do for ``list[str] | None``.
        """
        assert loader.load(_WithOptionalPoint, argv=["--pair", "13", "--pair", "42"], env={}).pair == _Point(x=13, y=42)

    def test_namedtuple_field_flags(self, loader: ConfargLoader) -> None:
        """--pair.x / --pair.y address the fields by name."""
        cfg = loader.load(_WithPoint, argv=["--pair.x", "13", "--pair.y", "42"], env={})
        assert cfg.pair == _Point(x=13, y=42)

    def test_namedtuple_index_flags(self, loader: ConfargLoader) -> None:
        """--pair.0 / --pair.1 address the fields by position."""
        cfg = loader.load(_WithPoint, argv=["--pair.0", "13", "--pair.1", "42"], env={})
        assert cfg.pair == _Point(x=13, y=42)

    def test_namedtuple_negative_index_flag(self, loader: ConfargLoader) -> None:
        """--pair.-1 addresses the last field, as --lang.-1 does on a fixed tuple (BUG-80)."""
        cfg = loader.load(_WithDefPoint, argv=["--pair.-1", "42"], env={})
        assert cfg.pair == _DefPoint(x=0, y=42)

    def test_namedtuple_negative_index_beside_positive(self, loader: ConfargLoader) -> None:
        """--pair.0 beside --pair.-1 is the all-index form ``build()`` already takes (BUG-80)."""
        cfg = loader.load(_WithDefPoint, argv=["--pair.0", "1", "--pair.-1", "42"], env={})
        assert cfg.pair == _DefPoint(x=1, y=42)

    def test_namedtuple_negative_index_merge_is_stored_as_spelled(self, loader: ConfargLoader) -> None:
        """The negative spelling reaches the merged dict as spelled, exactly as vanilla's (BUG-80).

        Vanilla's type walk takes the segment and stores it as spelled; the merged dicts must
        stay byte-identical, with ``build()`` owning the index resolution against the arity.
        """
        assert loader.merge(_WithDefPoint, argv=["--pair.-1", "42"], env={}) == {"pair": {"-1": 42}}

    def test_namedtuple_negative_index_out_of_range(self, loader: ConfargLoader) -> None:
        """An index past the arity is refused at parse, in each front-end's own voice (BUG-80).

        The type walk only passes in-range segments, positive and negative alike, so no
        registration ever carries ``--pair.-3``: vanilla names it an unknown argument and
        the adapters answer with their own usage error.
        """
        with pytest.raises((ConfargError, SystemExit)):
            loader.load(_WithDefPoint, argv=["--pair.-3", "1"], env={})

    def test_namedtuple_deep_field_negative_index(self, loader: ConfargLoader) -> None:
        """A negative index below a struct-shaped field spells under the name and index alike (BUG-80).

        The same two spellings a deep field's own flags take
        (``--pt.inner.*``, ``--pt.0.*``), plus the negative index of the field itself:
        ``--pt.inner.-1`` and ``--pt.0.-1`` both reach ``_Inner``'s last field.
        """
        cfg = loader.load(_WithNestedPoint, argv=["--pt.inner.-1", "hi"], env={})
        assert cfg.pt.inner == _Inner(a=0, b="hi")
        cfg = loader.load(_WithNestedPoint, argv=["--pt.0.-1", "hi"], env={})
        assert cfg.pt.inner == _Inner(a=0, b="hi")

    def test_tuple_whole_value(self, whole_value_arity_loader: ConfargLoader) -> None:
        """--pair '[13, 42]' fills a tuple[int, int] in one token (click declines it)."""
        cfg = whole_value_arity_loader.load(_WithIntPair, argv=["--pair", "[13, 42]"], env={})
        assert cfg.pair == (13, 42)

    def test_namedtuple_whole_value_object(self, whole_value_arity_loader: ConfargLoader) -> None:
        """--pair '{"x": 13, "y": 42}' fills a namedtuple by field name in one token."""
        cfg = whole_value_arity_loader.load(_WithPoint, argv=["--pair", '{"x": 13, "y": 42}'], env={})
        assert cfg.pair == _Point(x=13, y=42)

    def test_namedtuple_whole_value_array(self, whole_value_arity_loader: ConfargLoader) -> None:
        """--pair '[13, 42]' fills a namedtuple positionally, as the same-arity tuple does."""
        cfg = whole_value_arity_loader.load(_WithPoint, argv=["--pair", "[13, 42]"], env={})
        assert cfg.pair == _Point(x=13, y=42)

    def test_optional_namedtuple_whole_value(self, loader: ConfargLoader) -> None:
        """Optionality does not change what the whole value accepts (10-design-decisions.md).

        The optional spelling rides the union's multi-token registration, so the
        clicklike front-ends take the lone token too: their repeated-flag idiom holds
        the one token, and the collector decodes it exactly as vanilla does (BUG-79).
        """
        cfg = loader.load(_WithOptionalPoint, argv=["--pair", '{"x": 13, "y": 42}'], env={})
        assert cfg.pair == _Point(x=13, y=42)

    def test_optional_tuple_bare_flag_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """A bare --pair on tuple[int, int] | None is the union's missing value (BUG-61).

        To the vanilla parser the field is a union with a sequence variant and no
        varlen one, so the empty token run can build nothing. The adapters' collector
        routes the optional field through the same shaper instead of storing ``[]``,
        and the bare occurrence now stands bare, so the clicklike parsers drop it for
        the collector to refuse rather than exiting with their own error (BUG-79).
        """
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            loader.merge(_WithOptionalIntPair, argv=["--pair"], env={})

    def test_optional_namedtuple_bare_flag_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """A bare --pair on _Point | None is refused the same way (BUG-61)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            loader.merge(_WithOptionalPoint, argv=["--pair"], env={})

    def test_optional_tuple_token_run_is_stored_raw(self, space_sep_loader: ConfargLoader) -> None:
        """The union branch stores the run as raw tokens; build() judges the arity (BUG-61)."""
        assert space_sep_loader.merge(_WithOptionalIntPair, argv=["--pair", "13", "42"], env={}) == {
            "pair": ["13", "42"],
        }

    def test_optional_tuple_short_run_is_deferred_to_build(self, loader: ConfargLoader) -> None:
        """A one-token run stays a one-element list, an arity error build() owns (BUG-61, BUG-79).

        The plain spelling's count enforcement at the framework's own parse is the
        approved divergence; under Optional vanilla defers to build(), so the
        clicklike front-ends parse ``--pair 13`` and let ``build()`` refuse rather
        than exiting with their own usage error.
        """
        assert loader.merge(_WithOptionalIntPair, argv=["--pair", "13"], env={}) == {"pair": ["13"]}
        with pytest.raises(TypeCoercionError, match="Cannot coerce"):
            loader.load(_WithOptionalIntPair, argv=["--pair", "13"], env={})

    def test_optional_namedtuple_token_run_is_stored_raw(self, space_sep_loader: ConfargLoader) -> None:
        """The optional spelling keeps the run raw, coercing nothing per position (BUG-61)."""
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", "13", "42"], env={}) == {"pair": ["13", "42"]}

    def test_optional_namedtuple_field_flags_alone(self, loader: ConfargLoader) -> None:
        """A sub-flag under Optional still writes its own field, coerced (BUG-61)."""
        assert loader.merge(_WithOptionalPoint, argv=["--pair.x", "13", "--pair.y", "42"], env={}) == {
            "pair": {"x": 13, "y": 42},
        }

    def test_optional_namedtuple_arity_then_sub_flag_rides_the_star_shape(
        self,
        space_sep_loader: ConfargLoader,
    ) -> None:
        """A sub-flag after the arity flag descends into the raw run, '*' shape and all (BUG-61).

        The optional spelling is a union to vanilla too, so its positional promotion
        is the generic ``_set_nested`` one -- the list-op ``'*'`` base -- and not the
        by-field-name re-keying a plain namedtuple's positions get (BUG-66). Both
        sides store the same dict, and both refuse to build it.
        """
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", "1", "2", "--pair.y", "9"], env={}) == {
            "pair": {"*": ["1", "2"], "y": 9},
        }
        with pytest.raises(TypeCoercionError, match="Cannot coerce"):
            space_sep_loader.load(_WithOptionalPoint, argv=["--pair", "1", "2", "--pair.y", "9"], env={})

    def test_optional_namedtuple_sub_flag_then_arity_replaces_wholesale(self, space_sep_loader: ConfargLoader) -> None:
        """The arity flag typed last replaces the field wholesale, as on the plain spelling (BUG-61)."""
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair.y", "9", "--pair", "13", "42"], env={}) == {
            "pair": ["13", "42"],
        }
        assert space_sep_loader.load(
            _WithOptionalPoint,
            argv=["--pair.y", "9", "--pair", "13", "42"],
            env={},
        ).pair == _Point(
            x=13,
            y=42,
        )

    def test_optional_tuple_whole_value_array(self, loader: ConfargLoader) -> None:
        """The lone JSON array still decodes under Optional, on every front-end (BUG-61, BUG-79)."""
        assert loader.merge(_WithOptionalIntPair, argv=["--pair", "[13, 42]"], env={}) == {
            "pair": [13, 42],
        }

    def test_optional_namedtuple_whole_value_object_merge(self, loader: ConfargLoader) -> None:
        """The whole-value object blob still decodes under Optional (BUG-61)."""
        assert loader.merge(
            _WithOptionalPoint,
            argv=["--pair", '{"x": 13, "y": 42}'],
            env={},
        ) == {"pair": {"x": 13, "y": 42}}

    def test_optional_tuple_repeated_occurrences_accumulate(self, loader: ConfargLoader) -> None:
        """--pair 1 --pair 2 joins the runs, as every multi-token flag does (BUG-79).

        The resolved union consumes greedily in vanilla, so a repeated occurrence is a
        second spelling of one run of tokens, not a competitor: the adapters kept only
        the last occurrence's tokens and built ``(2,)``'s arity error where vanilla
        builds ``(1, 2)``.
        """
        assert loader.merge(_WithOptionalIntPair, argv=["--pair", "1", "--pair", "2"], env={}) == {"pair": ["1", "2"]}
        assert loader.load(_WithOptionalIntPair, argv=["--pair", "1", "--pair", "2"], env={}).pair == (1, 2)

    def test_optional_tuple_repeated_space_runs_join(self, space_sep_loader: ConfargLoader) -> None:
        """--pair 1 2 --pair 3 4 is one four-token run, an arity error build() owns (BUG-79)."""
        assert space_sep_loader.merge(_WithOptionalIntPair, argv=["--pair", "1", "2", "--pair", "3", "4"], env={}) == {
            "pair": ["1", "2", "3", "4"],
        }
        with pytest.raises(TypeCoercionError, match="Cannot coerce"):
            space_sep_loader.load(_WithOptionalIntPair, argv=["--pair", "1", "2", "--pair", "3", "4"], env={})

    def test_optional_namedtuple_repeated_occurrences_accumulate(self, loader: ConfargLoader) -> None:
        """A namedtuple's arity flag accumulates under Optional too, not last-wins (BUG-79)."""
        assert loader.merge(_WithOptionalPoint, argv=["--pair", "1", "--pair", "2"], env={}) == {"pair": ["1", "2"]}
        assert loader.load(_WithOptionalPoint, argv=["--pair", "1", "--pair", "2"], env={}).pair == _Point(x=1, y=2)

    def test_optional_namedtuple_repeated_space_runs_join(self, space_sep_loader: ConfargLoader) -> None:
        """The space-run form of the same join, refused by build() on every front-end (BUG-79)."""
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", "1", "2", "--pair", "3", "4"], env={}) == {
            "pair": ["1", "2", "3", "4"],
        }
        with pytest.raises(TypeCoercionError, match="Cannot coerce"):
            space_sep_loader.load(_WithOptionalPoint, argv=["--pair", "1", "2", "--pair", "3", "4"], env={})

    def test_optional_tuple_leading_bare_occurrence_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """--pair --pair 3 meets the shaper with the still-empty run at the first occurrence (BUG-79).

        Vanilla shapes the accumulation at every occurrence, so the leading bare
        occurrence is refused before the valued one is ever read; the adapters kept
        only the surviving run and answered as though the bare occurrence had not
        happened. The bare occurrence stands bare, so the clicklike parsers drop it
        and the collector reads the order off the argv the user typed.
        """
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            loader.merge(_WithOptionalIntPair, argv=["--pair", "--pair", "3"], env={})

    def test_optional_tuple_leading_bare_beside_a_space_run(self, space_sep_loader: ConfargLoader) -> None:
        """The space-run form of the same leading-bare refusal (BUG-79)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            space_sep_loader.merge(_WithOptionalIntPair, argv=["--pair", "--pair", "3", "4"], env={})

    def test_optional_tuple_trailing_bare_occurrence_keeps_the_run(self, loader: ConfargLoader) -> None:
        """--pair 1 --pair 2 --pair keeps the run: a non-empty accumulation makes the bare occurrence a no-op (BUG-79).

        A bare occurrence joins whatever the earlier occurrences accumulated, so once
        the run is non-empty it adds nothing rather than colliding with it.
        """
        assert loader.merge(_WithOptionalIntPair, argv=["--pair", "1", "--pair", "2", "--pair"], env={}) == {
            "pair": ["1", "2"],
        }

    def test_optional_tuple_trailing_bare_after_a_space_run(self, space_sep_loader: ConfargLoader) -> None:
        """--pair 1 2 --pair is accepted, the space-run form of the same trailing bare (BUG-79)."""
        assert space_sep_loader.merge(_WithOptionalIntPair, argv=["--pair", "1", "2", "--pair"], env={}) == {
            "pair": ["1", "2"],
        }

    def test_optional_namedtuple_leading_bare_occurrence_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """A namedtuple's arity flag under Optional refuses its leading bare occurrence too (BUG-79)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            loader.merge(_WithOptionalPoint, argv=["--pair", "--pair", "3"], env={})

    def test_optional_namedtuple_trailing_bare_occurrence_keeps_the_run(self, loader: ConfargLoader) -> None:
        """A trailing bare occurrence on a namedtuple's arity flag adds nothing (BUG-79)."""
        assert loader.merge(_WithOptionalPoint, argv=["--pair", "1", "--pair", "2", "--pair"], env={}) == {
            "pair": ["1", "2"],
        }

    def test_optional_namedtuple_blob_never_joins_the_token_accumulation(self, space_sep_loader: ConfargLoader) -> None:
        """--pair '{"x": 13}' --pair 1 2 leaves the run, and --pair 1 2 --pair '{"x": 13}' the blob (BUG-79).

        A whole-value blob is its own write in vanilla; it never enters the token
        accumulation. With the runs joined, only the argv order says which occurrence
        wrote last.
        """
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", '{"x": 13}', "--pair", "1", "2"], env={}) == {
            "pair": ["1", "2"],
        }
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", "1", "2", "--pair", '{"x": 13}'], env={}) == {
            "pair": {"x": 13},
        }

    def test_optional_namedtuple_blob_then_bare_occurrence_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """A bare occurrence after a blob meets an empty accumulation, blob or no blob (BUG-79)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            loader.merge(_WithOptionalPoint, argv=["--pair", '{"x": 13}', "--pair"], env={})

    def test_optional_namedtuple_blob_beside_a_surplus_token_raises(self, space_sep_loader: ConfargLoader) -> None:
        """A blob is one token, so the one after it is the stray positional vanilla names (BUG-79).

        The upper bound the plain spelling's guard already spells
        (``test_namedtuple_whole_value_beside_a_surplus_token_raises``); under Optional
        the adapters stored both tokens as an ordinary run instead.
        """
        with pytest.raises(UnknownArgumentError, match=re.escape("Unexpected positional argument: '9'")):
            space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", '{"x": 1, "y": 2}', "9"], env={})

    def test_optional_tuple_delete_then_bare_occurrence_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """The whole-field delete ends the accumulation, so the bare occurrence after it is empty (BUG-79)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            loader.merge(_WithOptionalIntPair, argv=["--pair", "1", "--pair", "2", "--pair-", "--pair"], env={})

    def test_optional_tuple_delete_then_run_starts_over(self, loader: ConfargLoader) -> None:
        """Only the tokens after the delete reach the value, on every front-end (BUG-79)."""
        assert loader.merge(
            _WithOptionalIntPair,
            argv=["--pair", "1", "--pair", "2", "--pair-", "--pair", "5", "--pair", "6"],
            env={},
        ) == {"pair": ["5", "6"]}

    def test_whole_value_refined_by_field_flag(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A sibling --pair.y refines the whole value, as it does for a struct field."""
        cfg = whole_value_arity_loader.load(
            _WithPoint,
            argv=["--pair", '{"x": 13, "y": 42}', "--pair.y", "7"],
            env={},
        )
        assert cfg.pair == _Point(x=13, y=7)

    def test_namedtuple_arity_then_sub_flag_merges_by_field_name(self, loader: ConfargLoader) -> None:
        """A sub-flag after the arity flag rides on its positions, keyed by field name (BUG-66).

        The latest arguments overwrite earlier ones, per path: a sub-flag writes at
        ``pair.y``, so it joins the arity flag's positional value instead of replacing
        it -- and the positions it did not take keep their field names, the shape
        ``build()`` reads, rather than vanilla's former list-op ``'*'`` base, which a
        namedtuple cannot build.
        """
        assert loader.merge(_WithPoint, argv=["--pair", "13", "42", "--pair.y", "7"], env={}) == {
            "pair": {"x": 13, "y": 7},
        }

    def test_namedtuple_sub_flag_then_arity_flag_replaces_wholesale(self, loader: ConfargLoader) -> None:
        """An arity flag after every sub-flag overwrites the field, as any later write does (BUG-66).

        The adapters used to merge the two halves order-independently, so a
        ``--pair.y`` the later ``--pair`` had already overwritten came back.
        """
        assert loader.merge(_WithPoint, argv=["--pair.y", "7", "--pair", "13", "42"], env={}) == {"pair": [13, 42]}

    def test_namedtuple_sub_flag_then_whole_value_replaces(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A whole value after a sub-flag overwrites the field the same way (BUG-66)."""
        assert whole_value_arity_loader.merge(
            _WithPoint,
            argv=["--pair.y", "7", "--pair", '{"x": 13, "y": 42}'],
            env={},
        ) == {"pair": {"x": 13, "y": 42}}

    def test_namedtuple_sub_flag_value_is_coerced(self, loader: ConfargLoader) -> None:
        """A sub-flag's token reaches the merged dict as its field type (BUG-66).

        Eager coercion is what lets an expression read the value: a raw token made
        ``${pair.y * 2}`` evaluate to ``'99'`` on the adapters while vanilla said 18.
        """
        assert loader.merge(_WithPoint, argv=["--pair.y", "7"], env={}) == {"pair": {"y": 7}}

    def test_namedtuple_sub_flag_feeds_expressions(self, loader: ConfargLoader) -> None:
        """The coerced sub-flag value is what a ``${...}`` over it sees (BUG-66)."""
        cfg = loader.load(
            _PointScale,
            argv=["--pair.x", "1", "--pair.y", "9", "--scale", "${pair.y * 2}"],
            env={},
        )
        assert cfg.pair == _Point(x=1, y=9)
        assert cfg.scale == 18

    def test_namedtuple_index_sub_flags_stay_index_keys(self, loader: ConfargLoader) -> None:
        """An index sub-flag keeps the key the user spelled, as vanilla does (BUG-65).

        The collector re-keyed ``--pair.0`` to ``x``, a collection-time priority
        vanilla never makes: construction reconciles index keys itself, and the
        re-keyed dict could not match vanilla's key for key.
        """
        assert loader.merge(_WithPoint, argv=["--pair.0", "13", "--pair.1", "42"], env={}) == {
            "pair": {"0": 13, "1": 42},
        }
        assert loader.load(_WithPoint, argv=["--pair.0", "13", "--pair.1", "42"], env={}).pair == _Point(13, 42)

    def test_namedtuple_index_sub_flag_beside_a_name_keeps_both(self, loader: ConfargLoader) -> None:
        """A ``--pair.0`` beside ``--pair.x`` is not dropped, and both refuse alike (BUG-65).

        The re-keying made the index flag vanish under the name flag on the
        adapters, while vanilla stores both keys and lets ``build()`` refuse the
        mixed spelling.
        """
        assert loader.merge(_WithPoint, argv=["--pair.x", "13", "--pair.0", "9"], env={}) == {
            "pair": {"x": 13, "0": 9},
        }
        with pytest.raises(TypeCoercionError, match=re.escape("Unknown field(s) ['0'] for _Point")):
            loader.load(_WithPoint, argv=["--pair.x", "13", "--pair.0", "9"], env={})

    def test_namedtuple_arity_then_index_sub_flag_keeps_both(self, loader: ConfargLoader) -> None:
        """An index sub-flag after the arity flag rides the positions as its own key (BUG-65).

        The positional base is re-keyed by field name, as vanilla's promotion does,
        and the index sub-flag keeps its index key on top of it — the dict
        ``build()`` refuses on both sides, not the ``x`` overwrite the re-keying
        invented.
        """
        assert loader.merge(_WithPoint, argv=["--pair", "1", "2", "--pair.0", "9"], env={}) == {
            "pair": {"x": 1, "y": 2, "0": 9},
        }
        with pytest.raises(TypeCoercionError, match=re.escape("Unknown field(s) ['0'] for _Point")):
            loader.load(_WithPoint, argv=["--pair", "1", "2", "--pair.0", "9"], env={})

    def test_optional_namedtuple_index_sub_flag_stays_index_key(self, loader: ConfargLoader) -> None:
        """An index sub-flag under Optional keeps its key too (BUG-65)."""
        assert loader.merge(_WithOptionalPoint, argv=["--pair.0", "13"], env={}) == {"pair": {"0": 13}}
        assert loader.load(_WithOptionalPoint, argv=["--pair.0", "13", "--pair.1", "42"], env={}).pair == _Point(13, 42)

    def test_optional_namedtuple_arity_then_index_sub_flag_keeps_both(self, space_sep_loader: ConfargLoader) -> None:
        """The union shape keeps the index key beside the ``'*'`` base, as vanilla does (BUG-65)."""
        assert space_sep_loader.merge(_WithOptionalPoint, argv=["--pair", "1", "2", "--pair.0", "9"], env={}) == {
            "pair": {"*": ["1", "2"], "0": 9},
        }

    def test_namedtuple_deep_sub_flag_below_a_namedtuple_field(self, loader: ConfargLoader) -> None:
        """--pt.inner.a reaches a namedtuple field of a namedtuple, as vanilla does (BUG-68).

        The adapters registered and collected a namedtuple's sub-flags one level
        deep only, so a path through a struct-shaped field was refused by the host
        framework's own parser while vanilla resolved it.
        """
        assert loader.merge(_WithNestedPoint, argv=["--pt.inner.a", "5"], env={}) == {"pt": {"inner": {"a": 5}}}

    def test_namedtuple_deep_sub_flag_below_a_struct_field(self, loader: ConfargLoader) -> None:
        """A struct field of a namedtuple takes the same deep path (BUG-68)."""
        assert loader.merge(_WithStructFieldPoint, argv=["--pt.inner.a", "5"], env={}) == {"pt": {"inner": {"a": 5}}}

    def test_namedtuple_deep_sub_flag_by_index(self, loader: ConfargLoader) -> None:
        """The index spelling descends a level too, keeping its own key (BUG-68)."""
        assert loader.merge(_WithNestedPoint, argv=["--pt.0.a", "5"], env={}) == {"pt": {"0": {"a": 5}}}

    def test_namedtuple_deep_sub_flags_keep_their_spelled_keys(self, loader: ConfargLoader) -> None:
        """Name and index spellings each keep their own key one level deeper (BUG-68)."""
        assert loader.merge(_WithNestedPoint, argv=["--pt.0.a", "5", "--pt.inner.b", "y"], env={}) == {
            "pt": {"0": {"a": 5}, "inner": {"b": "y"}},
        }

    def test_namedtuple_deep_sub_flag_builds(self, loader: ConfargLoader) -> None:
        """The collected deep dict is one construction reconciles, as vanilla's is (BUG-68)."""
        assert loader.load(_WithNestedPoint, argv=["--pt.inner.a", "5"], env={}).pt == _PtNested(
            inner=_Inner(a=5),
            x=0,
        )

    def test_namedtuple_struct_field_whole_value_object_decodes(self, loader: ConfargLoader) -> None:
        """A whole-value token on the namedtuple's struct field decodes (BUG-68).

        The collector used to coerce the token as a scalar leaf, so the blob reached
        the merged dict as a raw string where vanilla had the object it spells.
        """
        assert loader.merge(_WithStructFieldPoint, argv=["--pt.inner", '{"a": 7}'], env={}) == {
            "pt": {"inner": {"a": 7}},
        }

    def test_namedtuple_optional_struct_field_whole_value_object_decodes(self, loader: ConfargLoader) -> None:
        """The Optional spelling of the struct field decodes the same blob (BUG-68)."""
        assert loader.merge(_WithOptionalStructFieldPoint, argv=["--pt.inner", '{"a": 7}'], env={}) == {
            "pt": {"inner": {"a": 7}},
        }

    def test_namedtuple_optional_namedtuple_field_whole_value_object_decodes(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A whole-value token on the Optional namedtuple field decodes (BUG-68).

        The field is a union with a sequence variant, so the whole-value token
        keeps the clicklike front-ends' own list syntax (list-syntax-divergence.md).
        """
        assert whole_value_arity_loader.merge(_WithNestedPoint, argv=["--pt.inner", '{"a": 7}'], env={}) == {
            "pt": {"inner": {"a": 7}},
        }

    def test_namedtuple_deep_whole_value_object_decodes(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A whole-value token on the plain namedtuple's field decodes (BUG-68)."""
        assert whole_value_arity_loader.merge(
            _WithPlainNestedPoint,
            argv=["--pt.inner", '{"a": 1, "b": "z"}'],
            env={},
        ) == {"pt": {"inner": {"a": 1, "b": "z"}}}

    def test_namedtuple_arity_then_deep_sub_flag_merges(self, loader: ConfargLoader) -> None:
        """A deep sub-flag after the arity flag descends into the positions it left (BUG-68).

        The same priority one level up applies: the arity value is re-keyed by field
        name and the sub-flag replaces the key it names, here with the dict the
        deeper level collected.
        """
        assert loader.merge(_WithNestedPoint, argv=["--pt", "1", "2", "--pt.inner.b", "y"], env={}) == {
            "pt": {"inner": {"b": "y"}, "x": 2},
        }

    def test_namedtuple_deep_sub_flag_then_arity_replaces_wholesale(self, loader: ConfargLoader) -> None:
        """The arity flag typed after every deep sub-flag takes the whole field (BUG-68)."""
        assert loader.merge(_WithNestedPoint, argv=["--pt.inner.b", "y", "--pt", "1", "2"], env={}) == {"pt": ["1", 2]}

    def test_namedtuple_deep_arity_then_deep_sub_flag_merges(self, loader: ConfargLoader) -> None:
        """The same priority holds at the deeper level, on the field's own arity flag (BUG-68)."""
        assert loader.merge(_WithPlainNestedPoint, argv=["--pt.inner", "7", "8", "--pt.inner.a", "5"], env={}) == {
            "pt": {"inner": {"a": 5, "b": "8"}},
        }

    def test_namedtuple_deep_sub_flag_then_deep_arity_replaces(self, loader: ConfargLoader) -> None:
        """A deep arity flag after its own sub-flags replaces the field wholesale (BUG-68)."""
        assert loader.merge(_WithPlainNestedPoint, argv=["--pt.inner.a", "5", "--pt.inner", "7", "8"], env={}) == {
            "pt": {"inner": [7, "8"]},
        }

    def test_repeated_flag_last_occurrence_wins(self, loader: ConfargLoader) -> None:
        """A fixed-arity flag takes one value, so a repeat replaces it (BUG-62).

        ``FlagSpec.accumulates`` is False on a fixed-arity flag: vanilla's
        ``_consume_fixed_tuple_args`` ``_set_nested``s the second occurrence over
        the first, and the frameworks that keep one value per flag overwrite too.
        """
        assert loader.merge(_WithIntPair, argv=["--pair", "1", "2", "--pair", "3", "4"], env={}) == {"pair": [3, 4]}

    def test_repeated_whole_value_last_occurrence_wins(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A repeated whole-value token replaces the earlier one too (BUG-62)."""
        assert whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "[1, 2]", "--pair", "[3, 4]"], env={}) == {
            "pair": [3, 4],
        }

    def test_repeated_whole_value_then_positional_last_occurrence_wins(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """The two spellings of one flag are occurrences of the same flag (BUG-62)."""
        assert whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "[1, 2]", "--pair", "3", "4"], env={}) == {
            "pair": [3, 4],
        }

    def test_repeated_namedtuple_flag_last_occurrence_wins(self, loader: ConfargLoader) -> None:
        """A namedtuple's arity flag replaces on a repeat, as the same-arity tuple does (BUG-62)."""
        assert loader.load(_WithPoint, argv=["--pair", "1", "2", "--pair", "3", "4"], env={}).pair == _Point(x=3, y=4)

    def test_repeated_namedtuple_whole_value_last_occurrence_wins(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A repeated object whole value replaces the earlier one too (BUG-62)."""
        assert whole_value_arity_loader.merge(
            _WithPoint,
            argv=["--pair", '{"x": 1, "y": 2}', "--pair", '{"x": 13, "y": 42}'],
            env={},
        ) == {"pair": {"x": 13, "y": 42}}

    def test_repeated_flag_after_sub_flag_replaces_wholesale(self, loader: ConfargLoader) -> None:
        """The last occurrence is also the latest writer, so it takes the whole field (BUG-62).

        The repeat rides the read-back ``_arity_flag_writes_last`` already performs: the
        last ``--pair`` follows the ``--pair.y`` it supersedes, exactly as a lone arity
        flag does (BUG-66).
        """
        assert loader.merge(_WithPoint, argv=["--pair", "1", "2", "--pair.y", "7", "--pair", "3", "4"], env={}) == {
            "pair": [3, 4],
        }

    def test_repeated_short_first_occurrence_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """An earlier occurrence's short run is refused, not silently overwritten (BUG-73).

        Vanilla refuses the incomplete occurrence the moment it meets it, so ``--pair 1
        --pair 3 4`` never reaches the second occurrence. A greedy registration keeps
        only the last occurrence's run, so every occurrence's run is read back off
        argv, as the latest-writer question already is (BUG-66).
        """
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "1", "--pair", "3", "4"], env={})

    def test_repeated_short_first_occurrence_on_a_namedtuple_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A namedtuple is a fixed-length sequence, so its earlier short run vanishes the same way (BUG-73)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", "1", "--pair", "3", "4"], env={})

    def test_repeated_equals_spelled_short_first_occurrence_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """The ``--pair=1`` spelling opens its occurrence's run, which the next flag ends short (BUG-73)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair=1", "--pair", "3", "4"], env={})

    def test_repeated_bare_first_occurrence_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A bare occurrence beside a valued one is the same short run (BUG-73, BUG-74).

        Argparse answers through the guard's argv read-back; cyclopts asserts inside
        its own parse on this argv, so there the refusal runs before the parse, as the
        ``--config`` scan already does (BUG-51). The clicklike front-ends refuse the
        bare form through their exact-count parsers.
        """
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "--pair", "3", "4"], env={})

    def test_repeated_bare_last_occurrence_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A trailing bare occurrence is refused as well, so both orders answer alike (BUG-74)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "1", "2", "--pair"], env={})

    def test_repeated_bare_occurrence_on_a_namedtuple_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A namedtuple's arity flag is a fixed-arity flag, bare occurrence and all (BUG-74)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", "--pair", "3", "4"], env={})
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", "1", "2", "--pair"], env={})

    def test_click_refuses_the_short_first_occurrence_in_its_own_parser(self) -> None:
        """Click registers the exact count, so the short first occurrence never lands (BUG-73).

        The same approved divergence as the whole-value token
        (10-design-decisions.md#a-divergence-leans-towards-the-affected-backends-own-idiom):
        click's refusal is its own usage error rather than confarg's, and typer
        inherits it along with the option class it forked.
        """
        with pytest.raises(SystemExit):
            ClickLoader().merge(_WithIntPair, argv=["--pair", "1", "--pair", "3", "4"], env={})

    def test_tuple_too_many_tokens_raises(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A token past the arity is the surplus positional vanilla names, not a longer tuple.

        The upper bound of the token run, mirroring
        ``test_tuple_short_token_run_is_a_missing_value`` at the other end: it is a
        parse-time refusal naming the first token past the arity, so ``merge()`` already
        raises and ``build()`` never sees the over-long list (BUG-60).
        """
        with pytest.raises(ConfargError, match=re.escape("Unexpected positional argument: '3'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "1", "2", "3"], env={})

    def test_namedtuple_too_many_tokens_raises(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A namedtuple is a fixed-length sequence, so it refuses the surplus token too (BUG-60)."""
        with pytest.raises(ConfargError, match=re.escape("Unexpected positional argument: '3'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", "1", "2", "3"], env={})

    def test_tuple_whole_value_beside_a_surplus_token_raises(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A whole value consumes one token, so the second one is already surplus (BUG-60).

        ``--pair '[13]' 9`` is the whole-value spelling of the same over-fill: the lone
        array is the value, short arity and all, and ``9`` is the stray positional --
        never the token that completes it.
        """
        with pytest.raises(ConfargError, match=re.escape("Unexpected positional argument: '9'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "[13]", "9"], env={})

    def test_namedtuple_whole_value_beside_a_surplus_token_raises(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """The object spelling of a whole value is one token too (BUG-60)."""
        with pytest.raises(ConfargError, match=re.escape("Unexpected positional argument: '9'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", '{"x": 1, "y": 2}', "9"], env={})

    def test_tuple_too_few_tokens_raises(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A short whole value is rejected by build(), not by the framework.

        The counterpart of ``test_tuple_short_token_run_is_a_missing_value``: one token
        that *spells* the whole value is not a short token run, so it is an arity error
        and not a missing value, whichever front-end read it.
        """
        with pytest.raises(ConfargError, match="expected 2 elements, got 1"):
            whole_value_arity_loader.load(_WithIntPair, argv=["--pair", "[13]"], env={})

    def test_tuple_short_token_run_is_a_missing_value(self, whole_value_arity_loader: ConfargLoader) -> None:
        """--pair 1 is a missing value everywhere, not a one-element tuple (BUG-58)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair", "1"], env={})

    def test_tuple_bare_flag_is_a_missing_value(self, whole_value_arity_loader: ConfargLoader) -> None:
        """A fixed arity is not a shape a bare flag is reserved for (BUG-58)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithIntPair, argv=["--pair"], env={})

    def test_namedtuple_short_token_run_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A namedtuple is a fixed-length sequence, so it needs every token too (BUG-58)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", "1"], env={})

    def test_namedtuple_short_token_run_beside_a_field_flag_is_a_missing_value(
        self,
        whole_value_arity_loader: ConfargLoader,
    ) -> None:
        """A sibling --pair.y refines the arity flag; it does not excuse its short run (BUG-58)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pair'")):
            whole_value_arity_loader.merge(_WithPoint, argv=["--pair", "1", "--pair.y", "5"], env={})

    def test_click_declines_the_whole_value_token(self) -> None:
        """Click registers the exact token count, so it rejects the whole-value token.

        The approved divergence (09-invariants.md#cross-channel-parity): click's options
        cannot take a variable token count, and ``multiple=True`` -- its only alternative --
        would cost click users ``--pair 13 42``, the spelling a CLI user expects
        (10-design-decisions.md#a-divergence-leans-towards-the-affected-backends-own-idiom).
        """
        with pytest.raises(SystemExit):
            ClickLoader().load(_WithIntPair, argv=["--pair", "[13, 42]"], env={})


# ---------------------------------------------------------------------------
# The `=`-spelled run continued by bare tokens -- argparse alone declines it
# ---------------------------------------------------------------------------


class TestEqualsSpelledRunContinuation:
    """The value half of ``--flag=value`` opens its occurrence's run; bare tokens complete it (BUG-75)."""

    def test_fixed_arity_run_completed_by_bare_tokens(self) -> None:
        """``--pair=1 2`` is ``[1, 2]`` on every front-end but argparse, the namedtuple's flag too."""
        for loader in (VanillaLoader(), ClickLoader(), TyperLoader(), CycloptsLoader()):
            assert loader.merge(_WithIntPair, argv=["--pair=1", "2"], env={}) == {"pair": [1, 2]}
            assert loader.merge(_WithPoint, argv=["--pair=1", "2"], env={}) == {"pair": [1, 2]}

    def test_argparse_declines_the_continued_run(self) -> None:
        """Argparse has no spelling for continuing an ``=``-spelled run, so its parser exits.

        The approved divergence (docs-dev/architecture/invariants.md#cross-channel-parity):
        the ``=`` half binds exactly the text after it, the tokens that would complete the
        run are unrecognized arguments, and argparse exits with its own usage error --
        its native behavior kept, so confarg's arguments blend with the host application's
        own. The decline is every multi-token flag's: a fixed-arity flag and a varlen list
        alike, the config flag included below.
        """
        with pytest.raises(SystemExit):
            ArgparseLoader().merge(_WithIntPair, argv=["--pair=1", "2"], env={})
        with pytest.raises(SystemExit):
            ArgparseLoader().merge(WithList, argv=["--tags=a", "b"], env={})

    def test_argparse_declines_the_continued_config_run(self, tmp_yaml) -> None:
        """``--config=base.yaml extra.yaml`` exits on argparse, where the space form reads both."""
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        with pytest.raises(SystemExit):
            ArgparseLoader().merge(Simple, argv=[f"--config={base}", "extra.yaml"], env={})

    def test_varlen_run_completed_by_bare_tokens(self) -> None:
        """``--tags=a b`` is ``['a', 'b']`` where the space form is taken: vanilla and cyclopts.

        The clicklike front-ends decline the space form itself (list syntax divergence);
        argparse declines only the ``=`` opener (above).
        """
        for loader in (VanillaLoader(), CycloptsLoader()):
            assert loader.merge(WithList, argv=["--tags=a", "b"], env={}) == {"tags": ["a", "b"]}

    def test_config_run_completed_by_bare_tokens(self, tmp_yaml) -> None:
        """``--config=base.yaml override.yaml`` reads both files where the space form is taken."""
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        override = tmp_yaml("port: 2000\n", filename="override.yaml")
        for loader in (VanillaLoader(), CycloptsLoader()):
            assert loader.merge(Simple, argv=[f"--config={base}", str(override)], env={}) == {
                "host": "base",
                "port": 2000,
            }


# ---------------------------------------------------------------------------
# The config flag's space-separated multi-file run -- the clicklike front-ends decline it
# ---------------------------------------------------------------------------


class TestSpaceSeparatedConfigRun:
    """``--config base.yaml override.yaml`` reads both files where the space run is taken (BUG-99)."""

    def test_space_separated_config_files_merged(self, space_sep_loader: ConfargLoader, tmp_yaml) -> None:
        """``--config base.yaml override.yaml`` merges both files on the space-taking front-ends."""
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        override = tmp_yaml("port: 2000\n", filename="override.yaml")
        assert space_sep_loader.merge(Simple, argv=["--config", str(base), str(override)], env={}) == {
            "host": "base",
            "port": 2000,
        }

    def test_space_separated_subkey_config_files_merged(self, space_sep_loader: ConfargLoader, tmp_yaml) -> None:
        """The scoped ``--config.db base.yaml override.yaml`` run declines the same way (BUG-99)."""
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        override = tmp_yaml("port: 2000\n", filename="override.yaml")
        assert space_sep_loader.merge(AppConfig, argv=["--config.db", str(base), str(override)], env={}) == {
            "db": {"host": "base", "port": 2000},
        }

    def test_clicklike_decline_the_space_separated_config_run(self, tmp_yaml) -> None:
        """The space-separated multi-file run exits on click and typer (BUG-99).

        The approved divergence (docs-dev/architecture/invariants.md#cross-channel-parity):
        a click Option cannot vary its token count, and ``multiple=True`` -- the only
        registration that takes every path -- binds exactly one per occurrence, so the
        repeated form is the clicklike front-ends' multi-file spelling
        (docs-dev/architecture/cli-parsing/config-file-flags.md#config-file-flags). That
        form parses on every front-end, pinned by
        ``TestPipelineParity::test_multiple_config_files_merged``.
        """
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        override = tmp_yaml("port: 2000\n", filename="override.yaml")
        for loader in (ClickLoader(), TyperLoader()):
            with pytest.raises(SystemExit):
                loader.merge(Simple, argv=["--config", str(base), str(override)], env={})
            with pytest.raises(SystemExit):
                loader.merge(AppConfig, argv=["--config.db", str(base), str(override)], env={})


# ---------------------------------------------------------------------------
# Bool convention
# ---------------------------------------------------------------------------


class TestBoolValueConvention:
    """The explicit --flag true/false convention holds in every integration."""

    def test_bool_explicit_true(self, loader: ConfargLoader) -> None:
        """--debug true sets a bool field to True."""
        assert loader.load(Nested, argv=["--debug", "true"], env={}).debug is True

    def test_bool_explicit_false(self, loader: ConfargLoader) -> None:
        """--debug false sets a bool field to False."""
        assert loader.load(Nested, argv=["--debug", "false"], env={}).debug is False

    def test_no_negative_flag_registered(self, populating_loader: ConfargLoader) -> None:
        """No --no-debug style negative flag is generated for bool fields."""
        flags = populating_loader.registered_flags(Nested, config_flag="")
        assert flags is not None
        assert "no-debug" not in flags
        assert "no_debug" not in flags


# ---------------------------------------------------------------------------
# Union stealing rule and cast overrides
# ---------------------------------------------------------------------------


class TestStealingContract:
    """Scalar-union stealing rule and .str/.int cast overrides."""

    def test_str_float_stealing(self, loader: ConfargLoader) -> None:
        """--input inf coerces to float for str | float (stealing rule)."""
        cfg = loader.load(_WithStrFloat, argv=["--input", "inf"], env={})
        assert math.isinf(cfg.input)
        assert type(cfg.input) is float

    def test_str_bool_stealing(self, loader: ConfargLoader) -> None:
        """--input yes coerces to True for str | bool (stealing rule)."""
        cfg = loader.load(_WithStrBool, argv=["--input", "yes"], env={})
        assert cfg.input is True

    def test_str_override(self, loader: ConfargLoader) -> None:
        """--input.str yes preserves 'yes' as str, bypassing bool stealing."""
        cfg = loader.load(_WithStrBool, argv=["--input.str", "yes"], env={})
        assert cfg.input == "yes"
        assert type(cfg.input) is str

    def test_str_type_stealing_builtin(self, loader: ConfargLoader) -> None:
        """--value int resolves to the int class for str | type (type steals over str)."""
        cfg = loader.load(_WithStrType, argv=["--value", "int"], env={})
        assert cfg.value is int

    def test_str_type_stealing_dotted_path(self, loader: ConfargLoader) -> None:
        """--value <dotted> resolves to the class for str | type (type steals over str)."""
        path = f"{_StealMarker.__module__}.{_StealMarker.__qualname__}"
        cfg = loader.load(_WithStrType, argv=["--value", path], env={})
        assert cfg.value is _StealMarker

    def test_str_type_override(self, loader: ConfargLoader) -> None:
        """--value.str int preserves 'int' as a string, bypassing type stealing."""
        cfg = loader.load(_WithStrType, argv=["--value.str", "int"], env={})
        assert cfg.value == "int"
        assert type(cfg.value) is str

    def test_float_steals_over_int(self, loader: ConfargLoader) -> None:
        """--value 5 lands on float for int | float: rank decides, not declaration order."""
        cfg = loader.load(_WithIntFloat, argv=["--value", "5"], env={})
        assert type(cfg.value) is float

    def test_registered_leaf_steals_over_int(self, loader: ConfargLoader, leaf_registry: None) -> None:
        """--value 5 lands on the registered leaf for int | Decimal, in every integration."""
        confarg.register_leaf_type(Decimal, Decimal)
        cfg = loader.load(_WithIntDecimal, argv=["--value", "5"], env={})
        assert cfg.value == Decimal(5)
        assert type(cfg.value) is Decimal


# ---------------------------------------------------------------------------
# Scalar force-cast flags on plain (non-union) leaf fields
# ---------------------------------------------------------------------------


class TestPlainFieldCastContract:
    """Scalar force-cast flags on plain leaf fields, in every front-end (BUG-72).

    Vanilla's ``detect_force_cast`` accepts a scalar cast wherever the trailing
    segment names no real member of the field's type, and a plain leaf has no
    members — so ``--host.str`` reaches ``build()`` and pins the value there. The
    adapters register the cast flags only on multi-variant unions, so the host
    frameworks refused them; the registration now covers plain leaf fields too,
    and the last spelling typed wins, as vanilla's sequential writes decide it.
    """

    def test_matching_cast_on_str_and_int_fields(self, loader: ConfargLoader) -> None:
        """--host.str myhost --port.int 42 build, as vanilla does (the filed repro)."""
        cfg = loader.load(_PlainCastScalars, argv=["--host.str", "myhost", "--port.int", "42"], env={})
        assert cfg.host == "myhost"
        assert cfg.port == 42

    def test_cross_cast_pins_the_named_scalar_type(self, loader: ConfargLoader) -> None:
        """--host.int 5 and --port.str 42 pin the cast's type, not the field's."""
        cfg = loader.load(_PlainCastScalars, argv=["--host.int", "5"], env={})
        assert cfg.host == 5
        assert type(cfg.host) is int
        cfg = loader.load(_PlainCastScalars, argv=["--port.str", "42"], env={})
        assert cfg.port == "42"
        assert type(cfg.port) is str

    def test_float_and_bool_casts(self, loader: ConfargLoader) -> None:
        """--ratio.float 2 and --enabled.bool yes pin float and bool."""
        cfg = loader.load(_PlainCastScalars, argv=["--ratio.float", "2"], env={})
        assert cfg.ratio == 2.0
        assert type(cfg.ratio) is float
        cfg = loader.load(_PlainCastScalars, argv=["--enabled.bool", "yes"], env={})
        assert cfg.enabled is True

    def test_cast_on_optional_scalar(self, loader: ConfargLoader) -> None:
        """--note.str hi pins the str of a `str | None` field."""
        cfg = loader.load(_OptionalScalar, argv=["--note.str", "hi"], env={})
        assert cfg.note == "hi"

    def test_cast_on_enum_leaf(self, loader: ConfargLoader) -> None:
        """--color.str red pins the str, which build() then leaves as the field value."""
        cfg = loader.load(WithEnum, argv=["--color.str", "red"], env={})
        assert cfg.color == "red"
        assert type(cfg.color) is str

    def test_cast_on_nested_leaf(self, loader: ConfargLoader) -> None:
        """--inner.host.str x pins the leaf two levels down, not only at the root."""
        cfg = loader.load(_NestedPlainCast, argv=["--inner.host.str", "x"], env={})
        assert cfg.inner.host == "x"

    def test_plain_flag_typed_after_the_cast_wins(self, loader: ConfargLoader) -> None:
        """--host.str a --host b: vanilla's sequential writes leave the plain value."""
        cfg = loader.load(_PlainCastScalars, argv=["--host.str", "a", "--host", "b"], env={})
        assert cfg.host == "b"

    def test_cast_typed_after_the_plain_flag_wins(self, loader: ConfargLoader) -> None:
        """--host b --host.str a: the cast occurrence is the later write."""
        cfg = loader.load(_PlainCastScalars, argv=["--host", "b", "--host.str", "a"], env={})
        assert cfg.host == "a"

    def test_last_cast_of_several_wins(self, loader: ConfargLoader) -> None:
        """Several cast spellings: argv order decides, not the cast name."""
        cfg = loader.load(_PlainCastScalars, argv=["--host.int", "5", "--host.str", "a"], env={})
        assert cfg.host == "a"
        cfg = loader.load(_PlainCastScalars, argv=["--host.str", "a", "--host.int", "5"], env={})
        assert cfg.host == 5

    def test_replaced_bad_cast_does_not_error(self, loader: ConfargLoader) -> None:
        """The pinning is deferred, so a cast a later write replaced never coerces."""
        cfg = loader.load(_PlainCastScalars, argv=["--host.int", "abc", "--host.str", "a"], env={})
        assert cfg.host == "a"

    def test_surviving_bad_cast_raises_at_build(self, loader: ConfargLoader) -> None:
        """The surviving cast is coerced at build(), naming the field like vanilla."""
        with pytest.raises(TypeCoercionError):
            loader.load(_PlainCastScalars, argv=["--host.str", "a", "--host.int", "abc"], env={})

    def test_typed_cast_flag_is_registered(self, populating_loader: ConfargLoader) -> None:
        """The cast flag registers only when typed, like `.json` and the escaped openers."""
        flags = populating_loader.registered_flags(_PlainCastScalars, argv=["--host.str", "a"])
        assert flags is not None
        assert "host.str" in flags
        flags = populating_loader.registered_flags(_PlainCastScalars, argv=[])
        assert flags is not None
        assert "host.str" not in flags


# ---------------------------------------------------------------------------
# Union with a sequence variant (str | tuple[...], str | list[str])
# ---------------------------------------------------------------------------


class TestUnionWithSequenceContract:
    """A union mixing a scalar with a sequence variant accepts one or many tokens.

    One token stays a bare scalar; two-or-more tokens form the sequence. The
    space-separated spelling is not available everywhere, so it uses the space_sep
    fixture; the repeated spelling every front-end accepts, and means the same thing in
    each -- see TestRepeatedFlagAccumulationContract.
    """

    def test_str_tuple_single_value_is_scalar(self, loader: ConfargLoader) -> None:
        """--input foo yields the bare str for str | tuple[str, str]."""
        cfg = loader.load(_WithStrTuple, argv=["--input", "foo"], env={})
        assert cfg.input == "foo"

    def test_str_list_single_value_is_scalar(self, loader: ConfargLoader) -> None:
        """--input foo yields the bare str for str | list[str]."""
        cfg = loader.load(_WithStrList, argv=["--input", "foo"], env={})
        assert cfg.input == "foo"

    def test_bool_list_single_value_matches_scalar(self, loader: ConfargLoader) -> None:
        """--input true matches the bool variant for bool | list[str] (scalar priority)."""
        cfg = loader.load(_WithBoolList, argv=["--input", "true"], env={})
        assert cfg.input is True

    def test_bool_list_single_value_falls_back_to_list(self, loader: ConfargLoader) -> None:
        """--input hello: bool rejects it, so it fills list[str] as ['hello'] (the reported bug)."""
        cfg = loader.load(_WithBoolList, argv=["--input", "hello"], env={})
        assert cfg.input == ["hello"]

    def test_str_tuple_two_values_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input foo bar builds the tuple (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(_WithStrTuple, argv=["--input", "foo", "bar"], env={})
        assert cfg.input == ("foo", "bar")

    def test_str_tuple_two_values_repeated(self, loader: ConfargLoader) -> None:
        """--input foo --input bar builds the tuple, in every front-end."""
        cfg = loader.load(_WithStrTuple, argv=["--input", "foo", "--input", "bar"], env={})
        assert cfg.input == ("foo", "bar")

    def test_str_list_two_values_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input foo bar builds the list (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(_WithStrList, argv=["--input", "foo", "bar"], env={})
        assert cfg.input == ["foo", "bar"]

    def test_str_list_two_values_repeated(self, loader: ConfargLoader) -> None:
        """--input foo --input bar builds the list, in every front-end."""
        cfg = loader.load(_WithStrList, argv=["--input", "foo", "--input", "bar"], env={})
        assert cfg.input == ["foo", "bar"]

    def test_str_list_empty_builds_empty_list_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input with no token builds [] for str | list[str] (vanilla, argparse, cyclopts)."""
        cfg = space_sep_loader.load(_WithStrList, argv=["--input"], env={})
        assert cfg.input == []

    def test_str_tuple_empty_raises_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """--input with no token is rejected for str | tuple[str, str] (no varlen variant)."""
        with pytest.raises(ConfargError):
            space_sep_loader.load(_WithStrTuple, argv=["--input"], env={})

    def test_optional_varlen_tokens_are_stored_raw(self, loader: ConfargLoader) -> None:
        """``list[int] | None`` stores raw tokens, as the union branch does (BUG-61).

        Vanilla dispatches the *resolved* union, so it never coerces per element
        either; the merged dict carries the text and ``build()`` coerces it.
        """
        assert loader.merge(_WithOptionalIntList, argv=["--input", "5"], env={}) == {"input": ["5"]}

    def test_flag_registered(self, populating_loader: ConfargLoader) -> None:
        """The union-with-sequence field flag is registered on every adapter."""
        for target in (_WithStrTuple, _WithStrList):
            flags = populating_loader.registered_flags(target)
            assert flags is not None
            assert "input" in flags

    def test_leading_bare_occurrence_beside_a_valued_one_is_a_missing_value(self, loader: ConfargLoader) -> None:
        """--input --input a is refused at the first occurrence, whose run is still empty (BUG-79).

        The same argv-order read the Optional fixed-arity spelling needs: vanilla
        shapes the accumulation at every occurrence, and the union with no varlen
        variant has no empty value to store, so the leading bare occurrence is a
        missing value even though a valued one follows.
        """
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--input'")):
            loader.merge(_WithStrTuple, argv=["--input", "--input", "a"], env={})

    def test_leading_bare_occurrence_beside_a_space_run(self, space_sep_loader: ConfargLoader) -> None:
        """--input --input a b is the space-run form of the same refusal (BUG-79)."""
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--input'")):
            space_sep_loader.merge(_WithStrTuple, argv=["--input", "--input", "a", "b"], env={})

    def test_trailing_bare_occurrence_keeps_the_run(self, loader: ConfargLoader) -> None:
        """A trailing bare occurrence adds nothing once the run is non-empty (BUG-79)."""
        assert loader.merge(_WithStrTuple, argv=["--input", "a", "--input", "b", "--input"], env={}) == {
            "input": ["a", "b"],
        }


# ---------------------------------------------------------------------------
# Inline JSON array as a single token (nargs="*" collection / union-seq fields)
# ---------------------------------------------------------------------------


class TestJsonArrayTokenContract:
    """A single inline JSON-array token sets a collection field, matching confarg.load().

    A ``nargs="*"`` flag (a varlen list or a union-with-sequence-variant) accepts one
    inline JSON array as its whole value. Elements keep their JSON types: unlike the
    space-separated form, strings are exempt from the stealing rule and ``null`` is
    expressible. Every adapter must agree with the vanilla loader.
    """

    def test_varlen_list_json_array(self, loader: ConfargLoader) -> None:
        """--values '["hello", "yes", "well"]' -> strings; "yes" is NOT stolen to True."""
        cfg = loader.load(_WithStrBoolList, argv=["--values", '["hello", "yes", "well"]'], env={})
        assert cfg.values == ["hello", "yes", "well"]

    def test_varlen_list_json_preserves_null(self, loader: ConfargLoader) -> None:
        """--values '[null, 550]' -> [None, 550]; null cannot be expressed space-separated."""
        cfg = loader.load(_WithIntNoneList, argv=["--values", "[null, 550]"], env={})
        assert cfg.values == [None, 550]

    def test_union_seq_json_array(self, loader: ConfargLoader) -> None:
        """--input '["a", "b"]' fills the list variant of str | list[str]."""
        cfg = loader.load(_WithStrList, argv=["--input", '["a", "b"]'], env={})
        assert cfg.input == ["a", "b"]

    def test_invalid_json_falls_back_to_literal(self, loader: ConfargLoader) -> None:
        """A non-JSON '[' token is not parsed; it stays a single literal element."""
        cfg = loader.load(_WithStrBoolList, argv=["--values", "[oops"], env={})
        assert cfg.values == ["[oops"]

    def test_merged_dict_matches_vanilla(self, loader: ConfargLoader) -> None:
        """The raw merged dict is byte-identical across all four loaders (plain values)."""
        merged = loader.merge(_WithStrBoolList, argv=["--values", '["hello", "yes", "well"]'], env={})
        assert merged == {"values": ["hello", "yes", "well"]}


# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------


class TestConfigFilesContract:
    """Config-file loading and precedence behave identically in every integration."""

    def test_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Files passed via --config are loaded and merged."""
        cfg_file = tmp_yaml("host: filehost\nport: 5432\n")
        cfg = loader.load(Simple, argv=["--config", str(cfg_file)], env={})
        assert cfg.host == "filehost"
        assert cfg.port == 5432

    def test_config_file_via_files_param(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Files passed via files= are loaded without any CLI flag."""
        cfg_file = tmp_yaml("host: file_host\nport: 9999\n")
        cfg = loader.load(Simple, argv=[], env={}, files=[cfg_file])
        assert cfg.host == "file_host"
        assert cfg.port == 9999

    def test_csv_include_coerces_to_target_types(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        tmp_yaml,
    ) -> None:
        """A CSV pulled in by __include__ coerces its cells to the target leaf types."""
        (tmp_path / "rows.csv").write_text("host,port\nfilehost,5432\n")
        cfg_file = tmp_yaml("db:\n  __include__: ./rows.csv\n")
        cfg = loader.load(WithCsvRows, argv=["--config", str(cfg_file)], env={})
        assert cfg.db == [Simple(host="filehost", port=5432)]

    def test_include_list_layers_in_order(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        tmp_yaml,
    ) -> None:
        """A list-valued __include__ layers left to right, later entries winning."""
        (tmp_path / "a.yaml").write_text("host: a_host\nport: 1\n")
        (tmp_path / "b.yaml").write_text("host: b_host\n")
        cfg_file = tmp_yaml("__include__: [./a.yaml, ./b.yaml]\n")
        cfg = loader.load(Simple, argv=["--config", str(cfg_file)], env={})
        assert cfg == Simple(host="b_host", port=1)

    def test_cli_overrides_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """CLI values take priority over config-file values."""
        cfg_file = tmp_yaml("host: filehost\nport: 1111\n")
        cfg = loader.load(Simple, argv=["--config", str(cfg_file), "--port", "2222"], env={})
        assert cfg.host == "filehost"
        assert cfg.port == 2222

    def test_env_overrides_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Env vars take priority over config-file values."""
        cfg_file = tmp_yaml("host: filehost\nport: 1111\n")
        cfg = loader.load(
            Simple,
            argv=["--config", str(cfg_file)],
            env={"MYAPP_PORT": "3333"},
            env_prefix="MYAPP_",
        )
        assert cfg.host == "filehost"
        assert cfg.port == 3333

    def test_multiple_config_files_merged(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Later --config files override earlier ones (repeated-flag form works everywhere)."""
        base = tmp_yaml("host: base\nport: 1000\n", filename="base.yaml")
        override = tmp_yaml("port: 2000\n", filename="override.yaml")
        cfg = loader.load(Simple, argv=["--config", str(base), "--config", str(override)], env={})
        assert cfg.host == "base"
        assert cfg.port == 2000

    def test_subkey_config_loads_under_subkey(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.db file.yaml loads file contents under the 'db' key."""
        db_cfg = tmp_yaml("host: db_host\nport: 5555\nname: db_name\n", filename="db.yaml")
        cfg = loader.load(AppConfig, argv=["--config.db", str(db_cfg)], env={})
        assert cfg.db == DbConfig(host="db_host", port=5555, name="db_name")

    def test_subkey_and_root_config_combined(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Root --config and --config.db combine; CLI still wins over both."""
        root_cfg = tmp_yaml("debug: true\ncache:\n  enabled: false\n", filename="root.yaml")
        db_cfg = tmp_yaml("host: from_file\nport: 1111\nname: n\n", filename="db.yaml")
        cfg = loader.load(
            AppConfig,
            argv=["--config", str(root_cfg), "--config.db", str(db_cfg), "--db.port", "9999"],
            env={},
        )
        assert cfg.debug is True
        assert cfg.cache == CacheConfig(enabled=False)
        assert cfg.db.host == "from_file"
        assert cfg.db.port == 9999

    def test_left_to_right_subkey_then_root(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.db db.yaml --config root.yaml: root file (rightmost) wins for db."""
        root_cfg = tmp_yaml(
            "db:\n  host: root_host\n  port: 1111\n  name: root_db\ncache:\n  enabled: true\n",
            filename="root.yaml",
        )
        db_cfg = tmp_yaml("host: db_host\nport: 5555\nname: db_db\n", filename="db.yaml")
        cfg = loader.load(AppConfig, argv=["--config.db", str(db_cfg), "--config", str(root_cfg)], env={})
        assert cfg.db == DbConfig(host="root_host", port=1111, name="root_db")

    def test_left_to_right_root_then_subkey(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config root.yaml --config.db db.yaml: subkey file (rightmost) wins for db."""
        root_cfg = tmp_yaml(
            "db:\n  host: root_host\n  port: 1111\n  name: root_db\ncache:\n  enabled: true\n",
            filename="root.yaml",
        )
        db_cfg = tmp_yaml("host: db_host\nport: 5555\nname: db_db\n", filename="db.yaml")
        cfg = loader.load(AppConfig, argv=["--config", str(root_cfg), "--config.db", str(db_cfg)], env={})
        assert cfg.db == DbConfig(host="db_host", port=5555, name="db_db")

    def test_bare_config_flag_refused(self, loader: ConfargLoader) -> None:
        """A bare --config is an error in every front-end, never a silent no-op (BUG-51)."""
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(Simple, argv=["--config"], env={})

    def test_bare_config_error_names_the_flag(self, loader: ConfargLoader) -> None:
        """Where confarg raises the refusal itself, its message names the config flag (BUG-51)."""
        with pytest.raises(_REJECTS_BARE_FLAG) as excinfo:
            loader.load(Simple, argv=["--config"], env={})
        if isinstance(excinfo.value, ConfargError):
            assert "Missing file path after --config" in str(excinfo.value)

    def test_bare_config_subpath_flag_refused(self, loader: ConfargLoader) -> None:
        """A bare --config.<subpath> is refused like the root flag (BUG-51)."""
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(AppConfig, argv=["--config.db"], env={})

    def test_bare_config_append_flag_refused(self, loader: ConfargLoader) -> None:
        """A bare --config.<subpath>+ mounts nothing on no front-end (BUG-51)."""
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(WithList, argv=["--config.tags+"], env={})

    def test_bare_config_append_after_a_file_refused(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A bare --config.<subpath>+ tailing a carried one is an error, not a dropped tail (BUG-51)."""
        tags_file = tmp_yaml("- a\n- b\n", filename="tags.yaml")
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(WithList, argv=["--config.tags+", str(tags_file), "--config.tags+"], env={})

    def test_unknown_subpath_rejected_on_every_frontend(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.<subpath> naming no field is an error everywhere, not a silent mount (BUG-50)."""
        db_cfg = tmp_yaml("host: h\nport: 1\nname: n\n", filename="db.yaml")
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(AppConfig, argv=["--config.dbb", str(db_cfg)], env={})

    def test_unknown_subpath_error_names_the_field(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Where confarg raises the refusal itself, its message names the flag (BUG-50)."""
        db_cfg = tmp_yaml("host: h\nport: 1\nname: n\n", filename="db.yaml")
        with pytest.raises(_REJECTS_BARE_FLAG) as excinfo:
            loader.load(AppConfig, argv=["--config.dbb", str(db_cfg)], env={})
        if isinstance(excinfo.value, ConfargError):
            assert "--config.dbb" in str(excinfo.value)
            assert "names no field" in str(excinfo.value)

    def test_config_flag_registered_by_default(self, populating_loader: ConfargLoader) -> None:
        """populate_* registers the --config flag (and subkey flags) by default."""
        flags = populating_loader.registered_flags(AppConfig)
        assert flags is not None
        assert "config" in flags
        assert "config.db" in flags

    def test_config_flag_absent_when_disabled(self, populating_loader: ConfargLoader) -> None:
        """config_flag='' suppresses --config registration."""
        flags = populating_loader.registered_flags(Simple, config_flag="")
        assert flags is not None
        assert "config" not in flags

    def test_custom_config_flag_name(self, populating_loader: ConfargLoader) -> None:
        """config_flag='cfg' registers --cfg instead of --config."""
        flags = populating_loader.registered_flags(Simple, config_flag="cfg")
        assert flags is not None
        assert "cfg" in flags
        assert "config" not in flags

    def test_dict_field_gets_a_subkey_flag(self, populating_loader: ConfargLoader) -> None:
        """A dict field is a mount point too, so its --config.<name> flag is registered (BUG-50)."""
        flags = populating_loader.registered_flags(WithCollections)
        assert flags is not None
        assert "config.mapping" in flags

    def test_union_of_structs_field_gets_a_subkey_flag(self, populating_loader: ConfargLoader) -> None:
        """A union-of-structs field is a mount point too, so its --config.<name> flag is registered (BUG-70).

        Like a struct or a dict field's entry (BUG-50), on the adapters that register flags.
        """
        flags = populating_loader.registered_flags(_FieldTagged)
        assert flags is not None
        assert "config.u" in flags

    def test_union_mount_entry_help_names_the_tag(self) -> None:
        """The union mount entry's help says the file must name its variant with the tag (BUG-70).

        The field's own flags are per-variant, so without this line the reader cannot
        learn that the fragment's top level carries the tag.
        """
        specs = {s.name: s for s in build_static_flags(_FieldTagged)}
        assert "'class'" in specs["config.u"].help

    def test_config_subkeys_false_root_only(self, populating_loader: ConfargLoader) -> None:
        """config_subkeys=False registers only the root --config flag."""
        flags = populating_loader.registered_flags(AppConfig, config_subkeys=False)
        assert flags is not None
        assert "config" in flags
        assert "config.db" not in flags


# ---------------------------------------------------------------------------
# Pipeline parity — regressions for former vanilla-vs-adapter divergences
# ---------------------------------------------------------------------------


class TestPipelineParity:
    """Regression tests for former vanilla-vs-adapter divergences.

    One test per behavior that historically diverged between confarg.load()
    and the CLI adapters before both shared _merge_sources.
    """

    def test_custom_config_flag_env_pointer(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A custom config_flag is honored for env-specified config files.

        Adapters used to hard-default the env-pointer segment to "config",
        silently ignoring a custom flag name.
        """
        cfg = tmp_yaml("host: envhost\nport: 5432\nname: envdb\n")
        result = loader.load(
            DbConfig,
            argv=[],
            env={"MYAPP_CONF": str(cfg)},
            env_prefix="MYAPP_",
            config_flag="conf",
        )
        assert result == DbConfig(host="envhost", port=5432, name="envdb")

    def test_config_append_syntax(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.field+ appends file items to a list instead of replacing it.

        Adapters used to load all CLI config files with plain replace semantics,
        ignoring the trailing ``+``.
        """
        base = tmp_yaml("users:\n  - alice\n  - bob\n", filename="base.yaml")
        extra = tmp_yaml("- carol\n", filename="extra.yaml")
        target = make_target("users", list[str])
        result = loader.load(
            target,
            argv=["--config.users+", str(extra)],
            env={},
            files=[base],
        )
        assert result.users == ["alice", "bob", "carol"]

    def test_env_config_loads_named_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """env_config names an env var whose value is a config file path.

        Adapters used to not support env_config at all.  The env var itself must
        not be parsed as a field (no unknown-field warning / stray value).
        """
        cfg = tmp_yaml("host: filehost\nport: 1234\nname: filedb\n")
        result = loader.load(
            DbConfig,
            argv=[],
            env={"MYAPP_CONFIG_FILE": str(cfg), "MYAPP_PORT": "9999"},
            env_prefix="MYAPP_",
            env_config="MYAPP_CONFIG_FILE",
        )
        # Inline env var wins over the env_config file; other fields come from the file.
        assert result == DbConfig(host="filehost", port=9999, name="filedb")

    def test_env_config_subpath_ordering(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Env-specified config files load shallow-to-deep, so deeper paths win.

        Adapters used to load env config files in mapping order without sorting.
        """
        base = tmp_yaml(
            """\
            db:
              host: basehost
              port: 1111
              name: basedb
            cache:
              enabled: false
            """,
            filename="base.yaml",
        )
        db = tmp_yaml("host: dbhost\nport: 2222\nname: dbdb\n", filename="db.yaml")
        # Mapping order is deliberately deep-first; the pipeline must sort so the
        # global file loads first and the subpath file overrides it.
        result = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_CONFIG__DB": str(db), "MYAPP_CONFIG": str(base)},
            env_prefix="MYAPP_",
        )
        assert result.db == DbConfig(host="dbhost", port=2222, name="dbdb")
        assert result.cache == CacheConfig(enabled=False)

    def test_empty_config_flag_treats_config_as_field(self, loader: ConfargLoader) -> None:
        """config_flag="" disables config handling; a field named "config" stays a field."""
        target = make_target("config", str)
        result = loader.load(
            target,
            argv=[],
            env={"MYAPP_CONFIG": "hello"},
            env_prefix="MYAPP_",
            config_flag="",
        )
        assert result.config == "hello"

    def test_scalar_root_target_via_env(self, loader: ConfargLoader) -> None:
        """A non-struct root target works through every integration (build's __root__ path).

        Adapters used to call construct() directly, which lacked the __root__
        unwrapping that build() does for scalar targets.  The CLI channel is
        covered by :class:`TestCliPrefixContract`, which needs a cli_prefix to
        name the root.
        """
        result = loader.load(int, argv=[], env={"MYAPP_VALUE": "8080"}, env_prefix="MYAPP_", config_flag="")
        assert result == 8080


# ---------------------------------------------------------------------------
# cli_prefix
# ---------------------------------------------------------------------------


class TestCliPrefixContract:
    """``cli_prefix`` namespaces every confarg flag, identically in every integration.

    The prefix was vanilla-only until the adapters learned to apply it when
    registering flags and strip it when reading them back (BUG-2).  The loader
    harness hands it to ``populate_*`` only, so every test here also covers
    recovering the prefix recorded at registration time.
    """

    def test_scalar_root_from_cli(self, loader: ConfargLoader) -> None:
        """``--<prefix> VALUE`` sets a non-struct root — the CLI spelling BUG-2 lacked."""
        assert loader.load(int, argv=["--app", "8080"], env={}, cli_prefix="app", config_flag="") == 8080

    def test_scalar_root_merges_to_root_key(self, loader: ConfargLoader) -> None:
        """The merged dict for a scalar root is byte-identical to vanilla's ``__root__`` dict."""
        merged = loader.merge(int, argv=["--app", "8080"], env={}, cli_prefix="app", config_flag="")
        assert merged == {"__root__": 8080}

    def test_scalar_root_json_cast(self, loader: ConfargLoader) -> None:
        """``--<prefix>.json`` sets a non-struct root, as vanilla's root cast does."""
        assert loader.load(int, argv=["--app.json", "42"], env={}, cli_prefix="app", config_flag="") == 42

    def test_scalar_root_json_cast_list(self, loader: ConfargLoader) -> None:
        """A root ``.json`` cast builds a whole collection root from one token."""
        got = loader.load(list[int], argv=["--app.json", "[1, 2]"], env={}, cli_prefix="app", config_flag="")
        assert got == [1, 2]

    def test_scalar_root_optional_none_token(self, loader: ConfargLoader) -> None:
        """The ``none`` token resolves to None for an optional scalar root."""
        assert loader.load(str | None, argv=["--app", "none"], env={}, cli_prefix="app", config_flag="") is None

    def test_prefixed_flat_field(self, loader: ConfargLoader) -> None:
        """A flat field is addressed as ``--<prefix>.<field>``."""
        target = make_target("name", str)
        assert loader.load(target, argv=["--app.name", "val"], env={}, cli_prefix="app").name == "val"

    def test_prefixed_nested_field(self, loader: ConfargLoader) -> None:
        """A nested path keeps the prefix in front of the whole dotted path."""
        result = loader.load(
            AppConfig,
            argv=["--cfg.db.host", "h", "--cfg.db.port", "1", "--cfg.db.name", "n"],
            env={},
            cli_prefix="cfg",
        )
        assert result.db == DbConfig(host="h", port=1, name="n")

    def test_prefixed_config_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The config-file flag is prefixed too, as vanilla requires (``--<prefix>.config``)."""
        cfg = tmp_yaml("{host: filehost, port: 5432, name: filedb}")
        result = loader.load(DbConfig, argv=["--app.config", str(cfg)], env={}, cli_prefix="app")
        assert result == DbConfig(host="filehost", port=5432, name="filedb")

    def test_prefixed_collection_patch(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Argv-order collection patches survive the prefix strip of the argv rescan."""
        base = tmp_yaml("users: [alice, bob, claire]")
        cfg = loader.load(
            _WithUsers,
            argv=["--app.config", str(base), "--app.users.0", "allan"],
            env={},
            cli_prefix="app",
        )
        assert cfg.users == ["allan", "bob", "claire"]

    def test_prefixed_expression_over_cli(self, loader: ConfargLoader) -> None:
        """Eager coercion still happens under a prefix, so CLI numbers work in expressions."""
        target = make_target("port", int)
        assert loader.load(target, argv=["--app.port", "8080"], env={}, cli_prefix="app").port == 8080

    def test_every_registered_flag_carries_the_prefix(self, populating_loader: ConfargLoader) -> None:
        """``populate_*`` registers nothing outside the prefix namespace."""
        flags = populating_loader.registered_flags(AppConfig, cli_prefix="app")
        assert flags
        assert all(f == "app" or f.startswith("app.") for f in flags), sorted(flags)

    def test_scalar_root_registers_the_bare_prefix_flag(self, populating_loader: ConfargLoader) -> None:
        """A non-struct root is registered as the bare ``--<prefix>`` flag."""
        flags = populating_loader.registered_flags(int, cli_prefix="app", config_flag="")
        assert flags == {"app"}

    def test_no_prefix_registers_no_scalar_root_flag(self, populating_loader: ConfargLoader) -> None:
        """Without a prefix there is no flag name for a scalar root — as in vanilla."""
        assert populating_loader.registered_flags(int, config_flag="") == set()


# ---------------------------------------------------------------------------
# Inheritance-based dispatch (base class with subclasses)
# ---------------------------------------------------------------------------


class TestInheritanceDispatchContract:
    """Base-class targets dispatch to subclasses identically in every integration."""

    def test_class_flag_registered(self, populating_loader: ConfargLoader) -> None:
        """populate_* registers --class for a base dataclass with subclasses."""
        flags = populating_loader.registered_flags(_BaseDB, config_flag="")
        assert flags is not None
        assert "class" in flags

    def test_subclass_fields_registered(self, populating_loader: ConfargLoader) -> None:
        """populate_* also registers subclass fields as top-level flags."""
        flags = populating_loader.registered_flags(_BaseDB, config_flag="")
        assert flags is not None
        assert {"dbpath", "host", "port"} <= flags

    def test_class_completer_offers_each_subclass_once_nearest_first(self) -> None:
        """The --class completer lists every subclass exactly once, breadth-first.

        A diamond subclass is reachable by two inheritance paths and must not be
        offered twice; direct subclasses come before their own descendants.
        """
        flags = build_static_flags(_DiamondBase, union_tag="class", config_flag="")
        class_spec = next(f for f in flags if f.name == "class")
        assert class_spec.completer is not None
        expected = [f"{__name__}._Diamond{name}" for name in ("Left", "Right", "Join")]
        assert class_spec.completer("") == expected

    def test_dispatch_sqlite(self, loader: ConfargLoader) -> None:
        """--class selects and constructs the SQLite subclass."""
        result = loader.load(
            _BaseDB,
            argv=["--class", f"{__name__}._SQLiteDB", "--dbpath", "/var/db/app.sqlite"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _SQLiteDB)
        assert result.dbpath == "/var/db/app.sqlite"

    def test_dispatch_server(self, loader: ConfargLoader) -> None:
        """--class selects and constructs the server subclass."""
        result = loader.load(
            _BaseDB,
            argv=["--class", f"{__name__}._ServerDB", "--host", "db.example.com", "--port", "5432"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _ServerDB)
        assert result.host == "db.example.com"
        assert result.port == 5432

    def test_no_class_tag_raises(self, loader: ConfargLoader) -> None:
        """A base class with subclasses but no --class raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="discriminator"):
            loader.load(_BaseDB, argv=["--dbpath", "/var/db/app.sqlite"], env={}, config_flag="")

    def test_config_file_class_tag_keeps_cli_subclass_field(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A --config file's class tag still lets a subclass field typed on the CLI through."""
        cfg = tmp_yaml(f"class: {__name__}._SQLiteDB\n")
        result = loader.load(_BaseDB, argv=["--config", str(cfg), "--dbpath", "/var/db/app.sqlite"], env={})
        assert result == _SQLiteDB(dbpath="/var/db/app.sqlite")

    def test_nested_config_file_class_tag_keeps_cli_subclass_field(
        self,
        loader: ConfargLoader,
        tmp_yaml,
    ) -> None:
        """The same holds for a tag a --config file sets on a nested field."""
        cfg = tmp_yaml(f"db:\n  class: {__name__}._SQLiteDB\n")
        result = loader.load(_NestedDB, argv=["--config", str(cfg), "--db.dbpath", "/var/db/app.sqlite"], env={})
        assert result == _NestedDB(db=_SQLiteDB(dbpath="/var/db/app.sqlite"))

    def test_unimportable_class_tag_reaches_merged_dict(self, loader: ConfargLoader) -> None:
        """A --class tag naming no importable class still reaches the merged dict.

        Vanilla stores the raw string and lets ``build()`` raise the import error naming the
        path; an adapter that dropped the tag when the import failed answered instead with a
        misleading "no discriminator was provided" complaint (BUG-45).
        """
        merged = loader.merge(_BaseDB, argv=["--class", "no.such.module.Class"], env={}, config_flag="")
        assert merged == {"class": "no.such.module.Class"}

    def test_unimportable_field_class_tag_reaches_merged_dict(self, loader: ConfargLoader) -> None:
        """A nested path keeps its tag, not silence, when the named class does not import.

        The field-level shape loses more than the tag when it regresses: the recursion into
        the subclass fields is skipped along with it, so the whole ``db`` key vanishes.
        """
        merged = loader.merge(_NestedDB, argv=["--db.class", "no.such.module.Class"], env={}, config_flag="")
        assert merged == {"db": {"class": "no.such.module.Class"}}

    def test_valid_tag_keeps_other_subclass_flags_in_merged_dict(self, loader: ConfargLoader) -> None:
        """A valid tag keeps a sibling subclass's flags beside it, coerced by their own type.

        Vanilla coerces a flag by whichever subclass owns the name and lets ``build()``
        refuse it as unknown for the tagged subclass; an adapter that descended only into
        the named subclass dropped the flag silently instead (BUG-69).
        """
        merged = loader.merge(
            _BaseDB,
            argv=["--class", f"{__name__}._SQLiteDB", "--host", "db.example.com", "--port", "5432"],
            env={},
            config_flag="",
        )
        assert merged == {"class": f"{__name__}._SQLiteDB", "host": "db.example.com", "port": 5432}

    def test_valid_tag_other_subclass_flag_refused_by_build(self, loader: ConfargLoader) -> None:
        """A mistyped ``--<field>`` under a valid tag is an error, not a silent ignore.

        The loud case of BUG-69: the wrong-subclass flag reaches ``build()``, which raises
        ``Unknown field(s)`` naming it, exactly as the vanilla front-end does.
        """
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            loader.load(
                _BaseDB,
                argv=["--class", f"{__name__}._SQLiteDB", "--host", "db.example.com"],
                env={},
                config_flag="",
            )

    def test_unimportable_tag_keeps_sibling_flags(self, loader: ConfargLoader) -> None:
        """A tag whose import fails leaves the sibling flags in the dict ``merge()`` returns.

        The quiet case of BUG-69: the named subclass cannot be descended into, but the
        other subclasses' flags still reach the merged dict next to the raw tag, as in
        vanilla.
        """
        merged = loader.merge(
            _BaseDB,
            argv=["--class", "no.such.module.Class", "--dbpath", "/var/db/app.sqlite"],
            env={},
            config_flag="",
        )
        assert merged == {"class": "no.such.module.Class", "dbpath": "/var/db/app.sqlite"}

    def test_nested_valid_tag_keeps_other_subclass_flags(self, loader: ConfargLoader) -> None:
        """The nested inheritance path keeps a sibling subclass's flag too (BUG-69)."""
        merged = loader.merge(
            _NestedDB,
            argv=["--db.class", f"{__name__}._SQLiteDB", "--db.host", "db.example.com"],
            env={},
            config_flag="",
        )
        assert merged == {"db": {"class": f"{__name__}._SQLiteDB", "host": "db.example.com"}}

    def test_no_tag_keeps_subclass_flags_in_merged_dict(self, loader: ConfargLoader) -> None:
        """Without a tag anywhere, a subclass's flag still reaches the merged dict.

        Vanilla coerces the flag by the subclass's own field type and leaves ``build()``
        to raise the missing-discriminator complaint; the inheritance branch alone
        returned before any descent and dropped the flag outright (BUG-83).
        """
        merged = loader.merge(_BaseDB, argv=["--host", "db.example.com", "--port", "5432"], env={}, config_flag="")
        assert merged == {"host": "db.example.com", "port": 5432}

    def test_no_tag_nested_keeps_subclass_flags(self, loader: ConfargLoader) -> None:
        """The nested inheritance path keeps a subclass's flag without a tag too (BUG-83)."""
        merged = loader.merge(_NestedDB, argv=["--db.host", "db.example.com"], env={}, config_flag="")
        assert merged == {"db": {"host": "db.example.com"}}


# ---------------------------------------------------------------------------
# Struct field whose type is a union (tag dispatch on a non-root union field)
# ---------------------------------------------------------------------------


@dataclass
class _FieldSqlite:
    """Struct-union variant for field-level tag tests."""

    dbpath: str = ""


@dataclass
class _FieldServer:
    """Struct-union variant for field-level tag tests."""

    host: str = ""
    port: int = 0


@dataclass
class _FieldTagged:
    """Struct whose field is a union of structs (tag dispatch below the root)."""

    u: _FieldSqlite | _FieldServer | None = None


class TestUnionFieldTagContract:
    """A struct field whose type is a union dispatches on its tag identically everywhere."""

    def test_tag_keeps_other_variants_flags_in_merged_dict(self, loader: ConfargLoader) -> None:
        """A tag on a union field keeps the other variants' flags beside it (BUG-69).

        Vanilla coerces ``--u.<field>`` by whichever variant owns the name; descending
        only into the named variant dropped the rest from the adapters' merged dict.
        """
        merged = loader.merge(
            _FieldTagged,
            argv=["--u.class", f"{__name__}._FieldSqlite", "--u.host", "db.example.com", "--u.port", "5432"],
            env={},
            config_flag="",
        )
        assert merged == {"u": {"class": f"{__name__}._FieldSqlite", "host": "db.example.com", "port": 5432}}

    def test_tag_other_variants_flag_refused_by_build(self, loader: ConfargLoader) -> None:
        """A wrong-variant flag on a union field is an error, not a silent ignore (BUG-69)."""
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            loader.load(
                _FieldTagged,
                argv=["--u.class", f"{__name__}._FieldSqlite", "--u.host", "db.example.com"],
                env={},
                config_flag="",
            )

    def test_unimportable_tag_keeps_other_variants_flags(self, loader: ConfargLoader) -> None:
        """An unimportable tag on a union field keeps the variants' flags next to it (BUG-69)."""
        merged = loader.merge(
            _FieldTagged,
            argv=["--u.class", "no.such.module.Class", "--u.dbpath", "/var/db/app.sqlite"],
            env={},
            config_flag="",
        )
        assert merged == {"u": {"class": "no.such.module.Class", "dbpath": "/var/db/app.sqlite"}}


# ---------------------------------------------------------------------------
# A flag owned by several variants: vanilla coerces it once, by the common type
# when every owner agrees and by str when they disagree (BUG-84)
# ---------------------------------------------------------------------------


@dataclass
class _OwnerInt:
    """Union variant owning ``a`` as ``int``."""

    a: int = 1


@dataclass
class _OwnerFloat:
    """Union variant owning ``a`` as ``float``, and ``only`` alone."""

    a: float = 2.0
    only: int = 0


@dataclass
class _OwnersDisagree:
    """Union field whose variants own ``a`` with disagreeing types."""

    u: _OwnerInt | _OwnerFloat | None = None


@dataclass
class _OwnerInt2:
    """Union variant owning ``a`` as ``int``, like ``_OwnerInt``."""

    a: int = 1


@dataclass
class _OwnersAgree:
    """Union field whose variants own ``a`` with the same type."""

    u: _OwnerInt | _OwnerInt2 | None = None


@dataclass
class _InnerInt:
    """Nested struct owning ``b`` as ``int``."""

    b: int = 0


@dataclass
class _InnerFloat:
    """Nested struct owning ``b`` as ``float``."""

    b: float = 0.0


@dataclass
class _NestedOwnerInt:
    """Union variant owning ``a`` as a struct with ``b: int``."""

    a: _InnerInt | None = None


@dataclass
class _NestedOwnerFloat:
    """Union variant owning ``a`` as a struct with ``b: float``."""

    a: _InnerFloat | None = None


@dataclass
class _NestedOwnersDisagree:
    """Union field whose variants own ``a`` as disagreeing structs."""

    u: _NestedOwnerInt | _NestedOwnerFloat | None = None


@dataclass
class _NestedOwnerInt2:
    """Union variant owning ``a`` as the same struct ``_NestedOwnerInt`` has."""

    a: _InnerInt | None = None


@dataclass
class _NestedOwnersAgree:
    """Union field whose variants own ``a`` as the same struct type."""

    u: _NestedOwnerInt | _NestedOwnerInt2 | None = None


@dataclass
class _StructOwner:
    """Union variant owning ``a`` as a struct whose ``b`` is an ``int``."""

    a: _InnerInt | None = None


@dataclass
class _ScalarOwner:
    """Union variant owning ``a`` as a scalar ``int``."""

    a: int = 0


@dataclass
class _StructScalarDisagree:
    """Union field whose variants own ``a`` as a struct and as a scalar (BUG-85)."""

    u: _StructOwner | _ScalarOwner | None = None


@dataclass
class _ExtraBase:
    """Base class whose subclasses own ``extra`` with disagreeing types."""

    name: str = ""


@dataclass
class _ExtraInt(_ExtraBase):
    """Subclass owning the subclass-only field ``extra`` as ``int``."""

    extra: int = 0


@dataclass
class _ExtraFloat(_ExtraBase):
    """Subclass owning the subclass-only field ``extra`` as ``float``."""

    extra: float = 0.0


@dataclass
class _ExtraHolder:
    """Holder field typed as the base of the disagreeing subclasses."""

    x: _ExtraBase | None = None


_OwnersRoot: Any = _OwnerInt | _OwnerFloat


class TestVariantOwnerConflictContract:
    """A flag several variants own is coerced once, identically in every integration."""

    def test_disagreeing_owners_raw_without_tag(self, loader: ConfargLoader) -> None:
        """Vanilla returns the raw token when the variants disagree about a field's type.

        The adapters' collector walked each variant in turn and let the last write
        win, so the merged dict held that variant's coercion — ``7.0`` here —
        instead of the token ``build()`` resolves (BUG-84).
        """
        merged = loader.merge(_OwnersDisagree, argv=["--u.a", "7"], env={}, config_flag="")
        assert merged == {"u": {"a": "7"}}

    def test_disagreeing_owners_raw_with_tag(self, loader: ConfargLoader) -> None:
        """A tag does not change it: vanilla still coerces by all the variants' answer.

        With a tag the re-dispatch inside each sibling walk left the *named*
        variant's coercion standing — ``7`` here — while vanilla returns the raw
        token (BUG-84).
        """
        merged = loader.merge(
            _OwnersDisagree,
            argv=["--u.class", f"{__name__}._OwnerInt", "--u.a", "7"],
            env={},
            config_flag="",
        )
        assert merged == {"u": {"class": f"{__name__}._OwnerInt", "a": "7"}}

    def test_disagreeing_owners_build_defers_to_tagged_variant(self, loader: ConfargLoader) -> None:
        """The raw token still builds: ``build()`` coerces it by the variant the tag names."""
        result = loader.load(
            _OwnersDisagree,
            argv=["--u.class", f"{__name__}._OwnerFloat", "--u.a", "7"],
            env={},
            config_flag="",
        )
        assert result == _OwnersDisagree(u=_OwnerFloat(a=7.0))

    def test_single_owner_keeps_own_coercion(self, loader: ConfargLoader) -> None:
        """A flag only one variant owns keeps that variant's coercion.

        Guards the fix against over-firing: the conflict rule applies only where
        several owners disagree about the type.
        """
        merged = loader.merge(_OwnersDisagree, argv=["--u.only", "5"], env={}, config_flag="")
        assert merged == {"u": {"only": 5}}

    def test_agreeing_owners_keep_common_coercion(self, loader: ConfargLoader) -> None:
        """Owners that agree on the type are coerced by it, on every front-end."""
        merged = loader.merge(_OwnersAgree, argv=["--u.a", "7"], env={}, config_flag="")
        assert merged == {"u": {"a": 7}}

    def test_disagreeing_struct_owners_whole_value_raw(self, loader: ConfargLoader) -> None:
        """A whole-value token at a disagreeing struct flag stays the raw token.

        Vanilla resolves the flag to ``str``, so it decodes no object at all; the
        adapters' per-variant walks decoded the blob instead (BUG-84).
        """
        merged = loader.merge(_NestedOwnersDisagree, argv=["--u.a", '{"b": 7}'], env={}, config_flag="")
        assert merged == {"u": {"a": '{"b": 7}'}}

    def test_disagreeing_struct_owners_subflag_raw(self, loader: ConfargLoader) -> None:
        """A sub-flag two disagreeing structs own resolves to ``str`` as well."""
        merged = loader.merge(_NestedOwnersDisagree, argv=["--u.a.b", "7"], env={}, config_flag="")
        assert merged == {"u": {"a": {"b": "7"}}}

    def test_disagreeing_owner_raw_after_its_subflag_wins(self, loader: ConfargLoader) -> None:
        """A disagreeing-owner flag typed after its own sub-flag keeps the raw token (BUG-85).

        The conflict store is written before the variant walks, so a ``--u.a.b``
        the later ``--u.a`` had already overwritten came back on the adapters:
        the store is ``str`` here (a struct versus a scalar own ``a``), while
        its sub-flag stays a single owner's and is walked.
        """
        merged = loader.merge(_StructScalarDisagree, argv=["--u.a.b", "7", "--u.a", "9"], env={}, config_flag="")
        assert merged == {"u": {"a": "9"}}

    def test_disagreeing_owner_raw_before_its_subflag_is_walked(self, loader: ConfargLoader) -> None:
        """A disagreeing-owner flag typed first is descended into by its sub-flag (BUG-85).

        Guards the fix against over-firing: the walk's write lands on top of
        the raw store, as vanilla's later write does.
        """
        merged = loader.merge(_StructScalarDisagree, argv=["--u.a", "9", "--u.a.b", "7"], env={}, config_flag="")
        assert merged == {"u": {"a": {"b": 7}}}

    def test_disagreeing_struct_owners_nested_stores_in_argv_order(self, loader: ConfargLoader) -> None:
        """Two disagreeing paths, one below the other, are stored in argv order (BUG-85).

        ``a`` and ``a.b`` disagree between the variants here, so both are raw
        stores; the collector wrote them in walk order, so the deeper store
        covered the shallower one whatever argv spelled.
        """
        merged = loader.merge(_NestedOwnersDisagree, argv=["--u.a.b", "7", "--u.a", "9"], env={}, config_flag="")
        assert merged == {"u": {"a": "9"}}

    def test_disagreeing_struct_owners_nested_stores_reversed(self, loader: ConfargLoader) -> None:
        """The reverse argv order keeps the deeper store, the guard of the one above.

        Vanilla writes the deeper flag last, so it replaces the raw token the
        shallower one left.
        """
        merged = loader.merge(_NestedOwnersDisagree, argv=["--u.a", "9", "--u.a.b", "7"], env={}, config_flag="")
        assert merged == {"u": {"a": {"b": "7"}}}

    def test_disagreeing_struct_owners_nested_store_after_blob_raw(self, loader: ConfargLoader) -> None:
        """A raw whole-value token typed after its own sub-flag takes the path too (BUG-85)."""
        merged = loader.merge(
            _NestedOwnersDisagree,
            argv=["--u.a.b", "7", "--u.a", '{"b": 9}'],
            env={},
            config_flag="",
        )
        assert merged == {"u": {"a": '{"b": 9}'}}

    def test_agreeing_struct_owners_subflag_kept(self, loader: ConfargLoader) -> None:
        """A sub-flag the structs agree on keeps the common coercion, at depth too."""
        merged = loader.merge(_NestedOwnersAgree, argv=["--u.a.b", "7"], env={}, config_flag="")
        assert merged == {"u": {"a": {"b": 7}}}

    def test_disagreeing_subclasses_raw_without_tag(self, loader: ConfargLoader) -> None:
        """Subclasses disagreeing about a subclass-only field hit the same rule.

        Vanilla's ``_subclass_field_type`` answers ``str`` when the subclasses
        disagree; the adapters' subclass walks each coerced by their own field,
        the last one standing (BUG-84).
        """
        merged = loader.merge(_ExtraHolder, argv=["--x.extra", "7"], env={}, config_flag="")
        assert merged == {"x": {"extra": "7"}}

    def test_disagreeing_subclasses_raw_with_tag(self, loader: ConfargLoader) -> None:
        """A tag on the base does not change the disagreeing-subclass answer."""
        merged = loader.merge(
            _ExtraHolder,
            argv=["--x.class", f"{__name__}._ExtraInt", "--x.extra", "7"],
            env={},
            config_flag="",
        )
        assert merged == {"x": {"class": f"{__name__}._ExtraInt", "extra": "7"}}

    def test_disagreeing_owners_raw_at_union_root(self, loader: ConfargLoader) -> None:
        """A union root's variants own the flag together, the same rule included."""
        merged = loader.merge(_OwnersRoot, argv=["--a", "7"], env={}, config_flag="")
        assert merged == {"a": "7"}

    def test_disagreeing_owners_build_at_union_root(self, loader: ConfargLoader) -> None:
        """The union root's raw token still builds, coerced by the variant the tag names."""
        result = loader.load(
            _OwnersRoot,
            argv=["--class", f"{__name__}._OwnerInt", "--a", "7"],
            env={},
            config_flag="",
        )
        assert result == _OwnerInt(a=7)


# ---------------------------------------------------------------------------
# Root-level union target (target IS a union, not a struct containing one)
# ---------------------------------------------------------------------------


class TestUnionRootContract:
    """Union-of-structs root targets work identically in every integration."""

    def test_union_root_flags_built(self) -> None:
        """build_static_flags generates --class and all variant fields for a union root."""
        flags = build_static_flags(_RootDBConfig, union_tag="class", config_flag="")
        names = {f.name for f in flags}
        assert {"class", "dbpath", "host", "port", "name"} <= names

    def test_union_root_flags_registered(self, populating_loader: ConfargLoader) -> None:
        """populate_* registers --class and all variant fields for a union root."""
        flags = populating_loader.registered_flags(_RootDBConfig, config_flag="")
        assert flags is not None
        assert {"class", "dbpath", "host", "port", "name"} <= flags

    def test_union_root_round_trip_sqlite(self, loader: ConfargLoader) -> None:
        """--dbpath alone selects the SQLite variant without needing --class."""
        result = loader.load(_RootDBConfig, argv=["--dbpath", "/tmp/x.db"], env={}, config_flag="")
        assert isinstance(result, _RootSQLite)
        assert result.dbpath == "/tmp/x.db"

    def test_union_root_round_trip_db_server(self, loader: ConfargLoader) -> None:
        """DB server fields alone select the server variant without needing --class."""
        result = loader.load(
            _RootDBConfig,
            argv=["--host", "db.example.com", "--port", "5432", "--name", "mydb"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _RootDBServer)
        assert result.host == "db.example.com"
        assert result.port == 5432
        assert result.name == "mydb"

    def test_union_root_explicit_class_tag(self, loader: ConfargLoader) -> None:
        """--class overrides structural disambiguation for the union root."""
        result = loader.load(
            _RootDBConfig,
            argv=["--class", f"{__name__}._RootSQLite", "--dbpath", "/tmp/x.db"],
            env={},
            config_flag="",
        )
        assert isinstance(result, _RootSQLite)
        assert result.dbpath == "/tmp/x.db"

    def test_union_root_literal_discriminator_choices_merged(self) -> None:
        """A Literal discriminator shared across variants accepts every variant's value.

        Each variant contributes a ``type`` FlagSpec with its own single-member choices;
        these must be merged into one flag rather than first-wins-collapsed.
        """
        flags = build_static_flags(_RootTypedDBConfig, union_tag="class", config_flag="")
        type_specs = [f for f in flags if f.name == "type"]
        assert len(type_specs) == 1
        assert set(type_specs[0].choices or []) == {"mariadb", "postgres"}

    def test_union_root_literal_discriminator_selects_variant(self, loader: ConfargLoader) -> None:
        """--type <value> selects the matching union variant regardless of order."""
        maria = loader.load(_RootTypedDBConfig, argv=["--type", "mariadb", "--host", "h"], env={}, config_flag="")
        assert isinstance(maria, _RootMariaDBTyped)
        postgres = loader.load(_RootTypedDBConfig, argv=["--type", "postgres", "--host", "h"], env={}, config_flag="")
        assert isinstance(postgres, _RootPostgreTyped)


# ---------------------------------------------------------------------------
# merge() — the raw-dict variant
# ---------------------------------------------------------------------------


@dataclass
class _CoercedLeaves:
    """Leaves whose eager coercion yields a non-native type (``Path``, ``Enum``)."""

    out: Path = Path("default.txt")
    color: Color = Color.RED


_UUID_TEXT = "12345678-1234-5678-1234-567812345678"
_NIL_UUID = UUID(int=0)


@dataclass
class _RegisteredLeaf:
    """A field whose type is a leaf only because ``register_leaf_type`` says so."""

    id: UUID = _NIL_UUID


class TestMergeContract:
    """merge_* returns the raw merged dict, identically in every integration."""

    def test_returns_dict(self, loader: ConfargLoader) -> None:
        """Merge returns a dict, not a dataclass instance."""
        result = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        assert isinstance(result, dict)

    def test_cli_values_in_dict(self, loader: ConfargLoader) -> None:
        """CLI-provided values appear in the returned dict, eagerly coerced.

        Every integration coerces typed leaf values at merge time, so the raw
        dict carries ``port`` as the int ``9090`` regardless of which backend
        produced it (vanilla and adapters agree byte-for-byte).
        """
        result = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        assert result["host"] == "myhost"
        assert result["port"] == 9090

    def test_expressions_preserved(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Expression strings from config files are kept intact (not resolved)."""
        cfg = tmp_yaml("host: myhost\nport: '${host}'\n")
        result = loader.merge(Simple, argv=["--config", str(cfg)], env={})
        assert result["port"] == "${host}"

    def test_round_trip_equivalence(self, loader: ConfargLoader) -> None:
        """build(target, merge(...)) equals load(...) for the same inputs."""
        argv = ["--host", "myhost", "--port", "9090"]
        raw = loader.merge(Simple, argv=argv, env={})
        assert confarg.build(Simple, raw) == loader.load(Simple, argv=argv, env={})

    def test_dump_file_from_raw_dict(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """dump_file accepts the raw dict returned by merge without raising."""
        out = tmp_path / "out.yaml"
        raw = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        confarg.dump_file(raw, out)
        assert out.exists()

    @pytest.mark.parametrize("suffix", [".yaml", ".json", ".toml"])
    def test_dump_file_from_raw_dict_with_coerced_leaves(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        suffix: str,
    ) -> None:
        """A merged dict holding an eagerly coerced ``Path``/``Enum`` leaf dumps in every format.

        Leaves are coerced at merge time, so the dict carries a ``Path`` and an
        ``Enum`` member that no config-file writer accepts; both must leave as
        the scalars a config file would have carried.
        """
        out = tmp_path / f"snap{suffix}"
        raw = loader.merge(_CoercedLeaves, argv=["--out", "sub/x.txt", "--color", "blue"], env={})
        confarg.dump_file(raw, out)

        reloaded = loader.merge(_CoercedLeaves, argv=[], env={}, files=[out])
        assert reloaded == {"out": str(Path("sub/x.txt")), "color": "blue"}
        assert confarg.build(_CoercedLeaves, raw) == confarg.build(_CoercedLeaves, reloaded)

    @pytest.mark.parametrize("suffix", [".yaml", ".json", ".toml"])
    def test_dump_file_with_a_registered_leaf_type(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        suffix: str,
        leaf_registry: None,
    ) -> None:
        """A type registered with ``register_leaf_type`` dumps as a scalar in every integration.

        Registration makes a type a leaf in both directions, so the merged
        ``UUID`` must leave as the string a config file would have carried —
        identically whichever front-end produced the dict.
        """
        confarg.register_leaf_type(UUID, UUID)
        out = tmp_path / f"snap{suffix}"
        raw = loader.merge(_RegisteredLeaf, argv=["--id", _UUID_TEXT], env={})
        assert raw == {"id": UUID(_UUID_TEXT)}
        confarg.dump_file(raw, out)

        reloaded = loader.merge(_RegisteredLeaf, argv=[], env={}, files=[out])
        assert reloaded == {"id": _UUID_TEXT}
        assert confarg.build(_RegisteredLeaf, raw) == confarg.build(_RegisteredLeaf, reloaded)

    def test_dump_file_round_trip_via_instance(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Round-tripping through a built instance gives back the same config."""
        out = tmp_path / "out.yaml"
        raw = loader.merge(Simple, argv=["--host", "myhost", "--port", "9090"], env={})
        confarg.dump_file(confarg.build(Simple, raw), out)
        reloaded = confarg.load(Simple, argv=[], files=[out], env={})
        assert reloaded.host == "myhost"
        assert reloaded.port == 9090


# ---------------------------------------------------------------------------
# Collection patches — list index/append/delete and dict subkeys via CLI
# ---------------------------------------------------------------------------


@dataclass
class _PatchSqlite:
    """List-element struct for collection-patch tests."""

    dbpath: str = ""


@dataclass
class _WithUsers:
    """List-of-str field with a default base."""

    users: list[str] = dataclasses.field(default_factory=list)


@dataclass
class _WithLang:
    """Fixed-length tuple field."""

    lang: tuple[str, str] = ("en", "EN")


@dataclass
class _WithPair:
    """Fixed-length tuple field with no default (built element-by-element from CLI)."""

    input: tuple[int, int]


@dataclass
class _WithTriple:
    """Fixed-length 3-tuple field — completed from a shorter config base via index patch."""

    input: tuple[int, int, int]


@dataclass
class _WithDbs:
    """List-of-struct field."""

    dbs: list[_PatchSqlite] = dataclasses.field(default_factory=list)


@dataclass
class _WithMap:
    """Dict field (bare whole-value flag statically; keys patched via argv subkeys)."""

    data: dict[str, int] = dataclasses.field(default_factory=dict)


@dataclass
class _WithStrBools:
    """List-of-scalar-union field — elements are subject to the stealing rule."""

    input: list[str | bool] = dataclasses.field(default_factory=list)


@dataclass
class _WithListMap:
    """Dict field whose *values* are collections, so a subkey flag is itself multi-token."""

    data: dict[str, list[int]] = dataclasses.field(default_factory=dict)


@dataclass
class _WithGrid:
    """List-of-list field — element is itself a sequence (nested index patch)."""

    grid: list[list[int]] = dataclasses.field(default_factory=list)


@dataclass
class _WithPairs:
    """List-of-tuple field — element is a fixed-length sequence (nested index patch)."""

    pairs: list[tuple[int, int]] = dataclasses.field(default_factory=list)


class TestCollectionPatchContract:
    """List index/append/delete and dict-subkey CLI patches resolve identically everywhere.

    These were vanilla-only before ``build_dynamic_flags`` registered the
    argv-derived patch flags and ``_parse_cli(..., patch_only=True)`` applied
    them in command order on top of the framework parse result.
    """

    def test_index_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.N value`` replaces a single list element."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.0", "allan"], env={})
        assert cfg.users == ["allan", "bob", "claire"]

    def test_negative_index_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Negative indices count from the end."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.-1", "billy"], env={})
        assert cfg.users == ["alice", "bob", "billy"]

    def test_index_set_beside_a_plain_occurrence_records_the_op(self, loader: ConfargLoader) -> None:
        """An index patch over a list the same channel collected records, not applies (BUG-67).

        Within one channel the op is a *record*: vanilla's ``_set_nested`` promotes the
        stored list into the ``'*'`` base and sets the index key beside it, leaving
        ``build()`` to apply it. The adapters' join deep-merged the patch scan over the
        collected value, and ``_deep_merge`` applied the op on the spot — the same list
        built, but a merged dict that is not byte-identical, with the base list hidden
        from no one but the op that consumed it.
        """
        argv = ["--users", "alice", "--users", "bob", "--users.0", "allan"]
        assert loader.merge(_WithUsers, argv=argv, env={}) == {"users": {"*": ["alice", "bob"], "0": "allan"}}
        assert loader.load(_WithUsers, argv=argv, env={}).users == ["allan", "bob"]

    def test_nested_index_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Indices compose with sub-field paths (``--dbs.1.dbpath``)."""
        base = tmp_yaml("dbs:\n  - dbpath: a\n  - dbpath: b\n")
        cfg = loader.load(_WithDbs, argv=["--config", str(base), "--dbs.1.dbpath", "z"], env={})
        assert cfg.dbs == [_PatchSqlite("a"), _PatchSqlite("z")]

    def test_index_force_cast_bypasses_stealing(self, loader: ConfargLoader) -> None:
        """``--field.N.str`` force-casts a single list element, bypassing the stealing rule.

        The cast path (``input.1``) is itself a collection-patch path, so it is applied by the
        argv-order patch scan, not the flat collector — the whole reason both the patch-flag
        registration and ``_parse_cli(patch_only=True)`` route the decision through
        ``_is_collection_patch_path`` rather than assuming every cast is a plain-field cast.
        """
        cfg = loader.load(
            _WithStrBools,
            argv=["--input.0", "hello", "--input.1.str", "yes", "--input.2", "well"],
            env={},
        )
        assert cfg.input == ["hello", "yes", "well"]

    def test_index_force_cast_pins_first_element(self, loader: ConfargLoader) -> None:
        """``--field.0.str yes`` pins element 0 to the string 'yes' rather than stealing to True."""
        cfg = loader.load(_WithStrBools, argv=["--input.0.str", "yes"], env={})
        assert cfg.input == ["yes"]

    def test_index_into_list_element_patches_not_replaces(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--grid.0.0`` patches the inner list element, not replaces the whole inner list."""
        base = tmp_yaml("grid:\n  - [1, 2, 3]\n  - [4, 5]\n")
        cfg = loader.load(_WithGrid, argv=["--config", str(base), "--grid.0.0", "42"], env={})
        assert cfg.grid == [[42, 2, 3], [4, 5]]

    def test_index_into_tuple_element_patches_not_replaces(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--pairs.0.1`` patches one slot of an inner tuple element, not the whole tuple."""
        base = tmp_yaml("pairs:\n  - [1, 2]\n  - [3, 4]\n")
        cfg = loader.load(_WithPairs, argv=["--config", str(base), "--pairs.0.1", "9"], env={})
        assert cfg.pairs == [(1, 9), (3, 4)]

    def test_fixed_arity_element_bare_occurrence_is_a_missing_value(
        self,
        space_sep_loader: ConfargLoader,
    ) -> None:
        """A fixed-arity element flag refuses its bare occurrence, beside a valued one too (BUG-74).

        The patch scan replays vanilla's consumption off argv, so the refusal the
        scan would raise never has to be reached: cyclopts asserts inside its own
        parse on this argv first, and the pre-parse refusal is what keeps the five
        front-ends on vanilla's answer.
        """
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pairs.0'")):
            space_sep_loader.merge(_WithPairs, argv=["--pairs.0", "--pairs.0", "3", "4"], env={})
        with pytest.raises(ConfargError, match=re.escape("Missing value for '--pairs.0'")):
            space_sep_loader.merge(_WithPairs, argv=["--pairs.0", "1", "2", "--pairs.0"], env={})

    def test_tuple_index_set(self, loader: ConfargLoader) -> None:
        """Tuple elements are patchable by index."""
        cfg = loader.load(_WithLang, argv=["--lang.1", "FR"], env={})
        assert cfg.lang == ("en", "FR")

    def test_tuple_negative_index_set(self, loader: ConfargLoader) -> None:
        """A negative index resolves against the fixed tuple length (``-1`` → last slot)."""
        cfg = loader.load(_WithLang, argv=["--lang.-1", "FR"], env={})
        assert cfg.lang == ("en", "FR")

    def test_tuple_index_patch_beside_a_plain_occurrence_records_the_op(self, loader: ConfargLoader) -> None:
        """A fixed tuple's index patch rides the collected tokens as the ``'*'`` base (BUG-67).

        Same defect as the varlen spelling: the join applied the op to the collected
        list instead of recording it, so the adapters held ``[en, FR]`` where vanilla
        holds the operation ``{'*': [fr, FR], '0': en}``.
        """
        argv = ["--lang", "fr", "FR", "--lang.0", "en"]
        assert loader.merge(_WithLang, argv=argv, env={}) == {"lang": {"*": ["fr", "FR"], "0": "en"}}
        assert loader.load(_WithLang, argv=argv, env={}).lang == ("en", "FR")

    def test_tuple_build_with_mixed_indices_no_base(self, loader: ConfargLoader) -> None:
        """A fixed tuple builds element-by-element from mixed positive/negative indices."""
        cfg = loader.load(_WithPair, argv=["--input.0", "0", "--input.-1", "1"], env={})
        assert cfg.input == (0, 1)

    def test_tuple_completed_from_shorter_config_base(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A config base shorter than the tuple is completed by an index patch past its end.

        The merge layer cannot tell a list from a fixed tuple, so an index outside the
        base list is deferred to build(), which fills the declared tuple slot instead of
        raising the list replacement-only error.
        """
        base = tmp_yaml("input: [1, 2]\n")
        cfg = loader.load(_WithTriple, argv=["--config", str(base), "--input.2", "3"], env={})
        assert cfg.input == (1, 2, 3)

    def test_list_index_past_config_base_still_errors(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The same out-of-base index on a *list* field still errors (replacement-only).

        Confirms the deferral only relocated the list error to build() — it did not
        weaken list semantics.
        """
        base = tmp_yaml("users: [alice, bob]\n")
        with pytest.raises(ConfargError):
            loader.load(_WithUsers, argv=["--config", str(base), "--users.4", "carol"], env={})

    def test_append_single(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field+ value`` appends one element."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+", "david"], env={})
        assert cfg.users == ["alice", "bob", "david"]

    def test_append_no_items(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A bare ``--field+`` appends nothing and leaves the lower-priority list alone."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+"], env={})
        assert cfg.users == ["alice", "bob"]

    def test_append_no_items_before_another_flag(self, loader: ConfargLoader, tmp_yaml) -> None:
        """An empty append does not swallow the flag that follows it."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+", "--users.0", "allan"], env={})
        assert cfg.users == ["allan", "bob"]

    def test_append_valued_then_bare(self, loader: ConfargLoader, tmp_yaml) -> None:
        """One argv may spell the same append both ways; the bare occurrence appends nothing."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+", "david", "--users+"], env={})
        assert cfg.users == ["alice", "bob", "david"]

    def test_append_bare_then_valued(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The bare occurrence is honored wherever it stands, before the valued one included."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+", "--users+", "david"], env={})
        assert cfg.users == ["alice", "bob", "david"]

    def test_append_beside_a_plain_occurrence_records_the_op(self, loader: ConfargLoader) -> None:
        """An append over a list the same channel collected records, not applies (BUG-67).

        Vanilla's ``_merge_append_ops`` wraps the stored list as the ``'*'`` base and
        carries the appended items under ``'+'`` beside it; the adapters' join applied
        the append on the spot.
        """
        argv = ["--users", "alice", "--users", "bob", "--users+", "carol"]
        assert loader.merge(_WithUsers, argv=argv, env={}) == {"users": {"*": ["alice", "bob"], "+": ["carol"]}}
        assert loader.load(_WithUsers, argv=argv, env={}).users == ["alice", "bob", "carol"]

    def test_append_bare_twice(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Two bare appends append nothing twice, rather than reading as a repeated flag."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users+", "--users+"], env={})
        assert cfg.users == ["alice", "bob"]

    def test_bare_subkey_with_a_collection_value_type(self, loader: ConfargLoader) -> None:
        """``--data.k`` with nothing after it stores the empty collection under the key.

        The subkey flag inherits the value type's shape, so it stands bare exactly when a
        field flag of that type would (BUG-38).
        """
        cfg = loader.load(_WithListMap, argv=["--data.k"], env={})
        assert cfg.data == {"k": []}

    def test_bare_element_flag_with_a_collection_element_type(self, loader: ConfargLoader) -> None:
        """``--grid.0`` with nothing after it stores the empty collection at index 0."""
        cfg = loader.load(_WithGrid, argv=["--grid.0"], env={})
        assert cfg.grid == [[]]

    def test_bare_subkey_with_a_scalar_value_type_is_rejected(self, loader: ConfargLoader) -> None:
        """A scalar-valued subkey takes exactly one token, so the bare form stays an error."""
        with pytest.raises((ConfargError, SystemExit)):
            loader.load(_WithMap, argv=["--data.k"], env={})

    def test_delete_index(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.N-`` removes the element at N."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.0-"], env={})
        assert cfg.users == ["bob", "claire"]

    def test_delete_negative_index(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Negative-index deletes count from the end."""
        base = tmp_yaml("users: [alice, bob, claire]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.-2-"], env={})
        assert cfg.users == ["alice", "claire"]

    def test_index_delete_beside_a_plain_occurrence_records_the_op(self, loader: ConfargLoader) -> None:
        """An index delete over a list the same channel collected records, not applies (BUG-67).

        Vanilla's ``_accumulate_list_delete`` promotes the stored list into the
        ``'*'`` base and accumulates the index under ``'-'``; the adapters' join deleted
        the element from the collected list on the spot.
        """
        argv = ["--users", "alice", "--users", "bob", "--users.0-"]
        assert loader.merge(_WithUsers, argv=argv, env={}) == {"users": {"*": ["alice", "bob"], "-": [0]}}
        assert loader.load(_WithUsers, argv=argv, env={}).users == ["bob"]

    def test_dict_subkey_set(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.key value`` adds/overrides a dict entry (coerced to the value type)."""
        base = tmp_yaml("data: {a: 1, b: 2}\n")
        cfg = loader.load(_WithMap, argv=["--config", str(base), "--data.c", "3"], env={})
        assert cfg.data == {"a": 1, "b": 2, "c": 3}

    def test_dict_key_delete(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``--field.key-`` removes a dict entry."""
        base = tmp_yaml("data: {a: 1, b: 2}\n")
        cfg = loader.load(_WithMap, argv=["--config", str(base), "--data.a-"], env={})
        assert cfg.data == {"b": 2}

    def test_whole_field_delete_spelled_twice_is_one_delete(self, loader: ConfargLoader) -> None:
        """A delete repeated is the same delete, on every front-end (BUG-78).

        The whole-field delete is idempotent anyway, but a value-less cyclopts
        parameter refuses a second occurrence with a usage error where the other
        front-ends take it in stride.  The delete's value never reaches a parse
        result the collector reads — the patch scan reads argv directly — so
        repetition must not be a framework question.
        """
        cfg = loader.load(_WithUsers, argv=["--users", "a", "--users-", "--users-", "--users", "b"], env={})
        assert cfg.users == ["b"]

    def test_dict_key_delete_spelled_twice_is_one_delete(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A repeated dict-key delete is the same delete too (BUG-78)."""
        base = tmp_yaml("data: {a: 1, b: 2}\n")
        cfg = loader.load(_WithMap, argv=["--config", str(base), "--data.a-", "--data.a-"], env={})
        assert cfg.data == {"b": 2}

    def test_whole_field_delete_then_set(self, loader: ConfargLoader) -> None:
        """A whole-field delete loses to the plain flag that follows it (BUG-53).

        The delete drops the field and the later flag sets it again — the argv order
        vanilla honors, and the order that clears a configured list to put something
        else in its place.
        """
        cfg = loader.load(_WithUsers, argv=["--users-", "--users", "carol"], env={})
        assert cfg.users == ["carol"]

    def test_whole_field_delete_then_set_over_config(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The delete-then-set order holds with a config file below it (BUG-53)."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users-", "--users", "carol"], env={})
        assert cfg.users == ["carol"]

    def test_set_then_whole_field_delete(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The reverse order keeps the delete: the earlier set is ended by it."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users", "carol", "--users-"], env={})
        assert cfg.users == []

    def test_append_before_plain_set_discarded(self, loader: ConfargLoader) -> None:
        """A plain occurrence replaces the whole list, discarding the append before it (BUG-54)."""
        cfg = loader.load(_WithUsers, argv=["--users+", "billy", "--users", "carol"], env={})
        assert cfg.users == ["carol"]

    def test_index_delete_before_plain_set_discarded(self, loader: ConfargLoader, tmp_yaml) -> None:
        """An index delete before a plain occurrence dies with the list it patched (BUG-54)."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.0-", "--users", "carol"], env={})
        assert cfg.users == ["carol"]

    def test_index_set_before_plain_set_discarded(self, loader: ConfargLoader, tmp_yaml) -> None:
        """An index set before a plain occurrence dies with the list it patched (BUG-54)."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(_WithUsers, argv=["--config", str(base), "--users.0", "zed", "--users", "carol"], env={})
        assert cfg.users == ["carol"]

    def test_set_delete_then_set_starts_new_list(self, loader: ConfargLoader) -> None:
        """A whole-field delete ends the list being built, so the next occurrence starts over (BUG-76).

        A framework's parse result has accumulated every plain occurrence into one
        value, so the token spelled before the delete survives *inside* the value of
        the occurrence after it unless the collector reads the occurrences back off
        argv, where the delete still stands between them.
        """
        cfg = loader.load(_WithUsers, argv=["--users", "y", "--users-", "--users", "b"], env={})
        assert cfg.users == ["b"]

    def test_set_delete_then_two_sets_start_new_list(self, loader: ConfargLoader) -> None:
        """Every occurrence after the delete accumulates together, none from before it (BUG-76)."""
        cfg = loader.load(
            _WithUsers,
            argv=["--users", "y", "--users-", "--users", "b", "--users", "c"],
            env={},
        )
        assert cfg.users == ["b", "c"]

    def test_set_delete_then_set_over_config(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The new list the post-delete occurrence starts replaces the configured one too (BUG-76)."""
        base = tmp_yaml("users: [alice, bob]\n")
        cfg = loader.load(
            _WithUsers,
            argv=["--config", str(base), "--users", "y", "--users-", "--users", "b"],
            env={},
        )
        assert cfg.users == ["b"]

    def test_set_delete_then_bare_occurrence_clears(self, loader: ConfargLoader) -> None:
        """A bare occurrence after the delete clears the list, not resurrects the old tokens (BUG-76).

        The bare occurrence contributes no token, so the flat value still holds the
        pre-delete tokens alone; only argv says the user retyped the flag after the
        delete.
        """
        cfg = loader.load(_WithUsers, argv=["--users", "y", "--users-", "--users"], env={})
        assert cfg.users == []

    def test_union_set_delete_then_set_starts_new_list(self, loader: ConfargLoader) -> None:
        """The reset holds on a union's sequence variant, where one token is the scalar (BUG-76)."""
        cfg = loader.load(_WithStrList, argv=["--input", "y", "--input-", "--input", "b"], env={})
        assert cfg.input == "b"

    def test_interleaved_append_and_patch_newest(self, loader: ConfargLoader) -> None:
        """Append-empty-then-fill-by-(-1) repeats resolve in command order.

        The hardest ordering case: the framework parse result cannot represent
        the two interleaved ``--dbs.-1.dbpath`` patches, so values are read from
        argv in order via the patch scan.
        """
        cfg = loader.load(
            _WithDbs,
            argv=["--dbs+", "{}", "--dbs.-1.dbpath", "db1", "--dbs+", "{}", "--dbs.-1.dbpath", "db2"],
            env={},
        )
        assert cfg.dbs == [_PatchSqlite("db1"), _PatchSqlite("db2")]


class TestCollectionPatchListSyntax:
    """Multi-value appends follow each framework's list-argument convention.

    Whole-field list values keep their framework syntax (space-separated for
    argparse/cyclopts, repeated flags for click); the append/delete ordering on
    top is shared.
    """

    def test_append_multi_space_separated(self, space_sep_loader: ConfargLoader, tmp_yaml) -> None:
        """Space-separated multi-value append (argparse/cyclopts/vanilla)."""
        base = tmp_yaml("users: [john]\n")
        cfg = space_sep_loader.load(_WithUsers, argv=["--config", str(base), "--users+", "billy", "alice"], env={})
        assert cfg.users == ["john", "billy", "alice"]

    def test_append_multi_repeated(self, repeated_loader: ConfargLoader, tmp_yaml) -> None:
        """Repeated-flag multi-value append (click/cyclopts)."""
        base = tmp_yaml("users: [john]\n")
        cfg = repeated_loader.load(
            _WithUsers,
            argv=["--config", str(base), "--users+", "billy", "--users+", "alice"],
            env={},
        )
        assert cfg.users == ["john", "billy", "alice"]

    def test_set_append_delete_order_space_sep(self, space_sep_loader: ConfargLoader) -> None:
        """Whole-list set, then append, then delete — applied in command order."""
        cfg = space_sep_loader.load(
            _WithUsers,
            argv=["--users", "john", "--users+", "billy", "alice", "--users.-2-"],
            env={},
        )
        assert cfg.users == ["john", "alice"]

    def test_set_append_delete_order_repeated(self, repeated_loader: ConfargLoader) -> None:
        """Same ordering via click's repeated-flag list syntax."""
        cfg = repeated_loader.load(
            _WithUsers,
            argv=["--users", "john", "--users+", "billy", "--users+", "alice", "--users.-2-"],
            env={},
        )
        assert cfg.users == ["john", "alice"]


# ---------------------------------------------------------------------------
# Expressions over CLI-provided numbers (eager leaf coercion)
# ---------------------------------------------------------------------------


@dataclass
class _ExprConfig:
    """Config whose ``derived`` field is an expression over ``base``."""

    base: int = 0
    derived: int = 0


@dataclass
class _NestedExprBlock:
    """Block whose ``derived`` reads a sibling without naming the block it sits in."""

    base: int = 0
    derived: int = 0


@dataclass
class _NestedExprConfig:
    """Root carrying a same-named ``base``, so a wrong anchor gives a visibly wrong answer."""

    base: int = 99
    block: _NestedExprBlock = dataclasses_field(default_factory=_NestedExprBlock)


class TestExpressionOverCliContract:
    """A config expression resolves against a CLI-overridden numeric field in every backend.

    Regression for the deferred-coercion gap: adapters used to leave the CLI
    value as a string, so ``${base * 3}`` raised; eager leaf coercion fixes it.
    """

    def test_expr_references_cli_number(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A CLI int override flows into a config expression and resolves to an int."""
        cfg = tmp_yaml("base: 10\nderived: '${base * 3}'\n")
        result = loader.load(_ExprConfig, argv=["--config", str(cfg), "--base", "8"], env={})
        assert result.base == 8
        assert result.derived == 24

    def test_relative_expr_in_a_file_reads_its_own_block(self, loader: ConfargLoader, tmp_yaml) -> None:
        """${.base} is the block's own base, never the same-named field at the root."""
        cfg = tmp_yaml("base: 99\nblock:\n  base: 10\n  derived: '${.base * 3}'\n")
        result = loader.load(_NestedExprConfig, argv=["--config", str(cfg), "--block.base", "8"], env={})
        assert result.block.derived == 24

    def test_relative_expr_from_the_cli_is_anchored_where_it_lands(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A flag has no writing file, so its dots count from the path it is set at."""
        cfg = tmp_yaml("base: 99\nblock:\n  base: 10\n  derived: 0\n")
        result = loader.load(
            _NestedExprConfig,
            argv=["--config", str(cfg), "--block.derived", "${.base * 3}"],
            env={},
        )
        assert result.block.derived == 30


# ---------------------------------------------------------------------------
# Expressions into value-restricted and registered-leaf fields
# ---------------------------------------------------------------------------


class _Colour(Enum):
    """Enum whose members double as the values an expression may resolve to."""

    RED = "red"
    BLUE = "blue"


@dataclass
class _ChoiceConfig:
    """Config pairing a free-form ``name`` with domain-restricted ``lit`` / ``colour``."""

    name: str = "a"
    lit: Literal["a", "b"] = "a"
    colour: _Colour = _Colour.RED


@dataclass
class _LeafConfig:
    """Config whose ``log`` is a registered leaf type (``Path``) fed by an expression."""

    base: str = "/app"
    log: Path = dataclasses.field(default_factory=lambda: Path("."))


class TestExpressionIntoRestrictedFieldContract:
    """A ``${...}`` token reaches a Literal/Enum field through every front-end.

    Regression for the parse-time ``choices`` divergence: the adapters used to
    hand ``FlagSpec.choices`` straight to argparse / ``click.Choice`` /
    ``Literal[...]``, which rejected ``${name}`` before confarg saw it, while
    vanilla (and the env and config-file channels of every front-end) accepted
    it.  An expression's value is unknown until ``resolve_expressions`` runs, so
    the domain check belongs to ``build()``.
    """

    def test_expr_into_literal_field(self, loader: ConfargLoader) -> None:
        """An expression naming another field resolves into a Literal field."""
        cfg = loader.load(_ChoiceConfig, argv=["--name", "b", "--lit", "${name}"], env={})
        assert cfg.lit == "b"

    def test_expr_into_enum_field(self, loader: ConfargLoader) -> None:
        """An expression naming another field resolves into an Enum field."""
        cfg = loader.load(_ChoiceConfig, argv=["--name", "blue", "--colour", "${name}"], env={})
        assert cfg.colour is _Colour.BLUE

    def test_expr_resolving_outside_domain_fails_in_build(self, loader: ConfargLoader) -> None:
        """Deferred, not dropped: an expression resolving off-domain still fails, in build()."""
        with pytest.raises(TypeCoercionError, match="Literal"):
            loader.load(_ChoiceConfig, argv=["--name", "zz", "--lit", "${name}"], env={})

    def test_expr_into_registered_leaf_field(self, loader: ConfargLoader) -> None:
        """An expression survives eager coercion to a registered leaf type (``Path``).

        ``Path("${base}/logs")`` coerces *successfully*, so before the explicit
        expression check in ``_try_coerce`` the token became a ``Path`` that
        ``resolve_expressions`` (which scans ``str`` leaves only) never revisited
        — silently yielding a literal ``${base}/logs`` path.
        """
        cfg = loader.load(_LeafConfig, argv=["--base", "/app", "--log", "${base}/logs"], env={})
        assert cfg.log == Path("/app/logs")

    def test_registered_leaf_expr_matches_config_file_channel(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The CLI, env and config-file channels agree on a leaf-typed expression."""
        cfg_file = tmp_yaml("""
base: /app
log: '${base}/logs'
""")
        from_file = loader.load(_LeafConfig, argv=["--config", str(cfg_file)], env={})
        from_env = loader.load(_LeafConfig, argv=[], env={"X_BASE": "/app", "X_LOG": "${base}/logs"}, env_prefix="X_")
        from_cli = loader.load(_LeafConfig, argv=["--base", "/app", "--log", "${base}/logs"], env={})
        assert from_file.log == from_env.log == from_cli.log == Path("/app/logs")


# ---------------------------------------------------------------------------
# Callable bind on a class __call__ parameter
# ---------------------------------------------------------------------------


class _Greeter:
    """Callable instance: ``greeting`` is a constructor kwarg, ``punct`` a __call__ bind."""

    def __init__(self, greeting: str) -> None:
        self.greeting = greeting

    def __call__(self, name: str, punct: str) -> str:
        return f"{self.greeting}, {name}{punct}"


@dataclass
class _CallableConfig:
    """Config with a single callable field."""

    fn: Callable[[str], str]


@dataclass
class _OptCallableConfig:
    """Config whose callable field is optional: optionality is not a statement about syntax."""

    fn: Callable[[str], str] | None = None


class TestCallableBindContract:
    """``--field.bind.<param>`` for a class's ``__call__`` parameter is registered everywhere.

    In ``.class`` mode the constructor params become ``--field.<param>`` factory
    kwargs and the instance's ``__call__`` params become ``--field.bind.<param>``.
    """

    def test_bind_call_param(self, loader: ConfargLoader) -> None:
        """A class chosen via .class binds a __call__ param through --field.bind.<param>."""
        cfg = loader.load(
            _CallableConfig,
            argv=["--fn.class", f"{__name__}._Greeter", "--fn.greeting", "Hi", "--fn.bind.punct", "!"],
            env={},
        )
        assert cfg.fn("world") == "Hi, world!"


# ---------------------------------------------------------------------------
# The bare-string shorthand refined by a sibling flag
# ---------------------------------------------------------------------------


def _shout(name: str, punct: str = ".") -> str:
    """Module-level function whose second parameter is a bind target."""
    return f"{name.upper()}{punct}"


@dataclass
class _ScalarThenSubkey:
    """A dict field: it has no bare-scalar shorthand, so a scalar there means nothing."""

    d: dict[str, str] | None = None


@dataclass
class _CallableHolder:
    """A callable field named so no path segment reads as a directive."""

    hook: Callable[[str], str] | None = None


@dataclass
class _NestedCallable:
    """A callable field one level down, so the shorthand sits below the root."""

    inner: _CallableHolder = dataclasses_field(default_factory=_CallableHolder)


class TestShorthandRefinementContract:
    """A whole value followed by a sibling subkey resolves, in every channel and front-end.

    ``--fn <path>`` is the documented shorthand for ``--fn.fn <path>``, so a sibling
    ``--fn.bind.<param>`` refines it exactly as it refines the explicit opener.  A field
    with no such shorthand keeps last-write-wins: the subkey opens the scalar away.
    """

    def test_shorthand_then_bind_via_cli(self, loader: ConfargLoader) -> None:
        """The shorthand names the target; ``--fn.bind.<param>`` partially applies it."""
        cfg = loader.load(
            _CallableConfig,
            argv=["--fn", f"{__name__}._shout", "--fn.bind.punct", "!"],
            env={},
        )
        assert cfg.fn("hi") == "HI!"

    def test_shorthand_matches_explicit_opener(self, loader: ConfargLoader) -> None:
        """``--fn X`` and ``--fn.fn X`` merge to the same dict once a bind flag joins them."""
        shorthand = loader.merge(
            _CallableConfig,
            argv=["--fn", f"{__name__}._shout", "--fn.bind.punct", "!"],
            env={},
        )
        explicit = loader.merge(
            _CallableConfig,
            argv=["--fn.fn", f"{__name__}._shout", "--fn.bind.punct", "!"],
            env={},
        )
        assert shorthand == explicit

    def test_shorthand_then_bind_via_env(self, loader: ConfargLoader) -> None:
        """The env channel spells the same pair and reaches the same callable."""
        cfg = loader.load(
            _CallableConfig,
            argv=[],
            env={"APP_FN": f"{__name__}._shout", "APP_FN__BIND__PUNCT": "!"},
            env_prefix="APP_",
        )
        assert cfg.fn("hi") == "HI!"

    def test_explicit_opener_wins_over_shorthand(self, loader: ConfargLoader) -> None:
        """An opener flag beats the shorthand it refines, as it beats a whole-value blob."""
        cfg = loader.load(
            _CallableConfig,
            argv=["--fn", f"{__name__}._shout", "--fn.fn", "str.upper"],
            env={},
        )
        assert cfg.fn("hi") == "HI"

    def test_subkey_opens_a_scalar_with_no_shorthand(self, loader: ConfargLoader) -> None:
        """A dict field has no shorthand, so the later subkey replaces the scalar."""
        merged = loader.merge(_ScalarThenSubkey, argv=["--d", "oops", "--d.c", "x"], env={})
        assert merged == {"d": {"c": "x"}}

    def test_shorthand_survives_a_bind_delete(self, loader: ConfargLoader) -> None:
        """A delete travels with the patch ops, and must still open the shorthand (BUG-24)."""
        merged = loader.merge(_CallableConfig, argv=["--fn", f"{__name__}._shout", "--fn.bind-"], env={})
        assert merged == {"fn": {"fn": f"{__name__}._shout", "bind": DICT_DELETE}}

    def test_shorthand_survives_a_sibling_kwarg_delete(self, loader: ConfargLoader) -> None:
        """Any delete below the shorthand refines it, not only the bind directive."""
        merged = loader.merge(_CallableConfig, argv=["--fn", f"{__name__}._shout", "--fn.punct-"], env={})
        assert merged == {"fn": {"fn": f"{__name__}._shout", "punct": DICT_DELETE}}

    def test_nested_shorthand_survives_a_delete(self, loader: ConfargLoader) -> None:
        """The shorthand is opened wherever it sits, not only at the root."""
        merged = loader.merge(
            _NestedCallable,
            argv=["--inner.hook", f"{__name__}._shout", "--inner.hook.bind-"],
            env={},
        )
        assert merged == {"inner": {"hook": {"fn": f"{__name__}._shout", "bind": DICT_DELETE}}}


# ---------------------------------------------------------------------------
# Escaped directive mode (_fn/_class/_call/_bind) — collision escape, parity across channels
# ---------------------------------------------------------------------------


class _EscBinder:
    """__init__ takes a parameter literally named ``bind``; __call__ takes ``lr``.

    Escaped mode lets the ``__init__`` ``bind`` arg be set (plain ``bind``) while ``_bind``
    partial-applies ``__call__`` — the collision the plain directive names cannot express.
    """

    def __init__(self, bind: int) -> None:
        self.bind = bind

    def __call__(self, lr: int) -> int:
        return self.bind + lr


class _EscOwner:
    """__init__ takes a parameter named ``fn`` (the opener residual), with an instance method."""

    def __init__(self, fn: int) -> None:
        self.fn = fn

    def method(self, x: int) -> int:
        return x + self.fn


@dataclass
class _EscCallableConfig:
    """Config with a bare Callable field (skips arity checks after binding)."""

    fn: Callable


class TestEscapedCallableContract:
    """Escaped directive mode reaches parity across config, env, and CLI (all four front-ends)."""

    def test_compound_init_bind_and_call_bind_via_cli(self, loader: ConfargLoader) -> None:
        """`_class` opener: plain `bind` sets __init__, `_bind.lr` partial-applies __call__."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=["--fn._class", f"{__name__}._EscBinder", "--fn.bind", "5", "--fn._bind.lr", "10"],
            env={},
        )
        assert cfg.fn() == 15  # _EscBinder(bind=5), partial(lr=10) -> 5 + 10

    def test_opener_residual_via_cli(self, loader: ConfargLoader) -> None:
        """`_fn` opener frees a plain `fn` key to be the owning class's constructor kwarg."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=["--fn._fn", f"{__name__}._EscOwner.method", "--fn.fn", "100"],
            env={},
        )
        assert cfg.fn(1) == 101  # _EscOwner(fn=100).method(1) -> 1 + 100

    def test_compound_via_env(self, loader: ConfargLoader) -> None:
        """Env expresses escaped keys via the triple-underscore form (no env code change)."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=[],
            env={
                "APP_FN___CLASS": f"{__name__}._EscBinder",
                "APP_FN__BIND": "5",
                "APP_FN___BIND__LR": "10",
            },
            env_prefix="APP_",
        )
        assert cfg.fn() == 15


class TestMixedDirectiveFormContract:
    """A directive word in the *inactive* form is ordinary data, in every front-end.

    The opener alone selects the mode, so ``_bind`` beside a plain opener — and ``bind``
    beside an escaped one — is a kwarg, not a directive.  The adapters must accept the
    flag and let construction reject the kwarg, exactly as vanilla does (BUG-25).
    """

    def test_escaped_bind_beside_plain_opener_merges_as_data(self, loader: ConfargLoader) -> None:
        """``--fn.fn X --fn._bind.p V`` merges with ``_bind`` left as an ordinary kwarg."""
        merged = loader.merge(
            _EscCallableConfig,
            argv=["--fn.fn", f"{__name__}._shout", "--fn._bind.punct", "!"],
            env={},
        )
        assert merged == {"fn": {"fn": f"{__name__}._shout", "_bind": {"punct": "!"}}}

    def test_escaped_bind_beside_plain_opener_names_the_mixed_form(self, loader: ConfargLoader) -> None:
        """Construction rejects the stray kwarg and the message names both spellings."""
        with pytest.raises(TypeCoercionError, match="_bind") as exc_info:
            loader.load(
                _EscCallableConfig,
                argv=["--fn.fn", f"{__name__}._shout", "--fn._bind.punct", "!"],
                env={},
            )
        assert "'bind'" in str(exc_info.value)

    def test_escaped_bind_beside_bare_shorthand(self, loader: ConfargLoader) -> None:
        """The bare-string shorthand is a plain opener, so it reads ``_bind`` the same way."""
        merged = loader.merge(
            _EscCallableConfig,
            argv=["--fn", f"{__name__}._shout", "--fn._bind.punct", "!"],
            env={},
        )
        assert merged == {"fn": {"fn": f"{__name__}._shout", "_bind": {"punct": "!"}}}

    def test_plain_bind_beside_escaped_opener_merges_as_data(self, loader: ConfargLoader) -> None:
        """The mirror: ``--fn._fn X --fn.bind.p V`` merges with ``bind`` left as a kwarg."""
        merged = loader.merge(
            _EscCallableConfig,
            argv=["--fn._fn", f"{__name__}._shout", "--fn.bind.punct", "!"],
            env={},
        )
        assert merged == {"fn": {"_fn": f"{__name__}._shout", "bind": {"punct": "!"}}}

    def test_plain_bind_beside_escaped_opener_names_the_mixed_form(self, loader: ConfargLoader) -> None:
        """The mirror rejection names both spellings too."""
        with pytest.raises(TypeCoercionError, match="_bind") as exc_info:
            loader.load(
                _EscCallableConfig,
                argv=["--fn._fn", f"{__name__}._shout", "--fn.bind.punct", "!"],
                env={},
            )
        assert "'bind'" in str(exc_info.value)

    def test_active_bind_beside_escaped_opener_still_binds(self, loader: ConfargLoader) -> None:
        """Guard rail: the *active* form keeps working and buys no mixed-form complaint."""
        cfg = loader.load(
            _EscCallableConfig,
            argv=["--fn._fn", f"{__name__}._shout", "--fn._bind.punct", "!"],
            env={},
        )
        assert cfg.fn("hi") == "HI!"


# ---------------------------------------------------------------------------
# Sibling kwargs of a callable that no signature describes
# ---------------------------------------------------------------------------


class TestCallableSiblingKwargContract:
    """A ``--<field>.<name>`` below a ``Callable`` is registered from the path, not a signature.

    The adapters used to register sibling kwargs only from the named target's
    signature, so a name that signature did not carry — or a field with no opener at
    all, which names no target to inspect — was rejected by the framework while
    vanilla merged it and let construction judge it (BUG-28).  Both front-ends must
    fail the same way: not at the parser, but in ``build()``.
    """

    def test_inactive_bind_word_as_a_scalar_merges_as_data(self, loader: ConfargLoader) -> None:
        """``--fn._bind 5`` beside a plain opener is an ordinary kwarg, not a bind subtree."""
        merged = loader.merge(
            _CallableConfig,
            argv=["--fn.fn", f"{__name__}._shout", "--fn._bind", "5"],
            env={},
        )
        assert merged == {"fn": {"fn": f"{__name__}._shout", "_bind": "5"}}

    def test_inactive_bind_word_as_a_scalar_is_rejected_by_construction(self, loader: ConfargLoader) -> None:
        """The error comes from ``build()``, and names the mixed spelling."""
        with pytest.raises(TypeCoercionError, match="_bind"):
            loader.load(_CallableConfig, argv=["--fn.fn", f"{__name__}._shout", "--fn._bind", "5"], env={})

    def test_active_bind_word_as_a_scalar_merges_as_data(self, loader: ConfargLoader) -> None:
        """The mirror: the *active* bind word spelled as a scalar is data the parser stores."""
        merged = loader.merge(
            _CallableConfig,
            argv=["--fn.fn", f"{__name__}._shout", "--fn.bind", "5"],
            env={},
        )
        assert merged == {"fn": {"fn": f"{__name__}._shout", "bind": "5"}}

    def test_active_bind_word_as_a_scalar_is_rejected_by_construction(self, loader: ConfargLoader) -> None:
        """``bind`` must be a dict — construction says so, naming the token's type, in every front-end."""
        with pytest.raises(TypeCoercionError, match=r"must be a dict, got str$"):
            loader.load(_CallableConfig, argv=["--fn.fn", f"{__name__}._shout", "--fn.bind", "5"], env={})

    def test_sibling_kwarg_without_an_opener_merges(self, loader: ConfargLoader) -> None:
        """No opener names no target, so only the path can say the flag is addressable."""
        merged = loader.merge(_CallableConfig, argv=["--fn.greeting", "Hi"], env={})
        assert merged == {"fn": {"greeting": "Hi"}}

    def test_sibling_kwarg_without_an_opener_is_rejected_by_construction(self, loader: ConfargLoader) -> None:
        """The missing opener is what the user hears about, not an unrecognized flag."""
        with pytest.raises(TypeCoercionError, match="must specify one of"):
            loader.load(_CallableConfig, argv=["--fn.greeting", "Hi"], env={})

    def test_sibling_kwarg_beside_a_call_opener(self, loader: ConfargLoader) -> None:
        """A kwarg the ``.call`` target's signature does not name still merges."""
        merged = loader.merge(
            _CallableConfig,
            argv=["--fn.call", f"{__name__}._shout", "--fn.greeting", "Hi"],
            env={},
        )
        assert merged == {"fn": {"call": f"{__name__}._shout", "greeting": "Hi"}}

    def test_sibling_kwarg_beside_the_bare_shorthand(self, loader: ConfargLoader) -> None:
        """The shorthand is opened first, so the stray kwarg refines it instead of erasing it."""
        merged = loader.merge(
            _CallableConfig,
            argv=["--fn", f"{__name__}._shout", "--fn.greeting", "Hi"],
            env={},
        )
        assert merged == {"fn": {"fn": f"{__name__}._shout", "greeting": "Hi"}}

    def test_sibling_kwarg_below_a_nested_callable(self, loader: ConfargLoader) -> None:
        """The rule holds wherever the callable sits, not only at the root."""
        merged = loader.merge(_NestedCallable, argv=["--inner.hook.greeting", "Hi"], env={})
        assert merged == {"inner": {"hook": {"greeting": "Hi"}}}

    def test_bind_subkey_delete_stays_value_less(self, loader: ConfargLoader) -> None:
        """Registering from the path must not claim a *delete* flag as a value flag (BUG-29).

        ``--fn.bind.<key>-`` addresses the bind subtree, so the path predicate matches it,
        but it is the patch scan's flag and takes no argument.
        """
        merged = loader.merge(
            _CallableConfig,
            argv=["--fn.fn", f"{__name__}._shout", "--fn.bind.punct-"],
            env={},
        )
        assert merged == {"fn": {"fn": f"{__name__}._shout", "bind": {"punct": DICT_DELETE}}}


@dataclass
class _CallableFieldNamedFn:
    """A struct whose callable field is spelled like a callable opener."""

    fn: Callable[[str], str] | None = None


@dataclass
class _StructWithCallableFieldNamedFn:
    """The opener scan must not read ``inner`` itself as a callable (BUG-30)."""

    inner: _CallableFieldNamedFn = dataclasses_field(default_factory=_CallableFieldNamedFn)


class TestOpenerScanTypeGuidedContract:
    """The argv opener scan is type-guided: ``--<path>.fn`` opens only a callable-typed path.

    ``build_dynamic_flags`` pattern-matches ``--<field>.fn/.class/.call`` against argv,
    which a struct field literally named ``fn`` (or ``class``/``call``) trips: the scan
    read ``--inner.fn`` as an opener for ``inner`` and registered ``inner.bind.*`` beside
    the correct ``inner.fn.bind.*`` the type-guided blob walk already found.  The scan now
    asks the target type whether ``<path>`` is callable-typed before treating the suffix as
    an opener, so a plain struct field named like an opener is a value, not an opener
    (BUG-30).
    """

    def test_spurious_opener_not_registered(self, populating_loader: ConfargLoader) -> None:
        """``--inner.fn`` opens ``inner.fn`` (callable), not ``inner`` (a struct)."""
        flags = populating_loader.registered_flags(
            _StructWithCallableFieldNamedFn,
            argv=["--inner.fn", f"{__name__}._shout"],
            config_flag="",
        )
        assert flags is not None
        assert "inner.fn.bind.name" in flags
        assert "inner.fn.bind.punct" in flags
        assert "inner.bind.name" not in flags
        assert "inner.bind.punct" not in flags

    def test_field_named_fn_merges_as_the_callable_shorthand(self, loader: ConfargLoader) -> None:
        """``--inner.fn <path>`` is the shorthand for the ``inner.fn`` callable field.

        The bare string stays bare until a sibling subkey joins it, exactly as
        ``--fn <path>`` does for a root callable field (the opener opens at build, not
        at merge, unless a bind flag forces it).
        """
        merged = loader.merge(
            _StructWithCallableFieldNamedFn,
            argv=["--inner.fn", f"{__name__}._shout"],
            env={},
        )
        assert merged == {"inner": {"fn": f"{__name__}._shout"}}

    def test_field_named_fn_binds(self, loader: ConfargLoader) -> None:
        """A sibling ``--inner.fn.bind.<param>`` opens the shorthand, as for any callable."""
        cfg = loader.load(
            _StructWithCallableFieldNamedFn,
            argv=["--inner.fn", f"{__name__}._shout", "--inner.fn.bind.punct", "!"],
            env={},
        )
        assert cfg.inner.fn("hi") == "HI!"


# ---------------------------------------------------------------------------
# Explicit .json / __json force-cast
# ---------------------------------------------------------------------------


class TestJsonCastContract:
    """The explicit ``.json`` suffix parses a value as JSON for any field type.

    It is the fifth member of the ``.str``/``.int``/``.float``/``.bool`` cast family:
    an escape hatch that is predictable regardless of the field type and reaches cases
    the implicit two-gate magic cannot (``Any``-typed fields, ``null`` in a list).  A
    real field/dict-key of the same name always wins over the cast.
    """

    def test_struct_field_from_json(self, loader: ConfargLoader) -> None:
        """--db.json '{...}' builds a nested struct."""
        cfg = loader.load(Nested, argv=["--db.json", '{"host": "h", "port": 9}'], env={})
        assert cfg.db == Simple(host="h", port=9)

    def test_list_with_null_from_json(self, loader: ConfargLoader) -> None:
        """--values.json '[null, 5]' passes a None the space-separated syntax can't express."""
        cfg = loader.load(_WithIntNoneList, argv=["--values.json", "[null, 5]"], env={})
        assert cfg.values == [None, 5]

    def test_any_field_only_reachable_via_json(self, loader: ConfargLoader) -> None:
        """.json decodes into an ``Any`` field, which the two-gate magic never touches."""
        cfg = loader.load(_WithAnyField, argv=["--data.json", '{"a": 1}'], env={})
        assert cfg.data == {"a": 1}

    def test_json_null_is_stored_not_dropped(self, loader: ConfargLoader) -> None:
        """--data.json null yields None (the falsy result is not mistaken for 'no cast')."""
        cfg = loader.load(_WithAnyField, argv=["--data.json", "null"], env={})
        assert cfg.data is None

    def test_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """An explicit .json with a malformed value hard-errors (explicit → loud)."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=["--db.json", "not json"], env={})

    def test_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """A field literally named ``json`` is addressed as a field, not a cast."""
        cfg = loader.load(_WithJsonNamedField, argv=["--json", "7"], env={})
        assert cfg.json == 7

    def test_nested_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """--inner.json 3 sets the real sub-field ``json`` rather than casting ``inner``."""
        cfg = loader.load(_OuterInner, argv=["--inner.json", "3"], env={})
        assert cfg.inner.json == 3

    def test_dict_key_named_json(self, loader: ConfargLoader) -> None:
        """On a dict field, --d.json addresses the key ``json`` (a valid key path wins)."""
        cfg = loader.load(_WithDictField, argv=["--d.json", "5"], env={})
        assert cfg.d == {"json": 5}

    def test_merged_dict_is_shared(self, loader: ConfargLoader) -> None:
        """merge() yields the decoded structure raw, identically across every integration."""
        data = loader.merge(Nested, argv=["--db.json", '{"host": "h", "port": 9}'], env={})
        assert data["db"] == {"host": "h", "port": 9}

    def test_bare_object_on_any_is_a_string_via_cli(self, loader: ConfargLoader) -> None:
        """Without .json, a brace value on an Any field stays a string (the magic never guesses)."""
        data = loader.merge(_WithAnyField, argv=["--data", '{"a": 1}'], env={})
        assert data["data"] == '{"a": 1}'

    def test_bare_object_on_any_agrees_across_cli_and_env(self, loader: ConfargLoader) -> None:
        """CLI and env store the identical string for a bare object on an Any field.

        Regression for a divergence where env treated ``Any`` as a struct (via
        ``_is_plain_class(typing.Any)``) and JSON-parsed it while the CLI kept the string.
        """
        cli = loader.merge(_WithAnyField, argv=["--data", '{"a": 1}'], env={})
        env = loader.merge(_WithAnyField, argv=[], env={"MYAPP_DATA": '{"a": 1}'}, env_prefix="MYAPP_")
        assert cli["data"] == env["data"] == '{"a": 1}'


class TestRootJsonContract:
    """A bare ``--json`` injects the whole config at CLI priority: the root peer of ``--field.json``.

    It mirrors the per-field ``.json`` cast for the root object — field flags refine it and a
    real root field named ``json`` still wins (see ``test_real_json_field_wins`` above).
    """

    def test_struct_root_from_json(self, loader: ConfargLoader) -> None:
        """--json '{...}' builds the whole struct root."""
        cfg = loader.load(Nested, argv=["--json", '{"db": {"host": "h", "port": 9}, "debug": true}'], env={})
        assert cfg == Nested(db=Simple(host="h", port=9), debug=True)

    def test_union_root_from_json_structural(self, loader: ConfargLoader) -> None:
        """--json selects a union-root variant by structure, no --class needed."""
        cfg = loader.load(_RootDBConfig, argv=["--json", '{"dbpath": "/tmp/x.db"}'], env={}, config_flag="")
        assert cfg == _RootSQLite(dbpath="/tmp/x.db")

    def test_union_root_from_json_explicit_class(self, loader: ConfargLoader) -> None:
        """--json may carry an explicit class tag for the union root."""
        blob = json.dumps({"class": f"{__name__}._RootSQLite", "dbpath": "/tmp/x.db"})
        cfg = loader.load(_RootDBConfig, argv=["--json", blob], env={}, config_flag="")
        assert cfg == _RootSQLite(dbpath="/tmp/x.db")

    def test_field_flag_overrides_json_either_order(self, loader: ConfargLoader) -> None:
        """A per-field CLI flag wins over --json regardless of argv order."""
        base = '{"db": {"host": "h", "port": 9}}'
        a = loader.load(Nested, argv=["--json", base, "--db.port", "1"], env={})
        b = loader.load(Nested, argv=["--db.port", "1", "--json", base], env={})
        assert a == b == Nested(db=Simple(host="h", port=1))

    def test_json_beats_env(self, loader: ConfargLoader) -> None:
        """Root --json lands at CLI priority, overriding env for the same key."""
        cfg = loader.load(
            Nested,
            argv=["--json", '{"db": {"host": "from-json"}}'],
            env={"MYAPP_DB__HOST": "from-env"},
            env_prefix="MYAPP_",
        )
        assert cfg.db.host == "from-json"

    def test_non_object_for_struct_root_raises(self, loader: ConfargLoader) -> None:
        """A non-object --json for a structured target is rejected."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=["--json", "[1, 2]"], env={})

    def test_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """A malformed root --json hard-errors (explicit → loud)."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=["--json", "{bad"], env={})

    def test_merged_dict_is_shared(self, loader: ConfargLoader) -> None:
        """merge() folds the decoded object into the raw dict identically across integrations."""
        data = loader.merge(Nested, argv=["--json", '{"db": {"host": "h", "port": 9}}'], env={})
        assert data["db"] == {"host": "h", "port": 9}


class TestEnvJsonCastContract:
    """The env counterpart ``FOO__field__json`` mirrors the CLI ``.json`` suffix."""

    def test_env_struct_from_json(self, loader: ConfargLoader) -> None:
        """MYAPP_DB__json='{...}' builds a nested struct from env."""
        cfg = loader.load(
            Nested,
            argv=[],
            env={"MYAPP_DB__json": '{"host": "eh", "port": 1}'},
            env_prefix="MYAPP_",
        )
        assert cfg.db == Simple(host="eh", port=1)

    def test_env_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """A malformed __json env value hard-errors, matching the CLI."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=[], env={"MYAPP_DB__json": "nope"}, env_prefix="MYAPP_")

    def test_env_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """MYAPP_INNER__json sets the real ``json`` sub-field, not a cast on ``inner``."""
        cfg = loader.load(_OuterInner, argv=[], env={"MYAPP_INNER__json": "9"}, env_prefix="MYAPP_")
        assert cfg.inner.json == 9

    def test_env_root_json_injects_whole_config(self, loader: ConfargLoader) -> None:
        """MYAPP_JSON='{...}' injects the whole configuration, mirroring a bare ``--json``."""
        cfg = loader.load(
            Nested,
            argv=[],
            env={"MYAPP_JSON": '{"db": {"host": "eh", "port": 1}, "debug": true}'},
            env_prefix="MYAPP_",
        )
        assert cfg == Nested(db=Simple(host="eh", port=1), debug=True)

    def test_env_root_json_loses_to_field_env_var(self, loader: ConfargLoader) -> None:
        """A per-field env var refines the injected object, as a CLI flag refines ``--json``."""
        cfg = loader.load(
            Nested,
            argv=[],
            env={"MYAPP_JSON": '{"db": {"host": "eh", "port": 1}}', "MYAPP_DB__PORT": "2"},
            env_prefix="MYAPP_",
        )
        assert cfg.db == Simple(host="eh", port=2)

    def test_env_root_json_loses_to_cli(self, loader: ConfargLoader) -> None:
        """Root env JSON lands at env priority: the CLI still wins."""
        cfg = loader.load(
            Nested,
            argv=["--db.host", "cli"],
            env={"MYAPP_JSON": '{"db": {"host": "eh", "port": 1}}'},
            env_prefix="MYAPP_",
        )
        assert cfg.db == Simple(host="cli", port=1)

    def test_env_root_real_json_field_wins(self, loader: ConfargLoader) -> None:
        """A real root field named ``json`` is addressed as a field, not a cast."""
        cfg = loader.load(_WithJsonNamedField, argv=[], env={"MYAPP_JSON": "7"}, env_prefix="MYAPP_")
        assert cfg.json == 7

    def test_env_root_non_object_for_struct_root_raises(self, loader: ConfargLoader) -> None:
        """A non-object root JSON for a structured target is rejected, as on the CLI."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=[], env={"MYAPP_JSON": "[1, 2]"}, env_prefix="MYAPP_")

    def test_env_root_invalid_json_raises(self, loader: ConfargLoader) -> None:
        """A malformed root JSON env value hard-errors (explicit -> loud)."""
        with pytest.raises(ConfargError):
            loader.load(Nested, argv=[], env={"MYAPP_JSON": "{bad"}, env_prefix="MYAPP_")


# ---------------------------------------------------------------------------
# Whole-value flags (a bare ``--<field> '{...}'`` assigning an object in one token)
# ---------------------------------------------------------------------------


@dataclass
class _WholeInner:
    """Struct with a nested dict field, to exercise whole-value flags at depth."""

    a: int = 1
    d: dict[str, int] = dataclasses.field(default_factory=dict)


@dataclass
class _WholeSqlite:
    """Struct-union variant for whole-value tests."""

    dbpath: str = ""


@dataclass
class _WholeServer:
    """Struct-union variant for whole-value tests."""

    host: str = ""
    port: int = 0


@dataclass
class _WholeValue:
    """One field per type that accepts a whole ``{...}`` token."""

    env: dict[str, str] = dataclasses.field(default_factory=dict)
    opt: dict[str, str] | None = None
    sub: _WholeInner = dataclasses.field(default_factory=_WholeInner)
    u: _WholeSqlite | _WholeServer | None = None


@dataclass
class _WholeMid:
    """Struct whose own field is a struct: two levels for bare-flag order tests (BUG-85)."""

    inner: _WholeInner = dataclasses.field(default_factory=_WholeInner)


@dataclass
class _WholeMidHolder:
    """Holder whose struct field holds a struct (BUG-85)."""

    x: _WholeMid = dataclasses.field(default_factory=_WholeMid)


class _WholePlain:
    """Plain class, not a dataclass: a struct everywhere else in construction."""

    def __init__(self, host: str = "h", port: int = 1) -> None:
        """Initialize with a host and a port."""
        self.host, self.port = host, port


@dataclass
class _WholePlainConfig:
    """Target whose struct field is a plain class rather than a dataclass."""

    db: _WholePlain = dataclasses.field(default_factory=_WholePlain)


# Vanilla raises its own ConfargError; argparse, click and cyclopts reject the flag in
# their own parsers and exit.  Both are "the front-end refused it", which is the contract.
_REJECTS_BARE_FLAG = (ConfargError, SystemExit)


class TestWholeValueFlagContract:
    """A dict, struct, struct-union or callable field takes its whole value in one token.

    ``--env '{"a": "b"}'`` assigns the entire mapping, the peer of the env channel's
    ``MYAPP_ENV='{"a": "b"}'``.  The flag is registered statically, so it shows up in
    ``--help`` beside the bare ``--tags``/``--pair`` flags that lists and tuples get.
    A token that is not a JSON object is kept raw and rejected by ``build()``, because
    the merge layer never validates.
    """

    def test_whole_dict_from_json(self, loader: ConfargLoader) -> None:
        """--env '{...}' assigns the whole mapping in one token."""
        cfg = loader.load(_WholeValue, argv=["--env", '{"a": "b"}'], env={})
        assert cfg.env == {"a": "b"}

    def test_nested_whole_dict_from_json(self, loader: ConfargLoader) -> None:
        """A dict nested inside a struct takes a whole value too."""
        cfg = loader.load(_WholeValue, argv=["--sub.d", '{"k": 1}'], env={})
        assert cfg.sub.d == {"k": 1}

    def test_whole_dict_merges_with_subkey(self, loader: ConfargLoader) -> None:
        """A later --env.<key> refines the mapping assigned as a whole."""
        cfg = loader.load(_WholeValue, argv=["--env", '{"a": "b"}', "--env.c", "d"], env={})
        assert cfg.env == {"a": "b", "c": "d"}

    def test_whole_optional_dict_from_json(self, loader: ConfargLoader) -> None:
        """An optional dict takes the whole mapping its non-optional peer takes."""
        cfg = loader.load(_WholeValue, argv=["--opt", '{"a": "b"}'], env={})
        assert cfg.opt == {"a": "b"}

    def test_whole_optional_dict_merges_with_subkey(self, loader: ConfargLoader) -> None:
        """A later --opt.<key> refines the optional mapping assigned as a whole."""
        cfg = loader.load(_WholeValue, argv=["--opt", '{"a": "b"}', "--opt.c", "d"], env={})
        assert cfg.opt == {"a": "b", "c": "d"}

    def test_whole_optional_dict_matches_env_channel(self, loader: ConfargLoader) -> None:
        """The CLI and env spellings of a whole optional mapping agree, as for a plain dict."""
        cli = loader.merge(_WholeValue, argv=["--opt", '{"a": "b"}'], env={})
        env = loader.merge(_WholeValue, argv=[], env={"MYAPP_OPT": '{"a": "b"}'}, env_prefix="MYAPP_")
        assert cli["opt"] == env["opt"] == {"a": "b"}

    def test_whole_struct_from_json(self, loader: ConfargLoader) -> None:
        """--sub '{...}' assigns a whole nested struct."""
        cfg = loader.load(_WholeValue, argv=["--sub", '{"a": 2}'], env={})
        assert cfg.sub == _WholeInner(a=2)

    def test_whole_plain_class_from_json(self, loader: ConfargLoader) -> None:
        """A plain-class field takes the blob its dataclass peer takes (BUG-39)."""
        cfg = loader.load(_WholePlainConfig, argv=["--db", '{"host": "x", "port": 9}'], env={})
        assert (cfg.db.host, cfg.db.port) == ("x", 9)

    def test_whole_plain_class_merges_with_subkey(self, loader: ConfargLoader) -> None:
        """A later --db.<param> refines the plain-class object assigned as a whole (BUG-39)."""
        cfg = loader.load(_WholePlainConfig, argv=["--db", '{"host": "x"}', "--db.port", "9"], env={})
        assert (cfg.db.host, cfg.db.port) == ("x", 9)

    def test_whole_plain_class_matches_env_channel(self, loader: ConfargLoader) -> None:
        """The CLI and env spellings of a whole plain-class value merge alike (BUG-39)."""
        blob = '{"host": "x", "port": 9}'
        cli = loader.merge(_WholePlainConfig, argv=["--db", blob], env={})
        env = loader.merge(_WholePlainConfig, argv=[], env={"MYAPP_DB": blob}, env_prefix="MYAPP_")
        assert cli["db"] == env["db"] == {"host": "x", "port": 9}

    def test_struct_non_object_token_is_kept_raw(self, loader: ConfargLoader) -> None:
        """merge() keeps a struct flag's non-object token verbatim, as the dict flag's (BUG-82).

        Vanilla's ``_consume_value`` leaves the token raw for ``build()`` to refuse, so
        the collector must store it too: dropping it swallowed a typo'd CLI value on
        four of the five front-ends, silently building the field's default.
        """
        data = loader.merge(_WholeValue, argv=["--sub", "oops"], env={})
        assert data["sub"] == "oops"

    def test_struct_non_object_token_fails_to_build(self, loader: ConfargLoader) -> None:
        """build() is what rejects it, loudly on every front-end (BUG-82)."""
        with pytest.raises(TypeCoercionError, match="expected dict"):
            loader.load(_WholeValue, argv=["--sub", "oops"], env={})

    def test_struct_non_object_token_below_a_namedtuple_is_kept_raw(self, loader: ConfargLoader) -> None:
        """The same token at a namedtuple's struct field is kept too (BUG-82, via BUG-68).

        A struct field below a namedtuple reaches the same struct branch of the
        per-field dispatch, so the drop occurred at that depth as well.
        """
        data = loader.merge(_WithStructFieldPoint, argv=["--pt.inner", "oops"], env={})
        assert data["pt"]["inner"] == "oops"

    def test_struct_bare_flag_after_subflag_takes_the_field(self, loader: ConfargLoader) -> None:
        """A bare --<field> typed after its sub-flags replaces the subtree, as any later write does (BUG-85).

        Vanilla writes the flags in the order argv spells them, so a bare
        ``--x.inner 9`` overwrites the ``--x.inner.a`` write before it. The
        adapters' collector stored the bare value ahead of its descent into the
        sub-flags, so the sub-flag's write landed on top of it whatever argv
        spelled.
        """
        assert loader.merge(_WholeMidHolder, argv=["--x.inner.a", "7", "--x.inner", "9"], env={}) == {
            "x": {"inner": "9"},
        }

    def test_struct_bare_flag_after_subflag_fails_to_build(self, loader: ConfargLoader) -> None:
        """build() is what rejects the raw token, loudly on every front-end (BUG-85, via BUG-82)."""
        with pytest.raises(TypeCoercionError, match="expected dict"):
            loader.load(_WholeMidHolder, argv=["--x.inner.a", "7", "--x.inner", "9"], env={})

    def test_struct_bare_flag_before_subflag_stays_refined(self, loader: ConfargLoader) -> None:
        """A bare --<field> typed first is descended into by the sub-flag typed after it (BUG-85).

        Guards the fix against over-firing: only the bare flag typed after its
        sub-flags replaces the subtree.
        """
        assert loader.merge(_WholeMidHolder, argv=["--x.inner", "9", "--x.inner.a", "7"], env={}) == {
            "x": {"inner": {"a": 7}},
        }

    def test_struct_whole_value_after_subflag_takes_the_field(self, loader: ConfargLoader) -> None:
        """A whole value typed after a sub-flag replaces it, the blob spelling of BUG-85."""
        assert loader.merge(
            _WholeMidHolder,
            argv=["--x.inner.a", "7", "--x.inner", '{"a": 2}'],
            env={},
        ) == {"x": {"inner": {"a": 2}}}

    def test_union_plain_flag_before_variant_flag_is_descended_into(self, loader: ConfargLoader) -> None:
        """A bare union flag typed first is refined by the variant flag typed after it (BUG-85).

        The collector's union branch wrote the plain value after the variant
        walks, so the plain token won whatever argv spelled -- the inversion of
        the struct branch.
        """
        assert loader.merge(_WholeValue, argv=["--u", "9", "--u.dbpath", "x"], env={}) == {
            "u": {"dbpath": "x"},
        }

    def test_union_plain_flag_after_variant_flag_takes_the_field(self, loader: ConfargLoader) -> None:
        """A bare union flag typed after the variant flags replaces the subtree (BUG-85).

        Guards the fix against over-firing: this order already agreed, because
        the plain write followed the walks.
        """
        assert loader.merge(_WholeValue, argv=["--u.dbpath", "x", "--u", "9"], env={}) == {"u": "9"}

    def test_union_whole_value_after_variant_flag_takes_the_field(self, loader: ConfargLoader) -> None:
        """A whole value typed after a variant flag replaces it, the union spelling of BUG-85."""
        assert loader.merge(
            _WholeValue,
            argv=["--u.dbpath", "x", "--u", '{"host": "h"}'],
            env={},
        ) == {"u": {"host": "h"}}

    def test_registered_leaf_scalar_after_param_flag_takes_the_field(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """A registered leaf's scalar typed after its ``__init__`` parameter flags replaces them (BUG-85).

        The registered-leaf branch stored the scalar before the structural walk,
        so a ``--id.hex`` the later ``--id`` had already overwritten came back.
        """
        confarg.register_leaf_type(UUID, UUID)
        assert loader.merge(_RegisteredLeaf, argv=["--id.hex", "ab", "--id", "7"], env={}) == {"id": "7"}

    def test_registered_leaf_scalar_before_param_flag_stays_refined(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """A scalar typed before the parameter flags keeps the walk's answer (BUG-85).

        Guards the fix against over-firing.
        """
        confarg.register_leaf_type(UUID, UUID)
        assert loader.merge(_RegisteredLeaf, argv=["--id", "7", "--id.hex", "ab"], env={}) == {
            "id": {"hex": "ab"},
        }

    def test_tagged_registered_leaf_takes_the_whole_value(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """A tag naming a registered leaf's class opens it from the CLI too (BUG-39).

        A registered leaf is opaque to every implicit decision, but an explicit tag builds
        it from its ``__init__`` parameters -- the hatch the coercion error points at.  The
        whole-value predicate therefore asks ``_is_struct``, not the narrower
        ``_is_struct_variant``: the token has to be decoded before the tag inside it can be
        seen.  Env and files honoured the hatch all along; the CLI used to keep the blob as
        a string and build a leaf out of the JSON text.
        """
        confarg.register_leaf_type(UUID, UUID)
        blob = f'{{"class": "uuid.UUID", "hex": "{_UUID_TEXT.replace("-", "")}"}}'
        cfg = loader.load(_RegisteredLeaf, argv=["--id", blob], env={})
        assert cfg.id == UUID(_UUID_TEXT)

    def test_flat_tagged_registered_leaf_builds_on_every_frontend(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """The flat spelling of the tagged-leaf hatch crosses the adapter seam (BUG-56).

        ``--id.class`` / ``--id.hex`` is what ``ID__CLASS`` / ``ID__HEX`` says in the
        environment, and vanilla accepted it all along because its type walk treats a
        registered leaf structurally. The adapters took their registered-leaf branch
        first, so no such flag was ever registered and the four frameworks rejected the
        tokens at parse time.
        """
        confarg.register_leaf_type(UUID, UUID)
        hex_text = _UUID_TEXT.replace("-", "")
        cfg = loader.load(_RegisteredLeaf, argv=["--id.class", "uuid.UUID", "--id.hex", hex_text], env={})
        assert cfg.id == UUID(_UUID_TEXT)

    def test_flat_tagged_registered_leaf_matches_env_channel(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """The flat CLI spelling merges exactly what ID__CLASS / ID__HEX merges (BUG-56)."""
        confarg.register_leaf_type(UUID, UUID)
        hex_text = _UUID_TEXT.replace("-", "")
        cli = loader.merge(
            _RegisteredLeaf,
            argv=["--id.class", "uuid.UUID", "--id.hex", hex_text],
            env={},
        )
        env = loader.merge(
            _RegisteredLeaf,
            argv=[],
            env={"MYAPP_ID__CLASS": "uuid.UUID", "MYAPP_ID__HEX": hex_text},
            env_prefix="MYAPP_",
        )
        assert cli == env == {"id": {"class": "uuid.UUID", "hex": hex_text}}

    def test_flat_leaf_param_refines_whole_value(self, loader: ConfargLoader, leaf_registry: None) -> None:
        """A --id.<param> beside a tagged blob refines it, as a struct's sub-flag does (BUG-56)."""
        confarg.register_leaf_type(UUID, UUID)
        hex_text = _UUID_TEXT.replace("-", "")
        blob = '{"class": "uuid.UUID"}'
        cfg = loader.load(_RegisteredLeaf, argv=["--id", blob, "--id.hex", hex_text], env={})
        assert cfg.id == UUID(_UUID_TEXT)

    def test_flat_leaf_flags_register_only_when_typed(
        self,
        populating_loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """Typed flat leaf flags register; an empty argv keeps them off --help (BUG-56).

        The registration is argv-scanned, like an escaped opener: a registered leaf's
        ordinary spelling is its scalar, and one flag per ``__init__`` parameter would
        clutter ``--help`` for the escape hatch.
        """
        confarg.register_leaf_type(UUID, UUID)
        hex_text = _UUID_TEXT.replace("-", "")
        typed = populating_loader.registered_flags(
            _RegisteredLeaf,
            argv=["--id.class", "uuid.UUID", "--id.hex", hex_text],
        )
        assert typed is not None
        assert {"id.class", "id.hex"} <= typed
        quiet = populating_loader.registered_flags(_RegisteredLeaf)
        assert quiet is not None
        assert not {f for f in quiet if f.startswith("id.")}

    def test_flat_leaf_unknown_param_refused(self, loader: ConfargLoader, leaf_registry: None) -> None:
        """--id.bogus names no __init__ parameter, so every front-end refuses it (BUG-56)."""
        confarg.register_leaf_type(UUID, UUID)
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(_RegisteredLeaf, argv=["--id.class", "uuid.UUID", "--id.bogus", "x"], env={})

    def test_flat_tagged_registered_leaf_root_builds_on_every_frontend(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """The flat tagged-leaf hatch reaches a registered leaf as the *root* target (BUG-71).

        The root has no field to descend from: the tag flag's only segment is the tag,
        so the scan found no leaf at a proper prefix of the path and registered nothing,
        while vanilla's type walk answers the tag segment whatever the target.  The
        ``__init__`` parameters were already registered statically (the root is walked
        structurally, as the union holding the same leaf is), so the tag flag alone was
        missing.
        """
        confarg.register_leaf_type(UUID, UUID)
        hex_text = _UUID_TEXT.replace("-", "")
        cfg = loader.load(UUID, argv=["--app.class", "uuid.UUID", "--app.hex", hex_text], env={}, cli_prefix="app")
        assert cfg == UUID(_UUID_TEXT)

    def test_flat_tagged_registered_leaf_root_merges_like_the_file_channel(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
        tmp_yaml,
    ) -> None:
        """A root-leaf tag merges at the top level, as the file and env channels do (BUG-71, BUG-90).

        The file channel's top-level ``class:`` key and the env channel's root-level
        ``CLASS`` variable merge to the same dict the tag flag produces.
        """
        confarg.register_leaf_type(UUID, UUID)
        hex_text = _UUID_TEXT.replace("-", "")
        cli = loader.merge(UUID, argv=["--app.class", "uuid.UUID", "--app.hex", hex_text], env={}, cli_prefix="app")
        cfg = tmp_yaml(f'class: uuid.UUID\nhex: "{hex_text}"\n')
        file = loader.merge(UUID, argv=[], env={}, files=[cfg])
        env = loader.merge(
            UUID,
            argv=[],
            env={"MYAPP_CLASS": "uuid.UUID", "MYAPP_HEX": hex_text},
            env_prefix="MYAPP_",
        )
        assert cli == file == env == {"class": "uuid.UUID", "hex": hex_text}

    def test_flat_leaf_root_tag_registers_only_when_typed(
        self,
        populating_loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """The root-leaf tag flag registers when typed; an empty argv keeps it off --help (BUG-71).

        Like a field's flat leaf flags, the tag is registered only when typed -- but the
        root's ``__init__`` parameters are static, so the quiet run still shows them.
        """
        confarg.register_leaf_type(UUID, UUID)
        typed = populating_loader.registered_flags(UUID, argv=["--app.class", "uuid.UUID"], cli_prefix="app")
        assert typed is not None
        assert "app.class" in typed
        quiet = populating_loader.registered_flags(UUID, cli_prefix="app")
        assert quiet is not None
        assert "app.class" not in quiet

    def test_flat_leaf_root_unknown_param_refused(self, loader: ConfargLoader, leaf_registry: None) -> None:
        """--app.bogus names no __init__ parameter of the root leaf, so every front-end refuses it (BUG-71)."""
        confarg.register_leaf_type(UUID, UUID)
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(UUID, argv=["--app.class", "uuid.UUID", "--app.bogus", "x"], env={}, cli_prefix="app")

    def test_whole_struct_union_from_json(self, loader: ConfargLoader) -> None:
        """--u '{...}' carries its own discriminator and builds the variant."""
        cfg = loader.load(
            _WholeValue,
            argv=["--u", f'{{"class": "{__name__}._WholeSqlite", "dbpath": "/x"}}'],
            env={},
        )
        assert cfg.u == _WholeSqlite(dbpath="/x")

    def test_whole_callable_from_json(self, loader: ConfargLoader) -> None:
        """A callable field decodes its blob into a spec rather than keeping the string."""
        cfg = loader.load(
            _CallableConfig,
            argv=["--fn", f'{{"class": "{__name__}._Greeter", "greeting": "Hi", "bind": {{"punct": "!"}}}}'],
            env={},
        )
        assert cfg.fn("world") == "Hi, world!"

    def test_whole_optional_callable_from_json(self, loader: ConfargLoader) -> None:
        """An optional callable decodes the blob its non-optional peer decodes (BUG-17)."""
        cfg = loader.load(
            _OptCallableConfig,
            argv=["--fn", f'{{"class": "{__name__}._Greeter", "greeting": "Hi", "bind": {{"punct": "!"}}}}'],
            env={},
        )
        assert cfg.fn is not None
        assert cfg.fn("world") == "Hi, world!"

    def test_bind_flag_registers_from_whole_callable_blob(self, loader: ConfargLoader) -> None:
        """A class named inside the blob still buys its --fn.bind.<param> flag (BUG-22)."""
        blob = json.dumps({"class": f"{__name__}._Greeter", "greeting": "Hi"})
        cfg = loader.load(_CallableConfig, argv=["--fn", blob, "--fn.bind.punct", "!"], env={})
        assert cfg.fn("world") == "Hi, world!"

    def test_factory_flag_registers_from_whole_optional_callable_blob(self, loader: ConfargLoader) -> None:
        """The blob's class buys its constructor kwarg flags too, optional field included (BUG-22)."""
        blob = json.dumps({"class": f"{__name__}._Greeter"})
        cfg = loader.load(
            _OptCallableConfig,
            argv=["--fn", blob, "--fn.greeting", "Hi", "--fn.bind.punct", "!"],
            env={},
        )
        assert cfg.fn is not None
        assert cfg.fn("world") == "Hi, world!"

    def test_dict_blob_buys_no_callable_flags(self, populating_loader: ConfargLoader) -> None:
        """A mapping that happens to carry a 'class' key is not read as a callable spec (BUG-22)."""
        blob = json.dumps({"class": f"{__name__}._Greeter"})
        flags = populating_loader.registered_flags(_WholeValue, argv=["--env", blob])
        assert flags is not None
        assert not {f for f in flags if f.startswith(("env.greeting", "env.bind."))}

    def test_whole_optional_callable_matches_env_channel(self, loader: ConfargLoader) -> None:
        """The CLI and env spellings of a whole optional callable spec agree, as for a dict."""
        blob = f'{{"class": "{__name__}._Greeter", "greeting": "Hi"}}'
        cli = loader.merge(_OptCallableConfig, argv=["--fn", blob], env={})
        env = loader.merge(_OptCallableConfig, argv=[], env={"MYAPP_FN": blob}, env_prefix="MYAPP_")
        assert cli["fn"] == env["fn"] == {"class": f"{__name__}._Greeter", "greeting": "Hi"}

    def test_whole_dict_matches_env_channel(self, loader: ConfargLoader) -> None:
        """The CLI and env spellings of a whole mapping merge to the identical dict."""
        cli = loader.merge(_WholeValue, argv=["--env", '{"a": "b"}'], env={})
        env = loader.merge(_WholeValue, argv=[], env={"MYAPP_ENV": '{"a": "b"}'}, env_prefix="MYAPP_")
        assert cli["env"] == env["env"] == {"a": "b"}

    def test_non_object_token_is_kept_raw(self, loader: ConfargLoader) -> None:
        """merge() keeps a non-JSON token verbatim: the merge layer never validates."""
        data = loader.merge(_WholeValue, argv=["--env", "oops"], env={})
        assert data["env"] == "oops"

    def test_non_object_token_fails_to_build(self, loader: ConfargLoader) -> None:
        """build() is what rejects it, with the same diagnosis everywhere."""
        with pytest.raises(TypeCoercionError, match="expected dict"):
            loader.load(_WholeValue, argv=["--env", "oops"], env={})

    def test_malformed_object_raises(self, loader: ConfargLoader) -> None:
        """A token that opens a JSON object but is malformed hard-errors identically."""
        with pytest.raises(ConfargError, match="Invalid JSON"):
            loader.load(_WholeValue, argv=["--env", "{"], env={})

    def test_bare_struct_flag_without_a_value_is_rejected(self, loader: ConfargLoader) -> None:
        """--sub with no token is rejected everywhere: a whole-value flag needs its value (BUG-8).

        Vanilla used to accept the bare form for a non-optional struct field and merge
        nothing, a no-op no adapter could reproduce -- cyclopts cannot express a parameter
        whose token count varies.  Every front-end now refuses it, the way they already
        refused the same form on the ``dict`` and ``dict | None`` fields below.
        """
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(_WholeValue, argv=["--sub"], env={})

    def test_bare_struct_flag_before_another_flag_is_rejected(self, loader: ConfargLoader) -> None:
        """--sub followed by another flag is rejected too, not silently skipped."""
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(_WholeValue, argv=["--sub", "--env", '{"a": "b"}'], env={})

    def test_bare_dict_flag_without_a_value_is_rejected(self, loader: ConfargLoader) -> None:
        """The dict peer of the struct flag refuses the bare form identically."""
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(_WholeValue, argv=["--env"], env={})

    def test_bare_optional_dict_flag_without_a_value_is_rejected(self, loader: ConfargLoader) -> None:
        """Optionality does not buy a bare form either."""
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.load(_WholeValue, argv=["--opt"], env={})

    def test_whole_value_flags_registered(self, populating_loader: ConfargLoader) -> None:
        """Every adapter registers the bare flag, so it is visible in --help."""
        flags = populating_loader.registered_flags(_WholeValue)
        assert flags is not None
        assert {"env", "opt", "sub", "u"} <= flags


# ---------------------------------------------------------------------------
# Local variables (the reserved ``locals:`` namespace)
# ---------------------------------------------------------------------------


@dataclass
class _LocalsConfig:
    """Config whose fields are all derived from local variables."""

    root: str = ""
    logs: str = ""
    n: int = 0


@dataclass
class _LocalsNode:
    """Block a mounted fragment describes, including its own scratch values."""

    host: str = ""


@dataclass
class _LocalsNested:
    """Target whose nested block carries a namespace of its own."""

    db: _LocalsNode = dataclasses_field(default_factory=_LocalsNode)


@dataclass
class _LocalsShadow:
    """Config that claims ``locals``, pushing the namespace to ``_locals``."""

    locals: str = ""
    root: str = ""


@dataclass
class _LocalsFromField:
    """Config whose ``env`` field feeds a local variable, the documented override path."""

    deploy_env: str = "dev"
    path: str = ""


class TestLocalsContract:
    """The reserved ``locals:`` namespace behaves identically in every front-end.

    A local is *declared* in a configuration file, which is what gives it a type,
    and *modified* from any channel.  Modification therefore has full
    cross-channel parity; only declaration is file-only, because declaring means
    fixing a type and env and CLI have none to fix.  An override is coerced to
    the declared type, so ``${locals.n * 2}`` keeps adding rather than repeating
    a string, and a write to an undeclared name is an error rather than a new
    variable.  These tests pin all of that across the four front-ends.

    The bare whole-namespace form (``--locals VALUE``) has parity too: the graft
    makes ``locals`` a dict-typed path, so every front-end registers the flag and
    the pipeline — not the host framework — rejects the assignment.
    """

    def test_whole_namespace_cannot_be_assigned(self, loader: ConfargLoader) -> None:
        """A bare --locals would replace the namespace; every front-end says so itself."""
        with pytest.raises(ConfargError, match="cannot be assigned as a whole"):
            loader.load(_LocalsConfig, argv=["--locals", "x"], env={})

    def test_locals_feed_expressions(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Config-file locals resolve into fields and never reach the target type."""
        cfg = tmp_yaml("""
locals:
  base: /srv/app
  k: 3
root: ${locals.base}
logs: ${locals.base}/logs
n: ${locals.k * 2}
""")
        result = loader.load(_LocalsConfig, argv=["--config", str(cfg)], env={})
        assert result == _LocalsConfig(root="/srv/app", logs="/srv/app/logs", n=6)

    def test_locals_keep_their_file_type(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A numeric local stays numeric, so arithmetic adds rather than concatenates."""
        cfg = tmp_yaml("locals:\n  k: 3\nn: ${locals.k * 2}\n")
        assert loader.load(_LocalsConfig, argv=["--config", str(cfg)], env={}).n == 6

    def test_locals_may_reference_locals(self, loader: ConfargLoader, tmp_yaml) -> None:
        """One local may be an expression over another; resolution order is topological."""
        cfg = tmp_yaml("locals:\n  a: 2\n  b: ${locals.a * 3}\nn: ${locals.b}\n")
        assert loader.load(_LocalsConfig, argv=["--config", str(cfg)], env={}).n == 6

    def test_cli_modifies_a_declared_local(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--locals.<name> retargets a declared local, identically in every front-end."""
        cfg = tmp_yaml("locals:\n  base: /srv\nroot: ${locals.base}\nlogs: ${locals.base}/logs\n")
        result = loader.load(_LocalsConfig, argv=["--config", str(cfg), "--locals.base", "/home/bob"], env={})
        assert result.root == "/home/bob"
        assert result.logs == "/home/bob/logs"

    def test_env_modifies_a_declared_local(self, loader: ConfargLoader, tmp_yaml) -> None:
        """The env channel modifies a local exactly as the CLI does."""
        cfg = tmp_yaml("locals:\n  base: /srv\nroot: ${locals.base}\n")
        result = loader.load(
            _LocalsConfig,
            argv=["--config", str(cfg)],
            env={"MYAPP_LOCALS__BASE": "/home/bob"},
            env_prefix="MYAPP_",
        )
        assert result.root == "/home/bob"

    def test_override_keeps_the_declared_type(self, loader: ConfargLoader, tmp_yaml) -> None:
        """An overridden int local stays an int, so the expression adds, not repeats.

        This is the property the earlier config-file-only rule existed to protect;
        coercing against the declaration preserves it while allowing the override.
        """
        cfg = tmp_yaml("locals:\n  k: 3\nn: ${locals.k * 2}\n")
        assert loader.load(_LocalsConfig, argv=["--config", str(cfg), "--locals.k", "5"], env={}).n == 10
        from_env = loader.load(
            _LocalsConfig,
            argv=["--config", str(cfg)],
            env={"MYAPP_LOCALS__K": "5"},
            env_prefix="MYAPP_",
        )
        assert from_env.n == 10

    def test_undeclared_local_raises(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A local no config file declared cannot be introduced from CLI or env."""
        cfg = tmp_yaml("locals:\n  base: /srv\nroot: ${locals.base}\n")
        with pytest.raises(ConfargError, match="declared by no configuration file"):
            loader.load(_LocalsConfig, argv=["--config", str(cfg), "--locals.nope", "x"], env={})
        with pytest.raises(ConfargError, match="declared by no configuration file"):
            loader.load(
                _LocalsConfig,
                argv=["--config", str(cfg)],
                env={"MYAPP_LOCALS__NOPE": "x"},
                env_prefix="MYAPP_",
            )

    def test_type_changing_override_raises(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A local's scalar type comes from its declaration and cannot change."""
        cfg = tmp_yaml("locals:\n  k: 3\nn: ${locals.k}\n")
        with pytest.raises(TypeCoercionError):
            loader.load(_LocalsConfig, argv=["--config", str(cfg), "--locals.k", "abc"], env={})

    def test_config_flag_override_path(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.locals FILE is the supported way to override a local from the CLI."""
        base = tmp_yaml("locals:\n  base: /srv\nroot: ${locals.base}\n")
        over = tmp_yaml("base: /opt\n", "override.yaml")
        result = loader.load(
            _LocalsConfig,
            argv=["--config", str(base), "--config.locals", str(over)],
            env={},
        )
        assert result.root == "/opt"

    def test_local_derived_from_a_real_field(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A local may be an expression over a real field, which stays CLI/env settable."""
        cfg = tmp_yaml("locals:\n  e: ${deploy_env}\npath: /srv/${locals.e}\n")
        result = loader.load(_LocalsFromField, argv=["--config", str(cfg), "--deploy_env", "prod"], env={})
        assert result.path == "/srv/prod"

    def test_merge_preserves_locals(self, loader: ConfargLoader, tmp_yaml) -> None:
        """merge() keeps the namespace, so a merged dict round-trips through dump_file()."""
        cfg = tmp_yaml("locals:\n  base: /srv\nroot: ${locals.base}\n")
        data = loader.merge(_LocalsConfig, argv=["--config", str(cfg)], env={})
        assert data["locals"] == {"base": "/srv"}
        assert data["root"] == "${locals.base}"

    def test_either_spelling_works(self, loader: ConfargLoader, tmp_yaml) -> None:
        """With ``locals`` free, ``_locals`` addresses the namespace just as well."""
        cfg = tmp_yaml("_locals:\n  base: /srv\nroot: ${_locals.base}\n")
        result = loader.load(_LocalsConfig, argv=["--config", str(cfg), "--_locals.base", "/home/bob"], env={})
        assert result.root == "/home/bob"

    def test_declaring_under_both_spellings_is_ambiguous(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Two declaration blocks are refused rather than one silently winning."""
        cfg = tmp_yaml("locals:\n  a: 1\n_locals:\n  b: 2\nroot: x\n")
        with pytest.raises(ConfargError, match="ambiguous"):
            loader.load(_LocalsConfig, argv=["--config", str(cfg)], env={})

    def test_a_locals_field_keeps_its_name(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A real ``locals`` field wins the name; the namespace moves to ``_locals``.

        The field stays settable from the CLI, which is what the derived name is
        for — the earlier design rejected such a target outright.
        """
        cfg = tmp_yaml("locals: iamafield\n_locals:\n  base: /srv\nroot: ${_locals.base}\n")
        result = loader.load(
            _LocalsShadow,
            argv=["--config", str(cfg), "--locals", "other", "--_locals.base", "/opt"],
            env={},
        )
        assert result.locals == "other"
        assert result.root == "/opt"

    def test_a_nested_namespace_works_in_every_front_end(self, loader: ConfargLoader, tmp_path, tmp_yaml) -> None:
        """A mounted fragment declares, uses and exposes its own namespace.

        An included file's root lands where it is mounted, so the namespace is
        derived per node.  Declaring stays file-only; modifying keeps full
        cross-channel parity at depth, just as it has at the root.
        """
        (tmp_path / "db.yaml").write_text("locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = tmp_yaml(f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert loader.load(_LocalsNested, argv=["--config", str(cfg)], env={}).db.host == "db.internal"
        cli = loader.load(_LocalsNested, argv=["--config", str(cfg), "--db.locals.h", "from-cli"], env={})
        assert cli.db.host == "from-cli"
        env = loader.load(
            _LocalsNested,
            argv=["--config", str(cfg)],
            env={"MYAPP_DB__LOCALS__H": "from-env"},
            env_prefix="MYAPP_",
        )
        assert env.db.host == "from-env"

    def test_an_undeclared_nested_local_is_rejected_everywhere(
        self,
        loader: ConfargLoader,
        tmp_path,
        tmp_yaml,
    ) -> None:
        """The declared-ness check follows the namespace down, in all four front-ends."""
        (tmp_path / "db.yaml").write_text("locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = tmp_yaml(f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        with pytest.raises(ConfargError, match=r"db\.locals\.nope"):
            loader.load(_LocalsNested, argv=["--config", str(cfg), "--db.locals.nope", "x"], env={})


# ---------------------------------------------------------------------------
# Dynamic flag registration failures
# ---------------------------------------------------------------------------


class TestDynamicFlagFailureContract:
    """A failure inside dynamic flag registration is announced by every front-end (BUG-5)."""

    def test_registration_failure_warns_in_every_front_end(
        self,
        populating_loader: ConfargLoader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``populate_*`` keeps its static flags but warns that the dynamic ones are missing.

        All three adapters route registration through the same ``build_dynamic_flags``, so one
        warning path has to cover them; silence would leave the user with nothing but the
        framework's own "unknown flag" message.
        """

        def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            msg = "deliberate boom"
            raise RuntimeError(msg)

        monkeypatch.setattr(build_mod, "_collect_fn_paths_from_argv", _boom)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            flags = populating_loader.registered_flags(Simple)
        assert flags is not None
        assert "host" in flags  # static registration is unaffected
        assert any(issubclass(w.category, ConfargWarning) and "deliberate boom" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Subclass named by a tag but not yet imported (BUG-6)
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Callable[[int], tuple[Any, str]]]:
    """Build a base module plus an *un-imported* plugin subclass module on sys.path.

    Returns ``make(union_tag="class") -> (base_module, plugin_module_name)`` with only the
    base imported: the plugin is importable but absent from ``sys.modules``, so
    ``Handler.__subclasses__()`` is empty until something imports it by name.  Each call gets
    freshly named modules because ``__subclasses__()`` bleeds for the process lifetime
    (tests/typedload/test_construct.py records the same constraint).
    """
    import importlib  # noqa: PLC0415 — only this fixture needs it
    import sys  # noqa: PLC0415

    made: list[str] = []
    monkeypatch.syspath_prepend(str(tmp_path))

    def make(n: int = 0) -> tuple[Any, str]:
        base_name, plug_name = f"_cfg_base_{n}", f"_cfg_plug_{n}"
        (tmp_path / f"{base_name}.py").write_text(
            "from dataclasses import dataclass, field\n\n\n"
            "@dataclass\nclass Handler:\n    name: str = 'base'\n\n\n"
            "@dataclass\nclass Config:\n    handler: Handler = field(default_factory=Handler)\n",
            newline="\n",
        )
        (tmp_path / f"{plug_name}.py").write_text(
            f"from dataclasses import dataclass\nfrom {base_name} import Handler\n\n\n"
            "@dataclass\nclass FileHandler(Handler):\n    path: str = '/var/log/a'\n",
            newline="\n",
        )
        made.extend((base_name, plug_name))
        base = importlib.import_module(base_name)
        assert plug_name not in sys.modules  # the whole point: the plugin is not loaded
        return base, plug_name

    yield make

    for name in made:
        sys.modules.pop(name, None)


class TestUnimportedSubclassContract:
    """A class named by the union tag is usable before anything imports it (BUG-6).

    ``build()`` resolves the tag by importing it, so the same keys in a config file already
    work; the CLI channel has to reach the same answer in every front-end.
    """

    def test_tag_on_argv(self, loader: ConfargLoader, plugin_pair: Any) -> None:
        """--handler.class names a subclass nobody imported, and its own flags follow."""
        base, plug = plugin_pair(0)
        result = loader.load(
            base.Config,
            argv=["--handler.class", f"{plug}.FileHandler", "--handler.path", "/x"],
            env={},
        )
        assert type(result.handler).__name__ == "FileHandler"
        assert (result.handler.name, result.handler.path) == ("base", "/x")

    def test_tag_in_config_file_selects_subclass(
        self,
        loader: ConfargLoader,
        plugin_pair: Any,
        tmp_path: Path,
    ) -> None:
        """The tag reaches the parser from a --config file, not only from argv."""
        base, plug = plugin_pair(1)
        cfg = tmp_path / "app.toml"
        cfg.write_text(f'[handler]\nclass = "{plug}.FileHandler"\n', newline="\n")
        result = loader.load(base.Config, argv=["--config", str(cfg)], env={})
        assert type(result.handler).__name__ == "FileHandler"
        assert result.handler.path == "/var/log/a"

    def test_tag_in_config_file_registers_subclass_flags(
        self,
        populating_loader: ConfargLoader,
        plugin_pair: Any,
        tmp_path: Path,
    ) -> None:
        """A tag read from a --config file makes the subclass's flags registrable too.

        The registration half, which is the one BUG-6 names; the collection half is pinned by
        :meth:`test_tag_in_config_file_collects_subclass_field` below.
        """
        base, plug = plugin_pair(5)
        cfg = tmp_path / "app.toml"
        cfg.write_text(f'[handler]\nclass = "{plug}.FileHandler"\n', newline="\n")
        flags = populating_loader.registered_flags(base.Config, argv=["--config", str(cfg)])
        assert flags is not None
        assert {"handler.class", "handler.path"} <= flags

    def test_tag_in_config_file_collects_subclass_field(
        self,
        loader: ConfargLoader,
        plugin_pair: Any,
        tmp_path: Path,
    ) -> None:
        """A subclass field typed on the CLI survives a tag that came from a --config file."""
        base, plug = plugin_pair(6)
        cfg = tmp_path / "app.toml"
        cfg.write_text(f'[handler]\nclass = "{plug}.FileHandler"\n', newline="\n")
        result = loader.load(base.Config, argv=["--config", str(cfg), "--handler.path", "/x"], env={})
        assert type(result.handler).__name__ == "FileHandler"
        assert result.handler.path == "/x"

    def test_custom_union_tag(self, loader: ConfargLoader, plugin_pair: Any) -> None:
        """The scan follows *union_tag*, not the literal 'class'."""
        base, plug = plugin_pair(2)
        result = loader.load(
            base.Config,
            argv=["--handler.kind", f"{plug}.FileHandler", "--handler.path", "/x"],
            env={},
            union_tag="kind",
        )
        assert type(result.handler).__name__ == "FileHandler"
        assert result.handler.path == "/x"

    def test_selector_and_subclass_fields_registered(
        self,
        populating_loader: ConfargLoader,
        plugin_pair: Any,
    ) -> None:
        """populate_* accepts both the selector and the named subclass's own flags."""
        base, plug = plugin_pair(3)
        argv = ["--handler.class", f"{plug}.FileHandler", "--handler.path", "/x"]
        flags = populating_loader.registered_flags(base.Config, argv=argv, config_flag="")
        assert flags is not None
        assert {"handler.class", "handler.path"} <= flags

    def test_root_level_tag(self, loader: ConfargLoader, plugin_pair: Any) -> None:
        """A bare --class selects an unimported subclass for a root target too."""
        base, plug = plugin_pair(4)
        result = loader.load(base.Handler, argv=["--class", f"{plug}.FileHandler", "--path", "/x"], env={})
        assert type(result).__name__ == "FileHandler"
        assert result.path == "/x"


@dataclass
class _DashValued:
    """One field per shape a ``--``-prefixed value has to reach."""

    key: str = ""
    tags: list[str] = dataclasses.field(default_factory=list)
    d: dict[str, str] = dataclasses.field(default_factory=dict)


class TestDashPrefixedValueContract:
    """``--key=--value`` delivers a ``--``-prefixed value on every front-end.

    The ``=`` form is the escape argparse, click and cyclopts all honor natively;
    vanilla split it back into two tokens before any flag-check ran, so the value
    was re-read as a flag.  The dict-subkey and append spellings go through the
    shared argv scan, so they were broken in all four front-ends.
    """

    def test_scalar(self, loader: ConfargLoader) -> None:
        """``--key=--value`` stores the dashed token as the field's value."""
        assert loader.load(_DashValued, argv=["--key=--value"], env={}).key == "--value"

    def test_scalar_single_dash(self, loader: ConfargLoader) -> None:
        """A single-dash value needs no escape but must keep working through the ``=`` form."""
        assert loader.load(_DashValued, argv=["--key=-v"], env={}).key == "-v"

    def test_dict_subkey(self, loader: ConfargLoader) -> None:
        """``--d.x=--v`` keys a dict with a dashed value."""
        assert loader.load(_DashValued, argv=["--d.x=--v"], env={}).d == {"x": "--v"}

    def test_list_element(self, loader: ConfargLoader) -> None:
        """``--tags=--a`` gives a one-element list, and stops before the next real flag."""
        cfg = loader.load(_DashValued, argv=["--tags=--a", "--key", "k"], env={})
        assert cfg.tags == ["--a"]
        assert cfg.key == "k"

    def test_list_append(self, loader: ConfargLoader) -> None:
        """``--tags+=--a`` appends a dashed element."""
        cfg = loader.load(_DashValued, argv=["--tags", "x", "--tags+=--a"], env={})
        assert cfg.tags == ["x", "--a"]

    def test_list_append_beside_a_bare_append(self, loader: ConfargLoader) -> None:
        """A bare append next door neither eats the ``=`` escape nor costs the dashed element."""
        cfg = loader.load(_DashValued, argv=["--tags", "x", "--tags+=--a", "--tags+"], env={})
        assert cfg.tags == ["x", "--a"]

    def test_only_the_eq_value_is_shielded(self, loader: ConfargLoader) -> None:
        """The shield covers the ``=`` value alone: a following ``--`` token is still a flag."""
        cfg = loader.load(_DashValued, argv=["--tags=--a", "--d.x=v"], env={})
        assert cfg.tags == ["--a"]
        assert cfg.d == {"x": "v"}


class TestRemoteConfigSourceContract:
    """A URL works wherever a config-file path works, identically on every front-end.

    Every channel reaches the same loader, so these are the tests that would catch a front-end
    that parsed a location differently or converted it to a path on the way in.
    """

    def test_config_flag_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """--config accepts a URL token."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 5432\n")
        cfg = loader.load(Simple, argv=["--config", f"{tmp_http}/app.yaml"], env={})
        assert cfg == Simple(host="served", port=5432)

    def test_config_flag_equals_form_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """The --config=<url> form parses the whole URL as one value."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 5432\n")
        cfg = loader.load(Simple, argv=[f"--config={tmp_http}/app.yaml"], env={})
        assert cfg == Simple(host="served", port=5432)

    def test_files_param_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """files= accepts a URL string alongside paths."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 9999\n")
        cfg = loader.load(Simple, argv=[], env={}, files=[f"{tmp_http}/app.yaml"])
        assert cfg == Simple(host="served", port=9999)

    def test_env_config_pointer_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """An env var naming a config location may name a URL."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 7777\n")
        cfg = loader.load(
            Simple,
            argv=[],
            env={"APP_CONFIG_FILE": f"{tmp_http}/app.yaml"},
            env_config="APP_CONFIG_FILE",
        )
        assert cfg == Simple(host="served", port=7777)

    def test_env_config_var_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """The <PREFIX>CONFIG env channel may name a URL."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 4444\n")
        cfg = loader.load(
            Simple,
            argv=[],
            env={"MYAPP_CONFIG": f"{tmp_http}/app.yaml"},
            env_prefix="MYAPP_",
        )
        assert cfg == Simple(host="served", port=4444)

    def test_subkey_config_flag_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """--config.<subpath> mounts a served document under that key."""
        (tmp_path / "db.yaml").write_text("host: db_host\nport: 5555\nname: db_name\n")
        cfg = loader.load(AppConfig, argv=["--config.db", f"{tmp_http}/db.yaml"], env={})
        assert cfg.db == DbConfig(host="db_host", port=5555, name="db_name")

    def test_subkey_env_config_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """CONFIG__<SUBPATH> mounts a served document under that key."""
        (tmp_path / "db.yaml").write_text("host: db_host\nport: 5555\nname: db_name\n")
        cfg = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_CONFIG__DB": f"{tmp_http}/db.yaml"},
            env_prefix="MYAPP_",
        )
        assert cfg.db == DbConfig(host="db_host", port=5555, name="db_name")

    def test_append_config_flag_takes_a_url(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """--config.<subpath>+ appends a served document to a list field."""
        (tmp_path / "one.yaml").write_text("host: appended\nport: 1\n")
        cfg = loader.load(WithCsvRows, argv=["--config.db+", f"{tmp_http}/one.yaml"], env={})
        assert cfg.db == [Simple(host="appended", port=1)]

    def test_a_url_and_a_path_merge_in_order(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """A URL and a local path are one priority level, applied left to right."""
        (tmp_path / "base.yaml").write_text("host: base\nport: 1000\n")
        override = tmp_path / "override.yaml"
        override.write_text("port: 2000\n")
        cfg = loader.load(
            Simple,
            argv=["--config", f"{tmp_http}/base.yaml", "--config", str(override)],
            env={},
        )
        assert cfg == Simple(host="base", port=2000)

    def test_cli_still_overrides_a_url_config(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """Source precedence is unchanged: a URL is a config file, below env and CLI."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 1111\n")
        cfg = loader.load(Simple, argv=["--config", f"{tmp_http}/app.yaml", "--port", "2222"], env={})
        assert cfg == Simple(host="served", port=2222)

    def test_env_still_overrides_a_url_config(self, loader: ConfargLoader, tmp_path: Path, tmp_http: str) -> None:
        """A served document loses to an inline env var, as a local file does."""
        (tmp_path / "app.yaml").write_text("host: served\nport: 1111\n")
        cfg = loader.load(
            Simple,
            argv=["--config", f"{tmp_http}/app.yaml"],
            env={"MYAPP_PORT": "3333"},
            env_prefix="MYAPP_",
        )
        assert cfg == Simple(host="served", port=3333)

    def test_a_file_url_equals_the_path_it_names(self, loader: ConfargLoader, tmp_yaml) -> None:
        """file:// is not a second code path: it produces the same merged dict."""
        cfg_file = tmp_yaml("host: filehost\nport: 5432\n")
        from_path = loader.merge(Simple, argv=["--config", str(cfg_file)], env={})
        from_url = loader.merge(Simple, argv=["--config", cfg_file.as_uri()], env={})
        assert from_path == from_url

    def test_a_class_tag_in_a_served_document_is_seen(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        tmp_http: str,
    ) -> None:
        """The tag pre-scan reads served documents too, so a subclass field still gets its flag."""
        (tmp_path / "app.yaml").write_text(f"class: {__name__}._SQLiteDB\n")
        result = loader.load(
            _BaseDB,
            argv=["--config", f"{tmp_http}/app.yaml", "--dbpath", "/var/db/app.sqlite"],
            env={},
        )
        assert result == _SQLiteDB(dbpath="/var/db/app.sqlite")

    def test_an_unregistered_scheme_is_reported(self, loader: ConfargLoader) -> None:
        """Every front-end reports an unknown scheme the same way."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="No handler registered"):
            loader.load(Simple, argv=["--config", "gs://bucket/app.yaml"], env={})

    def test_a_registered_scheme_reaches_every_front_end(
        self,
        loader: ConfargLoader,
        scheme_registry,
    ) -> None:
        """A handler registered once serves all five front-ends, through every channel."""
        confarg.register_scheme("mem", lambda loc: b"host: from-mem\nport: 8080\n")
        cfg = loader.load(Simple, argv=["--config", "mem://anywhere/app.yaml"], env={})
        assert cfg == Simple(host="from-mem", port=8080)


# ---------------------------------------------------------------------------
# Mount parity: --config.<path>, CONFIG__<PATH> and __include__ are one operation
# ---------------------------------------------------------------------------


@dataclass
class _MountHost:
    """Target whose one field is a free-form node, so any fragment shape can land there."""

    node: Any = None


@dataclass
class _MountTagHost:
    """Target with a union-typed node, so a fragment can name its variant with a class tag."""

    db: _RootSQLite | _RootDBServer | None = None


class TestMountParity:
    """The three mount routes accept the same fragment and produce the same merged dict.

    They are spelled differently on purpose
    (docs-dev/architecture/design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel), but
    what they mount does not differ: each reads its value as an ``__include__`` value through
    one resolver (docs-dev/architecture/config-files/mounting.md#mounting). Every route used to have
    its own loader, and they diverged -- the CLI and env routes refused non-dict roots and data
    files that ``__include__`` accepted at the same node, and had no spelling for the CSV
    options at all.
    """

    @pytest.mark.parametrize(
        ("fragment_name", "fragment", "expected"),
        [
            ("frag.yaml", "a: 1\nb: two\n", {"a": 1, "b": "two"}),
            ("frag.yaml", "- 1\n- 2\n", [1, 2]),
            ("frag.yaml", "42\n", 42),
            ("frag.json", '["x", "y"]', ["x", "y"]),
        ],
        ids=["dict-root", "list-root", "scalar-root", "json-list-root"],
    )
    def test_every_route_mounts_every_fragment_shape(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        fragment_name: str,
        fragment: str,
        expected: Any,
    ) -> None:
        """Test that all three routes mount a fragment of any root type identically."""
        frag = tmp_path / fragment_name
        frag.write_text(fragment, encoding="utf-8")
        via_include = tmp_path / "via_include.yaml"
        via_include.write_text(f"node:\n  {INCLUDE_KEY}: ./{fragment_name}\n", encoding="utf-8")

        from_cli = loader.merge(_MountHost, argv=["--config.node", str(frag)], env={})
        from_env = loader.merge(
            _MountHost,
            argv=[],
            env={"MYAPP_CONFIG__NODE": str(frag)},
            env_prefix="MYAPP_",
        )
        from_file = loader.merge(_MountHost, argv=[], env={}, files=[via_include])

        assert from_cli == {"node": expected}
        assert from_env == from_cli
        assert from_file == from_cli

    def test_a_subpath_naming_no_field_is_refused_by_the_flag_routes(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
    ) -> None:
        """The two routes that intercept a flag check their subpath; the file route cannot (BUG-50).

        A file's mount key is a node the file author wrote, so the same typo is data there
        and surfaces at ``build()`` as an unknown field instead.
        """
        frag = tmp_path / "frag.yaml"
        frag.write_text("host: h\n", encoding="utf-8")
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.merge(_MountHost, argv=["--config.nodee", str(frag)], env={})
        with pytest.raises(_REJECTS_BARE_FLAG):
            loader.merge(
                _MountHost,
                argv=[],
                env={"MYAPP_CONFIG__NODEE": str(frag)},
                env_prefix="MYAPP_",
            )

    def test_every_route_takes_the_options_object(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Test that the {path, orient, header} include form is spelled in every channel."""
        csv = tmp_path / "users.csv"
        csv.write_text("name,age\nalice,30\n", encoding="utf-8")
        spec = {"path": csv.as_posix(), "orient": "columns"}
        via_include = tmp_path / "via_include.yaml"
        via_include.write_text(
            f"node:\n  {INCLUDE_KEY}:\n    path: ./users.csv\n    orient: columns\n",
            encoding="utf-8",
        )
        expected = {"node": {"name": ["alice"], "age": ["30"]}}

        from_cli = loader.merge(_MountHost, argv=["--config.node", json.dumps(spec)], env={})
        from_env = loader.merge(
            _MountHost,
            argv=[],
            env={"MYAPP_CONFIG__NODE": json.dumps(spec)},
            env_prefix="MYAPP_",
        )
        from_file = loader.merge(_MountHost, argv=[], env={}, files=[via_include])

        assert from_cli == expected
        assert from_env == expected
        assert from_file == expected

    def test_a_data_file_mounts_at_a_node_from_the_cli(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Test that a CSV lands at a subpath without the append suffix.

        It used to be refused there: ``_LOADERS`` held no data format, so only
        ``--config.<path>+`` could reach one.
        """
        csv = tmp_path / "rows.csv"
        csv.write_text("val\nalpha\nbeta\n", encoding="utf-8")
        target = make_target("vals", list[str], default_factory=list)
        result = loader.load(target, argv=["--config.vals", str(csv)], env={})
        assert result.vals == ["alpha", "beta"]

    def test_include_inside_an_appended_fragment_is_resolved(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
    ) -> None:
        """Test that an __include__ in a file reached by --config.<path>+ is resolved.

        The append route had its own loader, which skipped include resolution, so the dunder
        key survived into the merged dict as ordinary user data (BUG-42).
        """
        (tmp_path / "part.yaml").write_text("host: inner\n", encoding="utf-8")
        item = tmp_path / "item.yaml"
        item.write_text(f"{INCLUDE_KEY}: part.yaml\n", encoding="utf-8")
        target = make_target("items", list[dict[str, str]], default_factory=list)

        merged = loader.merge(target, argv=["--config.items+", str(item)], env={})
        assert merged == {"items": {"+": [{"host": "inner"}]}}

    def test_append_parity_between_cli_and_file(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Test that --config.f+ FILE and f+: {__include__: FILE} mean the same thing.

        Both extend the list with the fragment's items: appending is the ``+`` operator's job
        and the mount has no say in it
        (docs-dev/architecture/design-decisions/plus-is-a-merge-operator.md#the--suffix-is-a-merge-operator-not-a-list-spelling).
        """
        rows = tmp_path / "rows.yaml"
        rows.write_text("- gamma\n- delta\n", encoding="utf-8")
        base = tmp_path / "base.yaml"
        base.write_text("tags:\n  - alpha\n", encoding="utf-8")
        via_file = tmp_path / "via_file.yaml"
        via_file.write_text(f"tags+:\n  {INCLUDE_KEY}: ./rows.yaml\n", encoding="utf-8")
        target = make_target("tags", list[str], default_factory=list)

        from_cli = loader.load(target, argv=["--config.tags+", str(rows)], env={}, files=[base])
        from_file = loader.load(target, argv=[], env={}, files=[base, via_file])

        assert from_cli.tags == ["alpha", "gamma", "delta"]
        assert from_file.tags == from_cli.tags

    def test_class_tag_in_an_include_replaces_the_node(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Test that a class tag inside an include discards the base node, as --config does.

        The include merges did not thread ``union_tag``, so the rule in
        docs-dev/architecture/design-decisions/class-tag-replaces.md#a-class-tag-replaces-not-merges held for
        ``--config.db`` and not for ``db: {__include__: …}``.
        """
        sqlite = tmp_path / "sqlite.yaml"
        sqlite.write_text(
            f"class: {__name__}._RootSQLite\ndbpath: /tmp/db.sqlite\n",
            encoding="utf-8",
        )
        base = tmp_path / "base.yaml"
        base.write_text("db:\n  host: example.com\n  port: 5432\n  name: mydb\n", encoding="utf-8")
        via_include = tmp_path / "via_include.yaml"
        via_include.write_text(f"db:\n  {INCLUDE_KEY}: ./sqlite.yaml\n", encoding="utf-8")

        from_cli = loader.merge(_MountTagHost, argv=["--config.db", str(sqlite)], env={}, files=[base])
        from_file = loader.merge(_MountTagHost, argv=[], env={}, files=[base, via_include])

        assert "host" not in from_cli["db"]  # the tag replaced the server config outright
        assert from_file == from_cli


# ---------------------------------------------------------------------------
# A field named exactly like the union tag is a field on every front-end (BUG-102)
# ---------------------------------------------------------------------------


@dataclass
class _KindFieldTarget:
    Kind: str = "field"


@dataclass
class _KindDispatchBase:
    Kind: str = "field"


@dataclass
class _KindDispatchSub(_KindDispatchBase):
    extra: str = "e"


@dataclass
class _KindUnionVariant:
    Kind: str


@dataclass
class _KindOtherVariant:
    other: str = "o"


@dataclass
class _KindOnlySubBase:
    """Base whose subclass alone owns the tag's spelling (BUG-103)."""


@dataclass
class _KindOnlySub(_KindOnlySubBase):
    Kind: str


class TestUnionTagFieldCollision:
    """The exact tag/field collision settles on the field, identically on all front-ends.

    The registration builders skipped a field named like the tag and registered the
    tag flag on its spelling, so the adapters rejected the field outright while
    vanilla imported its value as a class path. The field flag owns the spelling
    now; the tag flag is registered only where no field bears its name.
    """

    def test_shadowed_field_flag_sets_field(self, loader: ConfargLoader) -> None:
        """--Kind v builds the field on every front-end."""
        result = loader.load(_KindFieldTarget, argv=["--Kind", "v"], env={}, union_tag="Kind")
        assert result == _KindFieldTarget(Kind="v")

    def test_shadowed_field_on_dispatch_struct(self, loader: ConfargLoader) -> None:
        """A subclassed base with the colliding field still builds from its own field."""
        result = loader.load(_KindDispatchBase, argv=["--Kind", "v"], env={}, union_tag="Kind")
        assert result == _KindDispatchBase(Kind="v")

    def test_shadowed_variant_field_on_union(self, loader: ConfargLoader) -> None:
        """A union whose variant owns the colliding field builds that variant."""
        result = loader.load(
            _KindUnionVariant | _KindOtherVariant,
            argv=["--Kind", "v"],
            env={},
            union_tag="Kind",
        )
        assert result == _KindUnionVariant(Kind="v")

    def test_subclass_only_field_builds_owning_subclass(self, loader: ConfargLoader) -> None:
        """A subclass-only field spelled like the tag keeps its value on every front-end.

        Construction once read the tag-shaped key as a class path and stripped the
        value, so the field the user set went missing (BUG-103); the merged dict is
        the field's, and the subclass that owns the field is built from it.
        """
        result = loader.load(_KindOnlySubBase, argv=["--Kind", "v"], env={}, union_tag="Kind")
        assert result == _KindOnlySub(Kind="v")

    def test_subclass_only_field_merge_matches_vanilla(self, loader: ConfargLoader) -> None:
        """The merged dict carries the field's value, byte-identical to vanilla's."""
        merged = loader.merge(_KindOnlySubBase, argv=["--Kind", "v"], env={}, union_tag="Kind")
        assert merged == {"Kind": "v"}

    def test_shadowed_tag_use_warns_on_every_frontend(self, loader: ConfargLoader) -> None:
        """Setting the colliding field warns that no class-path tag dispatches.

        The warning is a build()-time one, so all five front-ends and every channel
        inherit it from the one construction site; the assertion runs per front-end
        to pin the parity, not to restate the behavior five times.
        """
        with pytest.warns(ConfargWarning, match="selected structurally"):
            result = loader.load(_KindOnlySubBase, argv=["--Kind", "v"], env={}, union_tag="Kind")
        assert result == _KindOnlySub(Kind="v")

    def test_registration_subclass_only_field_flag_wins(self) -> None:
        """The subclass-only field takes the spelling; no tag flag is registered on it."""
        flags = build_static_flags(_KindOnlySubBase, union_tag="Kind", config_flag="")
        by_name = {f.name: f for f in flags}
        assert "Kind" in by_name
        assert by_name["Kind"].metavar != "DOTTED.CLASS.PATH"

    def test_merge_matches_vanilla(self, loader: ConfargLoader) -> None:
        """The merged dict carries the field's value, byte-identical to vanilla's."""
        merged = loader.merge(_KindFieldTarget, argv=["--Kind", "v"], env={}, union_tag="Kind")
        assert merged == {"Kind": "v"}

    def test_registration_field_flag_wins(
        self,
    ) -> None:
        """The colliding field is registered as a field flag; no tag flag takes its spelling."""
        flags = build_static_flags(_KindDispatchBase, union_tag="Kind", config_flag="")
        by_name = {f.name: f for f in flags}
        assert "Kind" in by_name
        assert by_name["Kind"].metavar != "DOTTED.CLASS.PATH"

    def test_registration_union_root_field_flag_wins(
        self,
    ) -> None:
        """A union root registers the colliding variant field, not the tag flag."""
        flags = build_static_flags(_KindUnionVariant | _KindOtherVariant, union_tag="Kind", config_flag="")
        by_name = {f.name: f for f in flags}
        assert "Kind" in by_name
        assert by_name["Kind"].metavar != "DOTTED.CLASS.PATH"

    def test_unshadowed_tag_flag_still_registered(
        self,
    ) -> None:
        """Without the colliding field, the tag flag keeps its spelling."""
        flags = build_static_flags(_KindOtherVariant | int, union_tag="Kind", config_flag="")
        by_name = {f.name: f for f in flags}
        assert by_name["Kind"].metavar == "DOTTED.CLASS.PATH"
