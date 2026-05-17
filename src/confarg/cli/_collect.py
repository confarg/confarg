# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The adapters' shared merge tail: the CLI channel written from argv by vanilla's own loop.

Backend-neutral: every CLI adapter (argparse, click, typer, cyclopts) lets its framework
parse argv -- validation, ``--help``, completion -- then hands the parse result and the
argv here.  The CLI channel is written by :func:`~confarg._parse_cli._parse_cli` over that
argv, the loop vanilla runs, so the merged dict equals vanilla's by construction: values,
patches, tags and key order alike.  The parse result is only checked against the argv.

Dev Notes:
    docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from confarg._defaults import _Options
    from confarg._merge import MergeDict

from confarg._api import _build_for_cli
from confarg._parse_cli import _config_pairs_in, _parse_cli, _path_unknown
from confarg._pipeline import _merge_sources
from confarg.cli._argv import spelled_flag_names
from confarg.cli._build import _binds_a_run
from confarg.cli._prefix import strip_argv_prefix, strip_flat_prefix
from confarg.exceptions import ConfargError


def _require_argv_spells(
    flat: Mapping[str, Any],
    argv: Sequence[str],
    cli_prefix: str,
    target: object,
    union_tag: str,
) -> None:
    """Raise unless *argv* spells every confarg flag the framework's parse result holds.

    The CLI channel is written from *argv* alone, so a parse result that holds a flag
    *argv* never spells means the two are not the same command line -- typically
    ``parse_args(custom)`` merged with *argv* left to default to ``sys.argv[1:]``.  The
    values would be lost without a word, so the mismatch is refused instead.  A key the
    target does not resolve is the host's own parameter and is not confarg's to judge.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
    """
    spelled = spelled_flag_names(strip_argv_prefix(argv, cli_prefix))
    for key, value in strip_flat_prefix(dict(flat), cli_prefix).items():
        if value is None or key in spelled or _path_unknown(target, key.split("."), union_tag):
            continue
        msg = (
            f"The parse result holds '--{key}', which argv does not spell: pass argv= the "
            "list the framework parsed (it defaults to sys.argv[1:])"
        )
        raise ConfargError(msg)


def _merge_from_flat(  # noqa: PLR0913  # the parse result, then how the framework bound it
    flat: dict[str, Any],
    target: object,
    options: _Options,
    *,
    cli_prefix: str,
    binds_runs: bool,
    runs: frozenset[str] | None = None,
) -> MergeDict:
    """Merge every source into a raw dict, the CLI channel written from ``options.argv``.

    The shared tail of ``merge_namespace`` / ``merge_context`` / ``merge_app``, so the
    four cannot drift.  The CLI channel and its ``--config`` files are what vanilla's
    loop (:func:`~confarg._parse_cli._parse_cli`) reads off the argv, in the mode that
    leaves the host's own tokens to the host; the framework's parse result *flat* only
    has to agree with that argv (:func:`_require_argv_spells`).

    Args:
        flat: The adapter's parse result as ``{dotted.flag: value}``.
        target: The target type, used to guide the type walk.
        options: The caller's resolved options; ``argv`` is the list the framework parsed.
        cli_prefix: Namespace the flags were registered under, reconciled with
            ``options.cli_prefix`` by :func:`~confarg.cli._prefix.resolve_prefix`.
        binds_runs: The framework binds every token up to the next flag to a
            multi-token or fixed-arity flag (argparse, cyclopts), so a token after
            the run vanilla consumes is a stray rather than a positional of the host's.
        runs: The flags registration registered to bind such a run
            (:func:`~confarg.cli._build.bound_runs`), which the framework bound one to
            whatever vanilla's loop types the flag as; ``None`` when confarg did not
            register them, the type vanilla consumes for then answering.

    Returns:
        A plain dict of the merged configuration, with expression strings intact. A list
        operation that only ``build()`` can apply stays in it, keyed by a
        :class:`confarg.ListOp`.

    Raises:
        ConfargError: If *flat* holds a confarg flag the argv does not spell.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
    """
    _require_argv_spells(flat, options.argv, cli_prefix, target, options.union_tag)

    def parse_cli(below: MergeDict) -> MergeDict:
        return _parse_cli(
            options.argv,
            target,
            cli_prefix,
            options.config_flag,
            options.union_tag,
            host_parsed=True,
            host_binds_run=_host_binds_run(runs) if binds_runs else None,
            below=below,
        )[0]

    configs = _config_pairs_in(options.argv, target, cli_prefix, options.config_flag, options.union_tag)
    return _merge_sources(target, parse_cli, configs, options)


def _host_binds_run(runs: frozenset[str] | None) -> Callable[[list[str], Any], bool]:
    """Return whether the framework bound the token after a flag's run to it: registered so, or typed so."""
    if runs is None:
        return lambda _path, ft: _binds_a_run(ft)
    return lambda path, ft: ".".join(path) in runs or _binds_a_run(ft)


def _construct_from_merged(target: object, merged: MergeDict, union_tag: str, cli_prefix: str) -> Any:
    """Construct *target* from an already-merged dict; the shared tail of every ``from_*``.

    *cli_prefix* is the one the merge resolved, which a missing field's remedy is spelled under.
    """
    return _build_for_cli(target, merged, union_tag, cli_prefix)
