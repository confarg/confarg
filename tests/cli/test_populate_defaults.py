"""The ``populate_*`` functions default ``cli_prefix`` to ``None``, as ``MergeOptions`` does (REF-9).

Dev Notes:
    docs-dev/architecture/pipeline/api-seams.md#one-option-set
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from confarg.cli.argparse import populate_parser
from confarg.cli.click import populate_command as click_populate_command
from confarg.cli.cyclopts import populate_app
from confarg.cli.typer import populate_command as typer_populate_command

if TYPE_CHECKING:
    from collections.abc import Callable

POPULATE = [populate_parser, click_populate_command, populate_app, typer_populate_command]


@pytest.mark.parametrize("populate", POPULATE, ids=lambda f: f.__module__)
def test_cli_prefix_defaults_to_none(populate: Callable[..., object]) -> None:
    """The default is ``None``, not ``""``, so ``MergeOptions`` and ``populate_*`` agree."""
    assert inspect.signature(populate).parameters["cli_prefix"].default is None
