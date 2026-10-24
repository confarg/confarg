# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A parser, a command or an app holds one confarg target (BUG-273).

``populate_*`` records what it registered (the prefix, the sources) where the merge finds it,
one record per parser, command or app; a second target's record overwrote the first's, so the
first target's merge read the second's prefix and sources. A second target is refused; the
same one populated again replaces its own record.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import click
import cyclopts
import pytest
import typer
from typer.main import get_command

from confarg.cli.argparse import from_namespace, populate_parser
from confarg.cli.click import populate_command as click_populate
from confarg.cli.cyclopts import populate_app
from confarg.cli.typer import populate_command as typer_populate
from confarg.exceptions import ConfargError

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _Server:
    """One section of an application's configuration."""

    port: int = 80


@dataclass
class _Db:
    """Another section, which a second populate_* call would register on the same holder."""

    host: str = "localhost"


def _typer_command() -> Any:
    app = typer.Typer()

    @app.command()
    def run(ctx: typer.Context) -> None: ...

    return get_command(app)


HOLDERS: list[tuple[str, Callable[[], Any], Callable[..., None]]] = [
    ("argparse", argparse.ArgumentParser, populate_parser),
    ("click", lambda: click.command()(lambda **kwargs: None), click_populate),
    ("typer", _typer_command, typer_populate),
    ("cyclopts", cyclopts.App, populate_app),
]


@pytest.mark.parametrize(("make", "populate"), [h[1:] for h in HOLDERS], ids=[h[0] for h in HOLDERS])
def test_a_second_target_is_refused(make: Callable[[], Any], populate: Callable[..., None]) -> None:
    """The holder already records ``_Server``'s flags, so ``_Db`` on it is refused, naming both."""
    holder = make()
    populate(_Server, holder, cli_prefix="server", argv=[])
    with pytest.raises(ConfargError, match=r"_Server.*_Db|_Db.*_Server"):
        populate(_Db, holder, cli_prefix="db", argv=[])


@pytest.mark.parametrize(("make", "populate"), [h[1:] for h in HOLDERS], ids=[h[0] for h in HOLDERS])
def test_the_same_target_populated_again_is_accepted(make: Callable[[], Any], populate: Callable[..., None]) -> None:
    """Registering the same target again replaces its record."""
    holder = make()
    populate(_Server, holder, cli_prefix="server", argv=[])
    populate(_Server, holder, cli_prefix="server", argv=[])


def test_the_first_target_is_never_read_with_the_second_ones_record() -> None:
    """Before the refusal, ``_Server``'s merge read ``_Db``'s prefix and refused ``--db.host`` as its own flag."""
    parser = argparse.ArgumentParser()
    populate_parser(_Server, parser, cli_prefix="server", argv=[])
    with pytest.raises(ConfargError):
        populate_parser(_Db, parser, cli_prefix="db", argv=[])
    ns = parser.parse_args(["--server.port", "8080"])
    assert from_namespace(_Server, ns, argv=["--server.port", "8080"]) == _Server(port=8080)
