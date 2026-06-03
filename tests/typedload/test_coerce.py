# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for register_leaf_type and the _LEAF_COERCIONS extension mechanism."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

import confarg
from confarg._types import _StrToken
from confarg.exceptions import TypeCoercionError
from confarg.typedload._coerce import _LEAF_COERCIONS, _coerce_leaf, _try_coerce
from confarg.typedload._construct import construct

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_uuid(request: pytest.FixtureRequest):
    """Remove UUID from _LEAF_COERCIONS after each test that registers it."""
    yield
    _LEAF_COERCIONS.pop(UUID, None)


# ---------------------------------------------------------------------------
# TestRegisterLeafType — public API
# ---------------------------------------------------------------------------


class TestRegisterLeafType:
    """Tests for the confarg.register_leaf_type() public API."""

    def test_register_adds_to_leaf_coercions(self) -> None:
        """register_leaf_type adds the type to _LEAF_COERCIONS."""
        confarg.register_leaf_type(UUID, UUID)
        assert UUID in _LEAF_COERCIONS

    def test_register_callable_is_stored(self) -> None:
        """The coerce callable passed to register_leaf_type is stored verbatim."""
        coerce = lambda v: UUID(str(v))  # noqa: E731
        confarg.register_leaf_type(UUID, coerce)
        assert _LEAF_COERCIONS[UUID] is coerce

    def test_register_overrides_previous(self) -> None:
        """Re-registering the same type replaces the previous callable."""
        confarg.register_leaf_type(UUID, UUID)
        coerce2 = lambda v: UUID(str(v))  # noqa: E731
        confarg.register_leaf_type(UUID, coerce2)
        assert _LEAF_COERCIONS[UUID] is coerce2


# ---------------------------------------------------------------------------
# TestCoerceLeafCustomType — _coerce_leaf with registered type
# ---------------------------------------------------------------------------

_UUID_STR = "12345678-1234-5678-1234-567812345678"
_UUID_OBJ = UUID(_UUID_STR)


