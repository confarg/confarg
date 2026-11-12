"""The ``populate_*`` functions take the ``MergeOptions`` set, so ``cli_prefix`` defaults to ``None`` (REF-9).

What registration reads its sources by is the merge's too, so ``populate_*`` spells them as
``merge_*`` does.

Dev Notes:
    docs-dev/architecture/pipeline/api-seams.md#one-option-set
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import TYPE_CHECKING

import pytest

from confarg._defaults import _Options, _resolve_options
from confarg.cli._build import build_dynamic_flags, build_static_flags, registered_flags, widen_static
from confarg.cli.argparse import populate_parser
from confarg.cli.click import populate_command as click_populate_command
from confarg.cli.cyclopts import populate_app
from confarg.cli.typer import populate_command as typer_populate_command

if TYPE_CHECKING:
    from collections.abc import Callable

POPULATE = [populate_parser, click_populate_command, populate_app, typer_populate_command]


@pytest.mark.parametrize("populate", POPULATE, ids=lambda f: f.__module__)
def test_takes_merge_options(populate: Callable[..., object]) -> None:
    """Beside ``config_subkeys``, its keywords are ``MergeOptions``', whose ``cli_prefix`` defaults to ``None``."""
    params = inspect.signature(populate).parameters.values()
    named = (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD)
    keywords = [(p.name, p.kind) for p in params if p.kind in named]
    assert keywords == [("config_subkeys", inspect.Parameter.KEYWORD_ONLY), ("opts", inspect.Parameter.VAR_KEYWORD)]
    defaults = {f.name: f.default for f in dataclasses.fields(_Options)}
    assert defaults["cli_prefix"] is None


@dataclasses.dataclass
class _Tagged:
    """A list field, whose element flag argv spells."""

    tags: list[int] = dataclasses.field(default_factory=list)
    """The tags."""


def test_registered_flags_is_the_static_then_the_dynamic_specs() -> None:
    """The one walk every adapter loads: static flags first, then argv's, widened as ``widen_static`` says (REF-50)."""
    argv = ["--tags.0", "1", "--tags+", "2"]
    options = _resolve_options("populate_parser", {"argv": argv})
    static = build_static_flags(_Tagged, argv=argv, cli_prefix="", config_flag=options.config_flag, below={})
    dynamic = build_dynamic_flags(_Tagged, argv, cli_prefix="", config_flag=options.config_flag, below={})
    widened, rest = widen_static(static, dynamic)
    flags = registered_flags(_Tagged, options, {})
    assert flags == widened + rest
    assert [spec.name for spec in flags][: len(static)] == [spec.name for spec in static]
    assert {"tags.0", "tags+"} <= {spec.name for spec in flags}
