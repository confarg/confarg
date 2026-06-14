# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared dataclass definitions, fixtures, and hypothesis strategies for confarg tests."""

from __future__ import annotations

import enum
import textwrap
from dataclasses import dataclass, field, make_dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests._loaders import ConfargLoader

import pytest
from hypothesis import strategies as st

from tests._loaders import ALL_LOADERS, POPULATING_LOADERS, REPEATED_FLAG_LOADERS, SPACE_SEP_LOADERS

# ---------------------------------------------------------------------------
# Dynamic single-field dataclass factory
# ---------------------------------------------------------------------------

_SENTINEL = object()


def make_target(
    field_name: str,
    field_type: Any,
    *,
    default: object = _SENTINEL,
    default_factory: Callable[[], Any] | object = _SENTINEL,
) -> type[Any]:
    """Build a single-field dataclass on the fly via ``make_dataclass``.

    Replaces trivial hand-written wrappers like ``WithOptional``, ``WithList``, etc.
    """
    if default is not _SENTINEL:
        fields = [(field_name, field_type, field(default=default))]
    elif default_factory is not _SENTINEL:
        fields = [(field_name, field_type, field(default_factory=cast("Callable[[], Any]", default_factory)))]
    else:
        fields = [(field_name, field_type)]
    return cast("type[Any]", make_dataclass("Target", fields))


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Color(enum.Enum):
    """Simple enum for testing."""

    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class IntColor(enum.IntEnum):
    """IntEnum for testing."""

    RED = 1
    GREEN = 2
    BLUE = 3


# ---------------------------------------------------------------------------
# Type alias (Python 3.12+)
# ---------------------------------------------------------------------------

type HostPort = tuple[str, int]


@dataclass
class WithHostPort:
    """Dataclass using a Python 3.12+ type alias field."""

    endpoint: HostPort = ("localhost", 80)


# Additional Python 3.12+ type aliases for alias-shape tests.
type AliasInt = int
type AliasDc = DbConfig
type AliasUnion = DbConfig | CacheConfig
type AliasAnnotated = Annotated[DbConfig | CacheConfig, "metadata"]


@dataclass
class WithAliasDc:
    """Dataclass whose field type is a type-alias for another dataclass."""

    db: AliasDc


@dataclass
class WithAliasUnion:
    """Dataclass whose field type is a type-alias for a union of dataclasses."""

    service: AliasUnion


@dataclass
class WithAliasAnnotated:
    """Dataclass whose field type is a type-alias wrapping an Annotated union."""

    service: AliasAnnotated


# ---------------------------------------------------------------------------
# Dataclasses — flat
# ---------------------------------------------------------------------------


@dataclass
class Flat:
    """Flat dataclass with common leaf types, no defaults."""

    name: str
    count: int
    rate: float
    verbose: bool


@dataclass
class WithDefaults:
    """Every field has a default."""

    name: str = "default"
    count: int = 0
    rate: float = 1.0
    verbose: bool = False


@dataclass
class Empty:
    """Dataclass with no fields."""


# ---------------------------------------------------------------------------
# Dataclasses — nested
# ---------------------------------------------------------------------------


@dataclass
class DbConfig:
    """Database configuration."""

    host: str
    port: int
    name: str


@dataclass
class CacheConfig:
    """Cache configuration."""

    enabled: bool = True
    ttl: int = 300


@dataclass
class AppConfig:
    """Top-level app config with nested dataclasses."""

    db: DbConfig
    cache: CacheConfig
    debug: bool = False


@dataclass
class DeepNested:
    """Three levels of nesting."""

    app: AppConfig
    version: str = "1.0"


@dataclass
class WithCollections:
    """Multiple collection types."""

    names: list[str] = field(default_factory=list)
    counts: tuple[int, ...] = ()
    tags: set[str] = field(default_factory=set)
    mapping: dict[str, int] = field(default_factory=dict)


