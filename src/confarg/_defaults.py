# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Defaults and reserved key names shared by ``confarg.load`` and every CLI adapter.

Always reference these constants instead of repeating the literals, so the four front-ends
cannot drift apart.

Dev Notes:
    docs-dev/architecture/design-decisions/README.md
"""

from __future__ import annotations

import dataclasses
import os
import sys
from typing import TYPE_CHECKING, Any, Final, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

UNION_TAG: Final[str] = "class"
"""Default discriminator field name for union variants.

Dev Notes:
    docs-dev/architecture/design-decisions/union-tag-defaults-to-class.md#union_tag-defaults-to-class
"""

ENV_PREFIX: Final[str | None] = None
"""Default of :attr:`MergeOptions.env_prefix`: environment variables are not read.

Dev Notes:
    docs-dev/architecture/design-decisions/environment-variables-off-by-default.md#environment-variables-off-by-default
"""

ENV_SEPARATOR: Final[str] = "__"
"""Default of :attr:`MergeOptions.env_separator`."""

CONFIG_FLAG: Final[str] = "config"
"""Default name of the config-file CLI flag and env-pointer segment.

``""`` disables config-file handling entirely.
"""

LOCALS_KEYS: Final[tuple[str, str]] = ("locals", "_locals")
"""Names that may address the reserved namespace holding local variables.

Local variables are scratch values that expressions reference as ``${locals.<name>}`` but
that are not fields of the target type; the namespace is stripped before construction.
Either spelling addresses the namespace unless the target has a field of that name, in
which case the other spelling is used; a target owning both names has no namespace.
See ``confarg._parse_cli._locals_keys_at``.

Dev Notes:
    docs-dev/architecture/locals.md
"""

ROOT_KEY: Final[str] = "__root__"
"""Reserved key under which a non-struct target's value is stored in the merged dict.

Every channel writes it and ``build`` reads it, so all four front-ends have to agree on the
spelling.

Dev Notes:
    docs-dev/architecture/config-files/reserved-keys.md#reserved-file-only-keys
"""


class MergeOptions(TypedDict, total=False):
    """The sources :func:`confarg.merge` and :func:`confarg.load` read, and how they read them.

    Every key is optional and passed as a keyword argument::

        confarg.load(MyConfig, env_prefix="MYAPP_", files=["defaults.yaml"])

    The CLI adapters' ``merge_*`` and ``from_*`` functions take the same keywords. To
    forward them from a function of your own, annotate its keywords with this type::

        def run(**opts: Unpack[confarg.MergeOptions]) -> MyConfig:
            return confarg.load(MyConfig, **opts)

    Dev Notes:
        docs-dev/architecture/pipeline/api-seams.md#one-option-set
    """

    argv: Sequence[str] | None
    """CLI arguments to parse. Defaults to ``sys.argv[1:]``.

    A CLI adapter reads its CLI values and ``--config`` files from *argv*, so pass the list
    the framework parsed whenever it was not ``sys.argv[1:]`` (in tests, typically); a parse
    result holding a confarg flag that *argv* does not spell raises
    :class:`~confarg.exceptions.ConfargError`.
    """

    env: Mapping[str, str] | None
    """Environment variable mapping to scan. Defaults to :data:`os.environ`."""

    env_prefix: str | None
    """Prefix that environment variables must start with to be read.

    Defaults to ``None``, which disables environment variable parsing entirely. Set to
    ``""`` to read every variable, or to e.g. ``"MYAPP_"`` to read only the variables with
    that prefix.
    """

    env_separator: str
    """Separator splitting environment variable names into nested keys.

    Defaults to ``"__"``: ``MYAPP_DB__MAX_CONNECTIONS`` sets ``db.max_connections``.
    """

    cli_prefix: str | None
    """Namespace that all CLI flags live under, addressed as ``--<prefix>.<field>``.

    With one set, a flag that lacks it is rejected. It is also the only way to address a
    non-struct (scalar) target from the CLI, as ``--<prefix> VALUE``.

    Defaults to the prefix the flags were registered under: none for :func:`confarg.merge`
    and :func:`confarg.load`, and the one passed to ``populate_*`` for a CLI adapter, which
    is where an adapter applies it. Passing an adapter a prefix that disagrees with the
    registered one raises :class:`~confarg.exceptions.ConfargError` rather than silently
    matching no flags.
    """

    config_flag: str
    """Name of the CLI flag that loads config files, ``--config path/to/file.yaml``.

    It also names the environment variable that does, ``<env_prefix>CONFIG=path/to/file.yaml``.
    Defaults to ``"config"``; ``""`` disables both. A CLI adapter must be given the
    ``config_flag`` passed to ``populate_*``.
    """

    files: Sequence[str | Path]
    """Config files to load first, at the lowest priority, in the order given."""

    env_config: str | None
    """Name of an environment variable whose value is a config file path to load.

    The file is loaded after ``files`` but before CLI ``--config`` files.
    """

    union_tag: str
    """Field name used as a discriminator tag in union types. Defaults to ``"class"``."""


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class _Options:
    """:class:`MergeOptions` with every default applied: what the merge pipeline reads.

    Built by :func:`_resolve_options` alone, so each default has this one home.
    """

    argv: Sequence[str]
    env: Mapping[str, str]
    env_prefix: str | None = ENV_PREFIX
    env_separator: str = ENV_SEPARATOR
    cli_prefix: str | None = None
    config_flag: str = CONFIG_FLAG
    files: Sequence[str | Path] = ()
    env_config: str | None = None
    union_tag: str = UNION_TAG


def _resolve_options(caller: str, opts: Mapping[str, Any]) -> _Options:
    """Return the *opts* a public function *caller* received, with every default applied.

    ``argv`` and ``env`` are read from :mod:`sys` and :mod:`os` here, at call time. A key
    :class:`MergeOptions` does not declare raises the :class:`TypeError` Python raises for
    an unexpected keyword argument, since a ``**opts`` signature no longer does.

    Dev Notes:
        docs-dev/architecture/pipeline/api-seams.md#one-option-set
    """
    for key in opts:
        if key not in MergeOptions.__optional_keys__:
            msg = f"{caller}() got an unexpected keyword argument {key!r}"
            raise TypeError(msg)
    argv = opts.get("argv")
    env = opts.get("env")
    given: dict[str, Any] = {
        **opts,
        "argv": sys.argv[1:] if argv is None else list(argv),
        "env": os.environ if env is None else env,
    }
    return _Options(**given)
