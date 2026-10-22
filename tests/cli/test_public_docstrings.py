# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Every public function of the adapters documents only the parameters it takes.

A reader follows the ``Args:`` section of the rendered reference; an entry the signature does
not take is a ``TypeError`` for them (BUG-263).
"""

from __future__ import annotations

import inspect
import re
from typing import Any

import pytest

import confarg.cli.argparse
import confarg.cli.click
import confarg.cli.cyclopts
import confarg.cli.typer

_ADAPTERS = (confarg.cli.argparse, confarg.cli.click, confarg.cli.cyclopts, confarg.cli.typer)
_FUNCTIONS = [
    getattr(module, name)
    for module in _ADAPTERS
    for name in module.__all__
    if inspect.isfunction(getattr(module, name))
]

#: An entry of a Google-style ``Args:`` section: its indentation, then the name.
_ARG_ENTRY = re.compile(r"^        (\*{0,2}\w+):", re.MULTILINE)


def _documented(fn: Any) -> list[str]:
    """Return the parameter names *fn*'s ``Args:`` section documents, stars kept."""
    doc = inspect.getdoc(fn) or ""
    section = re.search(r"^Args:\n(.*?)(?=^\S|\Z)", doc, re.MULTILINE | re.DOTALL)
    return [] if section is None else re.findall(r"^    (\*{0,2}\w+):", section.group(1), re.MULTILINE)


def _taken(fn: Any) -> set[str]:
    """Return the parameter names *fn* takes, a variadic one with its stars."""
    stars = {inspect.Parameter.VAR_POSITIONAL: "*", inspect.Parameter.VAR_KEYWORD: "**"}
    return {stars.get(p.kind, "") + p.name for p in inspect.signature(fn).parameters.values()}


@pytest.mark.parametrize("fn", _FUNCTIONS, ids=lambda fn: f"{fn.__module__}.{fn.__name__}")
def test_documents_only_what_it_takes(fn: Any) -> None:
    """No ``Args:`` entry names a parameter the signature lacks."""
    assert set(_documented(fn)) <= _taken(fn)
