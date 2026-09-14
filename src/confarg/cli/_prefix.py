# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Apply and strip ``cli_prefix`` at the two adapter boundaries.

The prefix is a naming convention, not a parsing mode: it is added to every
``FlagSpec.name`` when flags are registered and removed again from the flat parse
result and from argv when they are read back.  Everything between those two
boundaries -- the type walk, the patch scan, the config-file scan -- never sees it.

Unlike vanilla's :func:`~confarg._parse_cli._strip_cli_prefix`, the strippers here
are **lenient**: a flag outside the prefix belongs to the host framework, not to a
user typo, so it is skipped rather than reported as unknown.

Dev Notes:
    docs-dev/architecture/03-cli-parsing.md#cli_prefix
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg.cli._spec import FlagSpec

from confarg.exceptions import ConfargError

#: Name under which ``populate_*`` records the prefix it registered with, so
#: ``merge_*`` can recover it instead of making the caller repeat it.
#:
#: It is stored on whatever survives into the merge step, which differs per
#: framework: argparse gets no reference to the parser, so it rides on the
#: Namespace (via ``set_defaults``); click commands get their ``params`` copied
#: onto other commands, so it rides on the options themselves; cyclopts hands the
#: App straight back, so it lives in that adapter's own ``_app_meta`` entry.
#: Set only when a prefix is in use, keeping the default case unchanged.
PREFIX_ATTR = "__confarg_cli_prefix__"


def resolve_prefix(registered: str | None, given: str | None) -> str:
    """Reconcile the prefix recorded at registration with the one passed to ``merge_*``.

    *given* of ``None`` means "not passed": the recorded prefix is reused, which is
    what makes repeating it at merge time optional.  Passing one that disagrees with
    what was registered is an error rather than a silent mismatch -- the flags would
    simply never be found, and the fields would come back missing.

    Args:
        registered: The prefix recorded by ``populate_*``, or ``None`` if none was.
        given: The prefix passed to ``merge_*`` / ``from_*``, or ``None`` if omitted.

    Returns:
        The prefix to strip with; ``""`` when there is none.

    Raises:
        ConfargError: If *given* and *registered* are both set and differ.
    """
    if given is None:
        return registered or ""
    if registered is not None and registered != given:
        msg = (
            f"cli_prefix mismatch: flags were registered with cli_prefix={registered!r},"
            f" but {given!r} was passed here. Pass the same value to populate_*() and to"
            f" merge_*()/from_*(), or omit it here to reuse the registered one."
        )
        raise ConfargError(msg)
    return given


def apply_prefix(specs: list[FlagSpec], cli_prefix: str) -> list[FlagSpec]:
    """Return *specs* renamed into the *cli_prefix* namespace.

    A spec with an empty name is the scalar root (``--<prefix> VALUE``): it becomes
    the bare prefix flag.  Without a prefix it has no spelling at all, so it is
    dropped -- vanilla has none either
    (:func:`~confarg._parse_cli._handle_scalar_root` is reached only through the
    bare ``--<prefix>`` token).
    """
    if not cli_prefix:
        return [spec for spec in specs if spec.name]
    return [dataclasses.replace(spec, name=f"{cli_prefix}.{spec.name}" if spec.name else cli_prefix) for spec in specs]


def strip_flat_prefix(flat: dict[str, Any], cli_prefix: str) -> dict[str, Any]:
    """Return *flat* with *cli_prefix* removed from its keys, dropping foreign entries.

    The bare prefix key becomes ``""``, the empty path that
    :func:`~confarg.cli._collect._collect_ns_fields` reads as the scalar root.  Keys
    outside the namespace are the host framework's own parameters and are dropped.
    """
    if not cli_prefix:
        return {k: v for k, v in flat.items() if k != PREFIX_ATTR}
    dot_pfx = f"{cli_prefix}."
    stripped: dict[str, Any] = {}
    for key, value in flat.items():
        if key == cli_prefix:
            stripped[""] = value
        elif key.startswith(dot_pfx):
            stripped[key[len(dot_pfx) :]] = value
    return stripped


def strip_argv_prefix(argv: Sequence[str], cli_prefix: str) -> list[str]:
    """Return *argv* with *cli_prefix* removed from its flags, dropping foreign tokens.

    ``--k=v`` is normalized first, so both spellings strip alike.  A flag outside the
    namespace is dropped **together with its value tokens**, which keeps the
    left-to-right order of what remains -- the whole reason the patch scan and the
    config-file scan read argv rather than the framework's parse result.

    The bare ``--<prefix>`` is dropped too: a scalar root carries no patch and no
    config file, and the flat collector already owns it (as it does in vanilla's
    ``patch_only`` mode).
    """
    # Imported here: a module-level import would create a load-time import cycle.
    from confarg._parse_cli import _looks_like_flag, _normalize_eq_args, _skip_flag_values  # noqa: PLC0415

    if not cli_prefix:
        return list(argv)
    args = _normalize_eq_args(list(argv))
    dot_pfx = f"{cli_prefix}."
    out: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if not _looks_like_flag(token) or not token[2:].startswith(dot_pfx):
            i = _skip_flag_values(args, i) if _looks_like_flag(token) else i + 1
            continue
        out.append(f"--{token[2 + len(dot_pfx) :]}")
        i += 1
        while i < len(args) and not _looks_like_flag(args[i]):
            out.append(args[i])
            i += 1
    return out
