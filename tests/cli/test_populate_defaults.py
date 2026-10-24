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

from confarg._defaults import _Options
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
