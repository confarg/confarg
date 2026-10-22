# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for _naming.py -- what a node names, and the keys that gives it.

The channels' agreement is a contract test (tests/cli/test_backend_contract.py); here, that the
listing of a node's keys reads the very naming its typing reads (REF-106).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from confarg._naming import Named, named_child, named_member_names

if TYPE_CHECKING:
    from confarg._merge import MergeDict


@dataclass
class _Base:
    """A struct whose subclass a tag may name."""

    a: int = 0


@dataclass
class _Sub(_Base):
    """A subclass the tag names, with a field of its own."""

    camelCase: int = 0  # a member the environment spells by its capitals


@dataclass
class _Unrelated:
    """A struct that is no subclass of ``_Base``."""

    other: int = 0


_SUB = f"{__name__}._Sub"
_UNRELATED = f"{__name__}._Unrelated"


class TestNamedMemberNamesListsWhatNamedChildTypes:
    """``named_member_names`` lists exactly the members ``named_child`` types, from one reading of the node."""

    def test_a_tag_naming_a_subclass_lists_its_members(self) -> None:
        """The subclass the tag names is what both read."""
        node: MergeDict = {"class": _SUB}
        assert named_child(_Base, "camelCase", node, "class") is int
        assert "camelCase" in named_member_names(_Base, node, "class")

    def test_a_tag_naming_no_subclass_lists_nothing(self) -> None:
        """``named_child`` types nothing by a class the field cannot hold, so nothing is listed by it either."""
        node: MergeDict = {"class": _UNRELATED}
        assert named_child(_Base, "other", node, "class") is Named.NOTHING
        assert named_member_names(_Base, node, "class") == []

    def test_a_typed_call_beside_a_tag_lists_nothing(self) -> None:
        """Under a custom tag, a ``call:`` beside it is a typed call, whose keys are ``call`` and ``args`` alone."""
        node: MergeDict = {"call": "builtins.dict", "kind": _SUB}
        assert named_child(_Base, "camelCase", node, "kind") is Named.REFUSED
        assert named_member_names(_Base, node, "kind") == []
