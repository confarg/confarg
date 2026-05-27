# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""cyclopts-specific flag loading: load_flags_into_app and populate_app."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Annotated, Any, Literal

from cyclopts import Group
from cyclopts import Parameter as CycloptsParam

if TYPE_CHECKING:
    from collections.abc import Sequence

    import cyclopts

    from confarg.cli.argparse._spec import FlagSpec

from confarg import _defaults
from confarg.cli.argparse._build import build_dynamic_flags, build_static_flags

# Maps id(app) to confarg metadata {command, name_map}.
# Keyed by id rather than the App object because App is unhashable (attrs frozen).
# Values hold a reference to the app itself to prevent id reuse after GC.
_app_meta: dict[int, dict[str, Any]] = {}


def _make_literal(choices: list[str]) -> Any:
    """Build Literal[c1, c2, ...] at runtime from a list of strings.

    ``Literal[tuple(choices)]`` is equivalent to ``Literal[c1, c2, ...]`` because
    Python's multi-item subscript syntax also passes a tuple to ``__getitem__``.
    """
    return Literal[tuple(choices)]  # ty: ignore[invalid-type-form]  # dynamic Literal construction at runtime; equivalent to Literal[c1, c2, ...]


def _spec_to_inspect_param(spec: FlagSpec) -> inspect.Parameter:
    """Convert one FlagSpec to a keyword-only inspect.Parameter."""
    py_name = spec.name.replace(".", "__")

    # Determine the Python type annotation (confarg handles actual coercion)
    if spec.choices:
        inner: Any = _make_literal(spec.choices)
    elif spec.nargs == "*" or isinstance(spec.nargs, int):
        inner = list[str]
    else:
        inner = str

    annotation_type = inner | None

    # Build cyclopts Parameter kwargs
    param_kwargs: dict[str, Any] = {
        "name": f"--{spec.name}",
        "required": False,
        "show_default": False,
        # Suppress --no-* (bool) and --empty-* (iterable) negative flags.
        # All our fields are Optional[str/list]; confarg handles coercion.
        "negative": (),
    }
    # Cyclopts has no `metavar` parameter; prefix the type name into help text
    # so users can see the expected type (e.g. "(INT) (default: 8080)").
    help_parts: list[str] = []
    if spec.metavar and not spec.choices:
        help_parts.append(f"({spec.metavar})")
    if spec.help:
        help_parts.append(spec.help)
    if help_parts:
        param_kwargs["help"] = " ".join(help_parts)
    if spec.nargs == "*":
        param_kwargs["consume_multiple"] = True
    elif isinstance(spec.nargs, int):
        param_kwargs["n_tokens"] = spec.nargs
    if spec.group:
        param_kwargs["group"] = Group(
            name=spec.group,
            help=spec.group_description,
        )

    cyclopts_param = CycloptsParam(**param_kwargs)
    annotated = Annotated[annotation_type, cyclopts_param]

    return inspect.Parameter(
        name=py_name,
        kind=inspect.Parameter.KEYWORD_ONLY,
        default=None,
        annotation=annotated,
    )


def load_flags_into_app(
    flags: list[FlagSpec],
    app: cyclopts.App,
) -> None:
    """Register a list of :class:`~confarg.cli.argparse.FlagSpec` objects on a cyclopts :class:`~cyclopts.App`.

    Because cyclopts is signature-driven, this generates a synthetic default
    function whose :class:`inspect.Signature` encodes all flags and registers it
    via ``app.default()``.  The app receives two private attributes so that
    :func:`from_app` can extract parsed values:

    - ``_confarg_command`` — reference to the synthetic function itself
    - ``_confarg_name_map`` — ``{py_identifier: dotted_cli_name}`` mapping

    Args:
        flags: The specs to register, typically from
            :func:`~confarg.cli.argparse.build_static_flags`.
        app: The cyclopts :class:`~cyclopts.App` to populate.
    """
    params: list[inspect.Parameter] = []
    name_map: dict[str, str] = {}

    for spec in flags:
        param = _spec_to_inspect_param(spec)
        params.append(param)
        name_map[param.name] = spec.name

    def __confarg_command__(**kwargs: Any) -> dict[str, Any]:
        return {k: v for k, v in kwargs.items() if v is not None}

    __confarg_command__.__signature__ = inspect.Signature(  # ty: ignore[unresolved-attribute]  # __signature__ is a valid dunder for inspect
        params,
        return_annotation=dict,
    )

    app.default(__confarg_command__)
    # Store metadata keyed by id(app); include a reference to app to prevent
    # id reuse if a different App is allocated at the same address after GC.
    _app_meta[id(app)] = {"app_ref": app, "command": __confarg_command__, "name_map": name_map}


def populate_app(  # noqa: PLR0913  # mirrors populate_parser/populate_command signatures; all params are keyword-only with sensible defaults
    dc_type: type,
    app: cyclopts.App,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    config_subkeys: bool = True,
    argv: Sequence[str] | None = None,
) -> None:
    """Register fields of a dataclass type as options on a cyclopts :class:`~cyclopts.App`.

    Generates a synthetic default function whose signature encodes all
    dataclass fields — including a ``--<config_flag>`` option for config files —
    and registers it via :func:`load_flags_into_app`.

    Use :func:`from_app` after parsing to obtain the fully merged dataclass
    instance.

    Args:
        dc_type: The dataclass type whose fields to register.
        app: The cyclopts :class:`~cyclopts.App` to populate.
        union_tag: Name of the union discriminator field to skip.
        config_flag: Name of the config-file option (default ``"config"``).
            Set to ``""`` to disable config-file option registration.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` options
            for each direct struct field of the root dataclass (default
            ``True``).
        argv: CLI argument list used to pre-resolve ``--<field>.fn`` /
            ``--<field>.class`` values so that callable ``--<field>.bind.*``
            options can be registered before parsing.
    """
    flags = build_static_flags(
        dc_type,
        union_tag=union_tag,
        config_flag=config_flag,
        config_subkeys=config_subkeys,
    )
    if argv is not None:
        flags = flags + build_dynamic_flags(dc_type, argv, union_tag=union_tag, config_flag=config_flag)
    load_flags_into_app(flags, app)
