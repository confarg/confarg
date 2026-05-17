# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the machinery the click and typer adapters share.

Behavior that reaches a user through either adapter belongs in
``tests/cli/test_backend_contract.py``; this file covers only the shared helpers
that neither framework's public surface exposes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from confarg.cli._clicklike import partial_argv_from_env


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