@dataclass
class WithNestedList:
    """Dataclass containing a list of nested dataclasses."""

    servers: list[DbConfig] = field(default_factory=list)


@dataclass
class WithOptionalNested:
    """Optional nested dataclass."""

    db: DbConfig | None = None


@dataclass
class WithUnionNested:
    """Union with nested dataclass."""

    value: int | DbConfig = 0


# ---------------------------------------------------------------------------
# Union edge-case dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ServerTcp:
    """Server with a numeric port."""

    host: str
    port: int


@dataclass
class ServerUnix:
    """Server with a string socket path."""

    host: str
    port: str  # same field name, different type


@dataclass
class WithUnionOverlap:
    """Union of two dataclasses sharing a field name with different types."""

    server: ServerTcp | ServerUnix


@dataclass
class PgConfig:
    """Postgres-specific config."""

    host: str
    port: int
    sslmode: str = "prefer"


@dataclass
class RedisConfig:
    """Redis-specific config."""

    host: str
    port: int
    db: int = 0


@dataclass
class WithUnionDisjointDefaults:
    """Union of two dataclasses with disjoint default fields for disambiguation."""

    backend: PgConfig | RedisConfig


@dataclass
class SqlCredentials:
    """Credentials for a SQL database."""

    username: str
    password: str


@dataclass
class TokenCredentials:
    """Credentials via bearer token."""

    token: str
    expires: int


@dataclass
class SqlBackend:
    """Backend using SQL credentials."""

    host: str
    auth: SqlCredentials


@dataclass
class TokenBackend:
    """Backend using token credentials."""

    host: str
    auth: TokenCredentials


@dataclass
class WithUnionDeepDisambiguation:
    """Union of two dataclasses whose same-named field is itself a dataclass.

    Requires recursive disambiguation on the nested fields.
    """

    backend: SqlBackend | TokenBackend


@dataclass
class CircleShape:
    """A circle defined by its radius."""

    x: float
    y: float
    radius: float


@dataclass
class RectangleShape:
    """A rectangle defined by width and height."""

    x: float
    y: float
    width: float
    height: float


@dataclass
class SquareShape:
    """A square — same fields as CircleShape (x, y, radius→side), structurally identical."""

    x: float
    y: float
    radius: float  # deliberately same name & type as CircleShape


@dataclass
class WithUnionAmbiguous:
    """Union of two structurally identical dataclasses — requires class tag."""

    shape: CircleShape | SquareShape


@dataclass
class WithUnionAmbiguousThree:
    """Union of three dataclasses, two of which are structurally identical."""

    shape: CircleShape | RectangleShape | SquareShape


# ---------------------------------------------------------------------------
# Union with Literal discriminators
# ---------------------------------------------------------------------------


@dataclass
class TaggedBool:
    """Union variant with bool value and Literal id."""

    value: bool
    id: Literal[1]


@dataclass
class TaggedStr:
    """Union variant with str value and Literal id."""

    value: str
    id: Literal[2]


@dataclass
class WithTaggedUnion:
    """Union of TaggedBool | TaggedStr, discriminated by Literal id."""

    entry: TaggedBool | TaggedStr


@dataclass
class MultiVal:
    """Union variant with list data."""

    data: list[int]
    tag: Literal["multi"]


@dataclass
class SingleVal:
    """Union variant with str data."""

    data: str
    tag: Literal["single"]


@dataclass
class WithCollectionOrScalar:
    """Union of MultiVal | SingleVal — data disagrees (list vs str)."""

    entry: MultiVal | SingleVal


@dataclass
class BoolVariantA:
    """Bool flag variant A."""

    flag: bool
    id: Literal["a"]


@dataclass
class BoolVariantB:
    """Bool flag variant B."""

    flag: bool
    id: Literal["b"]


@dataclass
class WithAgreedBoolUnion:
    """Union of BoolVariantA | BoolVariantB — flag type agrees (both bool)."""

    entry: BoolVariantA | BoolVariantB