class TestCoerceLeafCustomType:
    """Tests for _coerce_leaf() with registered custom types."""

    def test_coerce_from_str_token(self) -> None:
        """Custom type is coerced from a _StrToken (simulating CLI/env input)."""
        confarg.register_leaf_type(UUID, UUID)
        token = _StrToken(_UUID_STR)
        result = _coerce_leaf(UUID, token)
        assert result == _UUID_OBJ
        assert isinstance(result, UUID)

    def test_coerce_from_native_object(self) -> None:
        """Custom type is passed through when already an instance (file input)."""
        confarg.register_leaf_type(UUID, UUID)
        result = _coerce_leaf(UUID, _UUID_OBJ)
        assert result == _UUID_OBJ

    def test_coerce_invalid_raises(self) -> None:
        """Invalid input raises TypeCoercionError."""
        confarg.register_leaf_type(UUID, UUID)
        token = _StrToken("not-a-uuid")
        with pytest.raises(TypeCoercionError):
            _coerce_leaf(UUID, token)

    def test_unregistered_type_raises(self) -> None:
        """A type that is not registered as a leaf raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unsupported leaf type"):
            _coerce_leaf(UUID, _StrToken(_UUID_STR))


# ---------------------------------------------------------------------------
# TestTryCoerceCustomType — eager coercion during merge
# ---------------------------------------------------------------------------


class TestTryCoerceCustomType:
    """Tests for _try_coerce() with registered custom leaf types."""

    def test_registered_type_is_eagerly_coerced(self) -> None:
        """Registered types are eagerly coerced by _try_coerce (not deferred to construct)."""
        confarg.register_leaf_type(UUID, UUID)
        token = _StrToken(_UUID_STR)
        result = _try_coerce(UUID, token)
        assert result == _UUID_OBJ
        assert isinstance(result, UUID)

    def test_unregistered_type_returns_token(self) -> None:
        """Unregistered types are not eagerly coerced — token passes through unchanged."""
        token = _StrToken(_UUID_STR)
        result = _try_coerce(UUID, token)
        assert result is token

    def test_optional_registered_type_coerced(self) -> None:
        """Optional[T] with registered T is eagerly coerced."""
        confarg.register_leaf_type(UUID, UUID)
        token = _StrToken(_UUID_STR)
        result = _try_coerce(UUID | None, token)
        assert result == _UUID_OBJ

    def test_invalid_registered_returns_token(self) -> None:
        """When coercion fails, _try_coerce returns the original token unchanged."""
        confarg.register_leaf_type(UUID, UUID)
        token = _StrToken("not-a-uuid")
        result = _try_coerce(UUID, token)
        assert result is token


# ---------------------------------------------------------------------------
# TestConstructCustomType — construct() integration
# ---------------------------------------------------------------------------


class TestConstructCustomType:
    """Tests for construct() dispatching registered types to _coerce_leaf."""

    def test_construct_from_str_token(self) -> None:
        """construct() coerces a _StrToken to the registered type."""
        confarg.register_leaf_type(UUID, UUID)
        result = construct(UUID, _StrToken(_UUID_STR))
        assert result == _UUID_OBJ

    def test_construct_optional_from_str_token(self) -> None:
        """construct() coerces a _StrToken through an Optional[registered] union."""
        confarg.register_leaf_type(UUID, UUID)
        result = construct(UUID | None, _StrToken(_UUID_STR))
        assert result == _UUID_OBJ

    def test_construct_optional_none(self) -> None:
        """construct() returns None for an Optional[registered] field when data is None."""
        confarg.register_leaf_type(UUID, UUID)
        result = construct(UUID | None, None)
        assert result is None


# ---------------------------------------------------------------------------
# TestBuildEndToEnd — confarg.build() with a registered leaf type
# ---------------------------------------------------------------------------


@dataclass
class _Config:
    id: UUID
    token: UUID | None = None


class TestBuildEndToEnd:
    """End-to-end tests: confarg.build() with a registered leaf type in a dataclass."""

    def test_build_from_str_token(self) -> None:
        """End-to-end: confarg.build() constructs a dataclass with a registered leaf field."""
        confarg.register_leaf_type(UUID, UUID)
        result = confarg.build(_Config, {"id": _StrToken(_UUID_STR)})
        assert result == _Config(id=_UUID_OBJ, token=None)

    def test_build_from_native_uuid(self) -> None:
        """End-to-end: confarg.build() passes through a natively-parsed UUID (from file)."""
        confarg.register_leaf_type(UUID, UUID)
        result = confarg.build(_Config, {"id": _UUID_OBJ})
        assert result == _Config(id=_UUID_OBJ, token=None)

    def test_build_optional_field(self) -> None:
        """build() handles an Optional registered field with a _StrToken value."""
        confarg.register_leaf_type(UUID, UUID)
        result = confarg.build(
            _Config,
            {"id": _StrToken(_UUID_STR), "token": _StrToken(_UUID_STR)},
        )
        assert result == _Config(id=_UUID_OBJ, token=_UUID_OBJ)


# ---------------------------------------------------------------------------
# TestNoneTypeCoercion — _coerce_leaf and _try_coerce for NoneType
# ---------------------------------------------------------------------------


class TestNoneTypeCoercion:
    """Tests for NoneType coercion: only None and recognised null tokens are accepted."""

    def test_none_passthrough(self) -> None:
        """A Python None value passes through unchanged."""
        assert _coerce_leaf(type(None), None) is None

    def test_none_token(self) -> None:
        """The string token 'none' is accepted as a valid null representation."""
        assert _coerce_leaf(type(None), _StrToken("none")) is None

    def test_null_token(self) -> None:
        """The string token 'null' is accepted as a valid null representation."""
        assert _coerce_leaf(type(None), _StrToken("null")) is None

    def test_case_insensitive(self) -> None:
        """Null token matching is case-insensitive."""
        assert _coerce_leaf(type(None), _StrToken("NONE")) is None
        assert _coerce_leaf(type(None), _StrToken("NULL")) is None
        assert _coerce_leaf(type(None), _StrToken("Null")) is None

    def test_arbitrary_string_raises(self) -> None:
        """An unrecognised string raises TypeCoercionError instead of silently returning None."""
        with pytest.raises(TypeCoercionError):
            _coerce_leaf(type(None), _StrToken("x"))

    def test_empty_string_accepted(self) -> None:
        """An empty string token (e.g. NOTHING= env var) is accepted as None."""
        assert _coerce_leaf(type(None), _StrToken("")) is None

    def test_try_coerce_none_token(self) -> None:
        """_try_coerce eagerly converts 'none' tokens for NoneType fields."""
        result = _try_coerce(type(None), _StrToken("none"))
        assert result is None

    def test_try_coerce_invalid_returns_token(self) -> None:
        """_try_coerce returns the token unchanged when coercion would fail."""
        token = _StrToken("x")
        result = _try_coerce(type(None), token)
        assert result is token

    def test_load_integration_none_token(self) -> None:
        """confarg.load() accepts 'none' for a value: None field."""

        @dataclass
        class Config:
            value: None

        result = confarg.load(Config, argv=["--value", "none"], env={})
        assert result == Config(value=None)

    def test_load_integration_rejects_arbitrary(self) -> None:
        """confarg.load() rejects arbitrary strings for a value: None field."""

        @dataclass
        class Config:
            value: None

        with pytest.raises(TypeCoercionError):
            confarg.load(Config, argv=["--value", "x"], env={})
