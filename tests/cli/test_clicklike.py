# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the machinery the click and typer adapters share.

Behavior that reaches a user through either adapter belongs in
``tests/cli/test_backend_contract.py``; this file covers only the shared helpers
that neither framework's public surface exposes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from confarg.cli._clicklike import command_prefix, partial_argv_from_env, registered_prefix
from confarg.cli._prefix import PREFIX_ATTR
from confarg.cli._spec import FlagSpec


class TestPartialArgvFromEnv:
    """The COMP_WORDS/COMP_CWORD reader both adapters complete from."""

    def test_empty_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return [] when COMP_WORDS/COMP_CWORD are absent."""
        monkeypatch.delenv("COMP_WORDS", raising=False)
        monkeypatch.delenv("COMP_CWORD", raising=False)
        assert partial_argv_from_env() == []

    def test_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Strip the program name and the word currently being completed."""
        monkeypatch.setenv("COMP_WORDS", "cli --host myhost --")
        monkeypatch.setenv("COMP_CWORD", "3")
        assert partial_argv_from_env() == ["--host", "myhost"]

    def test_unparsable_cword_degrades_to_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A COMP_CWORD that is not an integer yields [] rather than raising."""
        monkeypatch.setenv("COMP_WORDS", "cli --host")
        monkeypatch.setenv("COMP_CWORD", "notanint")
        assert partial_argv_from_env() == []


class TestCommandPrefix:
    """The prefix recorded on a command's options, which registration and completion both read (REF-50)."""

    def test_none_without_a_recorded_prefix(self) -> None:
        """A command none of whose options carries a prefix has none."""
        command = SimpleNamespace(params=[SimpleNamespace(), SimpleNamespace()])
        assert command_prefix(command) is None

    def test_first_recorded_prefix_wins(self) -> None:
        """The first option carrying a prefix gives it; a context reads its command's."""
        command = SimpleNamespace(params=[SimpleNamespace(), SimpleNamespace(**{PREFIX_ATTR: "app"})])
        assert command_prefix(command) == "app"
        assert registered_prefix(SimpleNamespace(command=command)) == "app"


class TestFlagShape:
    """The two shape classifications every adapter reads off a :class:`FlagSpec` (REF-50)."""

    @pytest.mark.parametrize(
        ("nargs", "value_less", "takes_a_run"),
        [(None, False, False), (0, True, False), ("*", False, True), (2, False, False)],
    )
    def test_classification(self, nargs: int | str | None, *, value_less: bool, takes_a_run: bool) -> None:
        """A spec is value-less at ``nargs == 0`` and takes a run at ``"*"``, and nothing else is either."""
        spec = FlagSpec(name="x", nargs=nargs)
        assert (spec.value_less, spec.takes_a_run) == (value_less, takes_a_run)