# ---------------------------------------------------------------------------
# Union with type: Literal discriminator (canonical pattern)
# ---------------------------------------------------------------------------


@dataclass
class TypedVariantA:
    """Union variant A — type field is the only structural difference."""

    type: Literal["a"]
    value: int


@dataclass
class TypedVariantB:
    """Union variant B — type field is the only structural difference."""

    type: Literal["b"]
    value: int


@dataclass
class WithTypeLiteralUnion:
    """Union of TypedVariantA | TypedVariantB, discriminated by type: Literal."""

    item: TypedVariantA | TypedVariantB


# ---------------------------------------------------------------------------
# Union float/str ambiguity (inf / nan)
# ---------------------------------------------------------------------------


@dataclass
class FloatHolder:
    """Holds a single float value."""

    value: float


@dataclass
class StrHolder:
    """Holds a single string value."""

    value: str


@dataclass
class WithUnionFloatStr:
    """Union of FloatHolder | StrHolder — ambiguous for string "inf" / "nan"."""

    item: FloatHolder | StrHolder


# ---------------------------------------------------------------------------
# Fixtures — temp config files
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_toml(tmp_path: Path):
    """Create a temporary TOML config file.

    Returns:
        A callable that writes TOML content and returns the file path.
    """

    def _write(content: str, filename: str = "config.toml") -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(content))
        return p

    return _write


@pytest.fixture
def tmp_yaml(tmp_path: Path):
    """Create a temporary YAML config file.

    Returns:
        A callable that writes YAML content and returns the file path.
    """

    def _write(content: str, filename: str = "config.yaml") -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(content))
        return p

    return _write


@pytest.fixture
def tmp_json(tmp_path: Path):
    """Create a temporary JSON config file.

    Returns:
        A callable that writes JSON content and returns the file path.
    """

    def _write(content: str, filename: str = "config.json") -> Path:
        p = tmp_path / filename
        p.write_text(textwrap.dedent(content))
        return p

    return _write


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@pytest.fixture(params=ALL_LOADERS, ids=[ldr.id for ldr in ALL_LOADERS])
def loader(request: pytest.FixtureRequest) -> ConfargLoader:
    """Parametrised loader fixture — runs each test against all four CLI integrations."""
    return request.param


@pytest.fixture(params=SPACE_SEP_LOADERS, ids=[ldr.id for ldr in SPACE_SEP_LOADERS])
def space_sep_loader(request: pytest.FixtureRequest) -> ConfargLoader:
    """Loaders that accept space-separated list args: vanilla, argparse, cyclopts."""
    return request.param


@pytest.fixture(params=REPEATED_FLAG_LOADERS, ids=[ldr.id for ldr in REPEATED_FLAG_LOADERS])
def repeated_loader(request: pytest.FixtureRequest) -> ConfargLoader:
    """Loaders that accept repeated flags for lists: click, cyclopts."""
    return request.param


@pytest.fixture(params=POPULATING_LOADERS, ids=[ldr.id for ldr in POPULATING_LOADERS])
def populating_loader(request: pytest.FixtureRequest) -> ConfargLoader:
    """Loaders with a populate_* registration step: argparse, click, cyclopts."""
    return request.param


valid_identifiers: st.SearchStrategy[str] = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)

leaf_ints: st.SearchStrategy[int] = st.integers(min_value=-10_000, max_value=10_000)
leaf_floats: st.SearchStrategy[float] = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)
leaf_strs: st.SearchStrategy[str] = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=0,
    max_size=50,
)
leaf_bools: st.SearchStrategy[bool] = st.booleans()
cli_safe_strs: st.SearchStrategy[str] = leaf_strs.filter(lambda s: not s.startswith("-"))

env_prefixes: st.SearchStrategy[str] = st.from_regex(r"[A-Z][A-Z0-9_]{0,9}", fullmatch=True)
