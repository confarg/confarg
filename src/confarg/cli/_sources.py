# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What registration read, recorded where the merge finds it again.

An adapter registers its flags before the framework parses argv, and types each one by the
layers below argv (:func:`confarg._pipeline.below_argv`): the framework splits argv by those
types, so the merge must read the very same sources. ``populate_*`` records the options it
read them by, and the flags it registered to bind a run of tokens; ``merge_*`` / ``from_*``
reuse the options it is not given, and refuse one that differs (:func:`reconcile`), as
:func:`~confarg.cli._prefix.resolve_prefix` does for ``cli_prefix``.

Dev Notes:
    docs-dev/architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters
"""

from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from confarg._merge import MergeDict

from confarg._defaults import _Options, _resolve_options
from confarg._parse_cli import _config_pairs_in
from confarg._pipeline import below_argv
from confarg.exceptions import ConfargError

#: The attribute the registration is recorded under: on an argparse Namespace, a click or
#: typer option, a cyclopts app's metadata.
REGISTRATION_ATTR = "__confarg_registration__"

#: The options naming the sources registration reads and how it reads them: every one but
#: ``argv``, which each step is given, and ``cli_prefix``, which ``resolve_prefix`` keeps.
RECORDED_OPTIONS = ("files", "env", "env_prefix", "env_separator", "env_config", "config_flag", "union_tag")


@dataclasses.dataclass(frozen=True)
class Registration:
    """What ``populate_*`` read and registered, recorded on the parser, the command or the app."""

    #: The value of each of :data:`RECORDED_OPTIONS` registration read the sources by; ``env``
    #: is ``None`` when it read ``os.environ``, which the merge reads again.
    sources: Mapping[str, Any]
    #: The flags registered to bind every token up to the next flag, by their dotted names.
    runs: frozenset[str] = frozenset()


def registration_inputs(
    target: Any,
    caller: str,
    given: Mapping[str, Any],
) -> tuple[_Options, MergeDict, dict[str, Any]]:
    """Return what ``populate_*`` registers by: its options resolved, what lies below argv, and the sources to record.

    Raises:
        TypeError: If *given* holds a keyword :class:`~confarg.MergeOptions` does not declare.
    """
    options = _resolve_options(caller, given)
    prefix = options.cli_prefix or ""
    try:
        configs = _config_pairs_in(options.argv, target, prefix, options.config_flag, options.union_tag)
    except ConfargError:
        configs = []  # the merge raises it, naming the flag
    sources = {key: getattr(options, key) for key in RECORDED_OPTIONS}
    if given.get("env") is None:
        sources["env"] = None
    return options, below_argv(target, configs, options), sources


def reconcile(registration: Registration | None, given: Mapping[str, Any], caller: str) -> dict[str, Any]:
    """Return the options the merge reads: those registration read, with *given* beside them.

    An option *given* that registration read differently -- a default it read included --
    raises: the framework split argv by the types the sources registration read gave its
    flags, so the merge must read the same ones. An option registration read nothing by
    differs from nothing: the environment and its separator where registration read no
    variable. A merge of a parse result confarg did not register reads *given* alone.

    Raises:
        ConfargError: If *given* holds a recorded option whose value differs from the one
            registration read.
    """
    if registration is None:
        return dict(given)
    sources = registration.sources
    unread = set()
    if sources["env_prefix"] is None:
        unread.add("env_separator")
        if not sources["env_config"]:
            unread.add("env")
    for key in RECORDED_OPTIONS:
        if key in given and key not in unread and not _same(key, given[key], sources[key]):
            msg = (
                f"{key} mismatch: the flags were registered with {key}={registration.sources[key]!r},"
                f" but {given[key]!r} was passed to {caller}(). The framework split the command line"
                f" by the sources registration read: pass {key} to populate_*() (or make_parser()),"
                f" and omit it here to reuse it."
            )
            raise ConfargError(msg)
    recorded = {key: value for key, value in registration.sources.items() if not (key == "env" and value is None)}
    return {**recorded, **given}


def _same(key: str, given: Any, recorded: Any) -> bool:
    """Return whether the option *key* given as *given* names the sources registration read as *recorded*."""
    if key == "files":
        return [os.fspath(f) for f in given or ()] == [os.fspath(f) for f in recorded or ()]
    if key == "env":
        given_env = os.environ if given is None else given
        recorded_env = os.environ if recorded is None else recorded
        return given_env is recorded_env or dict(given_env) == dict(recorded_env)
    return given == recorded
