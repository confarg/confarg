# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build lists of FlagSpec from dataclass type information, for every CLI adapter.

Must not import argparse (it is shared by all adapters) and imports ``_parse_cli``
inside functions only.

Dev Notes:
    docs-dev/architecture/cli-adapters/flag-model.md#framework-neutral-flag-model
    docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import json
import operator
import re
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

from confarg import _defaults
from confarg._callable import (
    _OPENERS,
    _fillable_params,
    _instance_method_owner,
    _target_signature,
    spec_opener,
)
from confarg._cast import SCALAR_CAST_TYPES
from confarg._import import _import_dotted, dotted_name
from confarg._merge import (
    MergeDict,
    _peek_nested,
    _set_nested,
)
from confarg._tags import _partial_config_from_argv, import_tagged_classes
from confarg._types import (
    _base_declares_path,
    _elem_type,
    _fixed_seq_types,
    _init_defaults,
    _init_fields,
    _is_bool,
    _is_callable,
    _is_dict,
    _is_enum,
    _is_literal,
    _is_namedtuple,
    _is_struct,
    _is_struct_like,
    _is_tuple,
    _is_type_ref,
    _is_union,
    _is_varlen_collection,
    _literal_values,
    _namedtuple_defaults,
    _namedtuple_fields,
    _resolve_struct,
    _resolve_type,
    _struct_defaults,
    _struct_fields,
    _struct_subclasses,
    _tuple_types,
    _union_args_no_none,
    _union_has_seq_variant,
    _union_tag_shadowed,
    _unwrap_optional,
    _var_params,
)
from confarg.cli._prefix import apply_prefix, in_prefix, strip_argv_prefix
from confarg.cli._spec import FlagSpec, HelpParts, _build_help, _get_field_docstrings, _get_field_meta, _struct_doc
from confarg.exceptions import ConfargWarning, SymbolImportError
from confarg.typedload._coerce import _NONE_TOKENS, _enum_choices, _is_registered_leaf
from confarg.typedload._construct import _is_typed_call


def _scalar_cast_types_in_union(resolved: Any) -> list[type]:
    """Return the scalar cast types the union holds, to offer as explicit cast flags.

    A cast is admitted only where the field's type holds it, so a multi-variant
    union offers exactly its own scalar variants: the flags disambiguate the
    stealing among them, and registration and vanilla's parse agree because both
    ask the one admission rule (BUG-94).

    Dev Notes:
        docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags
        docs-dev/architecture/design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds
    """
    return [t for t in (_resolve_type(v) for v in _union_args_no_none(resolved)) if t in SCALAR_CAST_TYPES.values()]


def _literal_cli_choices(vals: tuple[Any, ...]) -> list[str]:
    """Map Literal members to their accepted CLI strings."""
    choices: list[str] = []
    for v in vals:
        if v is None:
            choices.extend(sorted(_NONE_TOKENS))
        else:
            choices.append(str(v))
    return choices


def _merge_or_append_spec(result: list[FlagSpec], by_name: dict[str, FlagSpec], spec: FlagSpec) -> None:
    """Append ``spec`` to ``result``, or merge its ``choices`` into a same-named earlier spec.

    Union variants can each contribute a ``FlagSpec`` for the same field (e.g.
    ``type: Literal["mariadb"]`` vs ``Literal["postgres"]``). When both the existing and
    new spec carry ``choices``, union them (order-preserving); otherwise keep the first
    spec unchanged.
    """
    existing = by_name.get(spec.name)
    if existing is None:
        result.append(spec)
        by_name[spec.name] = spec
        return
    if existing.choices is not None and spec.choices is not None:
        existing.choices.extend(c for c in spec.choices if c not in existing.choices)


def _takes_multi_tokens(tp: Any) -> bool:
    """Return whether a flag for a field of type *tp* consumes tokens until the next flag.

    The two families vanilla's :func:`~confarg._parse_cli._consume_collection_or_scalar`
    consumes greedily for, and the two it is therefore content with no token at all in: a
    varlen collection, and a union with a sequence variant.  Asked of a *resolved* type, so
    ``list[str] | None`` answers through its union.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """
    return _is_varlen_collection(tp) or _union_has_seq_variant(tp)


def _refusing_bare(spec: FlagSpec, tp: Any) -> FlagSpec:
    """Return *spec* refusing its bare occurrence when *tp* has a fixed arity, as vanilla spells it.

    The one ``_fixed_seq_types`` gate behind :attr:`FlagSpec.refuses_bare`, asked of the
    type *as resolved* (``None`` when the walk resolved none), which also sets the
    :attr:`FlagSpec.usage` vanilla's loop spells for that type (BUG-171).

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    from confarg._parse_cli import _fixed_arity_usage  # noqa: PLC0415  # import cycle

    if tp is None or _fixed_seq_types(tp) is None:
        return spec
    return dataclasses.replace(spec, refuses_bare=True, usage=_fixed_arity_usage(tp))


def _binds_a_run(tp: Any) -> bool:
    """Return whether a framework that varies a flag's token count binds a run to *tp*'s flag.

    Argparse and cyclopts register a multi-token flag (:func:`_takes_multi_tokens`) and a
    fixed-arity one (``FlagSpec.whole_value``, which needs a variable token count) greedily,
    so every token up to the next flag is the flag's; click and typer bind the exact count.
    Vanilla's loop asks it of the type it consumed for, to tell a stray it refuses from a
    positional of the host's own, and a subkey or element flag registers greedily exactly
    where it holds, so the two cannot disagree (BUG-179).

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#the-quartet
    """
    return _takes_multi_tokens(tp) or _fixed_seq_types(tp) is not None


def _scalar_cast_parent_is_leaf(parent: Any) -> bool:
    """Return whether a scalar force-cast lands on a plain leaf field (BUG-72).

    The registration half of the plain-field cast contract: a cast is admitted
    only where the field's type holds it, and a plain leaf holds exactly its own
    type, so the leaf's cast flag is the field's to take.  The parents that
    answer False keep their own spellings: a struct's or namedtuple's sub-flags, a
    collection's element indices, a dict's keys, a callable's openers, a registered
    leaf's tag hatch, and a multi-variant union, whose cast flags are registered
    statically for the union's own scalars.

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
        docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags
    """
    core = _unwrap_optional(_resolve_type(parent))
    if core is None:
        return False
    return not (
        _is_struct(core)
        or _is_namedtuple(core)
        or _is_dict(core)
        or _is_callable(core)
        or _is_registered_leaf(core)
        or _is_varlen_collection(core)
        or _is_tuple(core)
    )


def _build_leaf_spec(  # noqa: PLR0911 PLR0913 PLR0917
    flag: str,
    raw_type: Any,
    core: Any,
    help_text: HelpParts,
    group: str | None,
    group_description: str,
) -> FlagSpec:
    """Build a FlagSpec for a single leaf field."""
    meta = _get_field_meta(raw_type)
    metavar: str | None = meta.metavar if meta is not None else None
    base = FlagSpec(
        name=flag,
        help=help_text.prose,
        note=help_text.note,
        group=group,
        group_description=group_description,
    )

    if _is_bool(core):
        return dataclasses.replace(base, metavar=metavar or "true|false")

    if _is_varlen_collection(core):
        # One of _takes_multi_tokens' two disjuncts, so stands_bare holds here by that rule.
        et = _resolve_type(_elem_type(core))
        return dataclasses.replace(
            base,
            nargs="*",
            stands_bare=True,
            metavar=metavar or getattr(et, "__name__", "ITEM").upper(),
        )

    if _is_tuple(core):
        # _is_varlen_collection above absorbed tuple[X, ...], so a tuple
        # reaching here is fixed-length and tt is non-None. The guard narrows
        # the type; the None branch is unreachable.
        tt = _tuple_types(core)
        if tt is not None:
            return dataclasses.replace(
                base,
                nargs=len(tt),
                whole_value=True,
                metavar=metavar or "VALUE",
            )

    if _is_literal(core):
        return dataclasses.replace(base, choices=_literal_cli_choices(_literal_values(core)))

    if _is_enum(core):
        return dataclasses.replace(
            base,
            choices=_enum_choices(core),
            metavar=metavar or flag.rsplit(".", 1)[-1].upper(),
        )

    if _is_type_ref(core):
        return dataclasses.replace(base, metavar=metavar or "DOTTED.CLASS.PATH")

    # Generic scalar (str, int, float, Path, …)
    type_name = getattr(core, "__name__", "VALUE").upper()
    return dataclasses.replace(base, metavar=metavar or type_name)


# An index spelling's own segment: ``0``, ``-1`` — either sign, digits only.
_INDEX_SEGMENT = re.compile(r"-?\d+")

# (opener_suffix, opener) for each opener a ``--<field>.<opener>`` flag can spell.
_OPENER_SPECS: tuple[tuple[str, str], ...] = tuple((f".{opener}", opener) for opener in _OPENERS)


def _build_callable_fn_specs(
    flag: str,
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<flag>.bind``, ``--<flag>.class``, ``--<flag>.call``, ``--<flag>.classfn``."""
    return [
        FlagSpec(
            name=f"{flag}.{sub}",
            metavar="DOTTED.PATH",
            note=f"Dotted import path for the '{flag}' callable ({desc}).",
            group=group,
            group_description=group_description,
        )
        for sub, desc in (
            ("bind", "function or class; the --FLAG.args.PARAM flags are partially applied to it"),
            ("class", "class to instantiate from the --FLAG.FIELD flags; the instance is the callable"),
            ("call", "factory function to call with the --FLAG.args.PARAM flags; its result is the callable"),
            ("classfn", "instance method; the --FLAG.FIELD flags build its owner"),
        )
    ]


def _make_path_completer(paths: list[str]) -> Callable[[str], list[str]]:
    return lambda prefix: [p for p in paths if p.startswith(prefix)]


def _build_union_tag_spec(
    flag: str,
    union_tag: str,
    variant_types: list[Any],
    group: str | None,
    group_description: str,
) -> FlagSpec:
    """Build a FlagSpec for ``--<flag>.<union_tag>`` with an optional path completer."""
    completer = None
    if variant_types:
        paths = [dotted_name(v) for v in variant_types]
        completer = _make_path_completer(paths)
    return FlagSpec(
        name=f"{flag}.{union_tag}",
        metavar="DOTTED.CLASS.PATH",
        note=(
            f"Fully-qualified class path selecting the variant for '{flag}' "
            f"(e.g. mypackage.MyClass). "
            "Once set, use that class's field flags."
        ),
        group=group,
        group_description=group_description,
        completer=completer,
    )


def _argument_specs_from_signature(
    field_flag: str,
    sig: inspect.Signature,
    existing_names: set[str],
    *,
    grouped: bool = True,
) -> list[FlagSpec]:
    """Build ``--<field_flag>.args.<param>`` FlagSpecs from the signature of the callable a spec's target yields.

    A ``bind`` or ``call`` spec holds its target's arguments under ``args``, so the flags sit
    below it. One flag per parameter a caller fills
    (:func:`~confarg._callable._fillable_params`), the parameters construction counts.
    *grouped* puts them in a group named after the field, which only a Callable field leaves
    free: a struct field's own flags already hold that name with another description, and
    cyclopts refuses two such groups.

    Dev Notes:
        docs-dev/architecture/callables.md#one-coercion-route
    """
    group_desc = f"Arguments for callable '{field_flag}'"
    result: list[FlagSpec] = []
    for param in _fillable_params(sig.parameters):
        param_name = param.name
        dest = f"{field_flag}.{_defaults.ARGS_KEY}.{param_name}"
        if dest in existing_names:
            continue
        help_parts = []
        ann = param.annotation
        if ann is not inspect.Parameter.empty:
            help_parts.append(getattr(ann, "__name__", repr(ann)))
        if param.default is not inspect.Parameter.empty:
            help_parts.append(f"default: {param.default!r}")
        with contextlib.suppress(Exception):
            result.append(
                FlagSpec(
                    name=dest,
                    metavar=param_name.upper(),
                    note=", ".join(help_parts),
                    group=field_flag if grouped else None,
                    group_description=group_desc if grouped else "",
                ),
            )
        existing_names.add(dest)

    return result


def _collect_callable_argument_specs(
    field_flag: str,
    target_path: str,
    existing_names: set[str],
    *,
    grouped: bool = True,
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<field_flag>.args.<param>`` from the signature the named target yields.

    The signature is the one construction calls (:func:`~confarg._callable._target_signature`):
    an instance method's receiver is bound off, a function's declared ``self`` is kept.
    """
    try:
        sig = _target_signature(target_path)
    except (SymbolImportError, ValueError, TypeError):
        return []
    return _argument_specs_from_signature(field_flag, sig, existing_names, grouped=grouped)


def _collect_callable_factory_specs(
    flag: str,
    cls: type,
    existing_names: set[str],
    group: str | None = None,
    group_description: str = "",
) -> list[FlagSpec]:
    """Build FlagSpecs for factory-mode constructor kwargs of ``cls``."""
    try:
        fields = _init_fields(cls)
        defaults = _init_defaults(cls)
    except (ValueError, TypeError, NameError, AttributeError):
        return []

    result: list[FlagSpec] = []
    for param_name, ft in fields.items():
        dest = f"{flag}.{param_name}"
        if dest in existing_names:
            continue
        core_ft = _resolve_type(ft)
        help_parts: list[str] = []
        type_name = getattr(core_ft, "__name__", repr(core_ft))
        if type_name and type_name != "Any":
            help_parts.append(type_name)
        if param_name in defaults:
            help_parts.append(f"default: {defaults[param_name]!r}")
        with contextlib.suppress(Exception):
            result.append(
                _build_leaf_spec(dest, ft, core_ft, HelpParts(note=", ".join(help_parts)), group, group_description),
            )
        existing_names.add(dest)

    return result


def _collect_callable_field_specs(
    field_flag: str,
    target_path: str,
    mode: str,
    existing_names: set[str],
    *,
    grouped: bool = True,
) -> list[FlagSpec]:
    """Build the argument FlagSpecs for one callable spec given its target and its opener, *mode*.

    A ``class`` target's arguments are its fields, ``--<field>.<name>``, typed as they are,
    and so are those of a ``classfn`` target's owner; a ``bind`` or ``call`` target's are
    the parameters of the function, or of the class's constructor, that it names,
    ``--<field>.args.<param>``, grouped under the field when *grouped*. A ``classfn`` target
    that names no instance method buys nothing: construction refuses it.
    """
    if mode == _defaults.CLASSFN_KEY:
        owner = _instance_method_owner(target_path)
        return [] if owner is None else _collect_callable_factory_specs(field_flag, owner, existing_names)
    if mode == _defaults.CLASS_KEY:
        with contextlib.suppress(SymbolImportError):
            cls = _import_dotted(target_path)
            if isinstance(cls, type):
                return _collect_callable_factory_specs(field_flag, cls, existing_names)
    return _collect_callable_argument_specs(field_flag, target_path, existing_names, grouped=grouped)


def _match_opener_suffix(key: str) -> tuple[str, str] | None:
    """Return (field_flag, opener) if ``key`` ends with an opener suffix."""
    for suffix, opener in _OPENER_SPECS:
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)], opener
    return None


def _is_callable_field(target: object, field_flag: str, union_tag: str) -> bool:
    """Return True if the dotted ``field_flag`` resolves to a callable-typed field."""
    from confarg._parse_cli import _resolve_field_type  # noqa: PLC0415  # import cycle

    resolved = _resolve_field_type(target, field_flag.split("."), union_tag)
    return resolved is not None and _is_callable(_unwrap_optional(_resolve_type(resolved)))


def _opens_spec_at(target: object, field_flag: str, opener: str, union_tag: str) -> bool:
    """Return True if ``--<field_flag>.<opener>`` opens a spec at ``field_flag``.

    The argv opener scan pattern-matches ``--<path>.bind/.class/.call`` against argv, so a
    struct field literally named ``bind`` (or ``class``/``call``) would be misread as an
    opener for its parent.  Asking the type walk keeps the scan from registering argument
    flags below a path that holds no spec (BUG-30): any opener opens one on a callable
    field, and ``call`` on a field that takes a typed call
    (:func:`~confarg._parse_cli._opener_at`).

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    from confarg._parse_cli import _opener_at  # noqa: PLC0415  # import cycle

    return _opener_at(target, [*field_flag.split("."), opener], union_tag)


def _collect_fn_paths_from_argv(
    argv: Sequence[str],
    target: object,
    union_tag: str,
) -> dict[str, tuple[str, str]]:
    """Scan argv for --<field>.bind/.class/.call/.classfn.

    Returns {field_flag: (target_path, opener)}. CLI wins for duplicate keys.

    A match is kept only when the opener opens a spec at ``field_flag`` in *target*
    (:func:`_opens_spec_at`), so a plain struct field named like an opener
    (``bind``/``class``/``call``) is a value, not an opener (BUG-30).  The whole-value
    blob walk already applies this type-guided rule; the scan now agrees with it.
    """
    found: dict[str, tuple[str, str]] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            key, _, val = tok[2:].partition("=")
            matched = _match_opener_suffix(key)
            if matched is not None and _opens_spec_at(target, *matched, union_tag):
                found[matched[0]] = (val, matched[1])
            i += 1
        else:
            matched = _match_opener_suffix(tok[2:])
            if matched is not None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                if _opens_spec_at(target, *matched, union_tag):
                    found[matched[0]] = (argv[i + 1], matched[1])
                i += 2
            else:
                i += 1
    return found


def _blob_document_from_argv(target: Any, argv: Sequence[str], union_tag: str) -> MergeDict:
    """Nest every whole-value ``--<dotted.path> <value>`` token of argv into one document.

    The result is shaped like a config file, so :func:`_collect_fn_paths_from_config`
    reads the callable openers a whole value spells with the very walk it uses on
    ``--config`` files.  That walk is type-guided, which is what keeps a mapping field
    whose value happens to carry a ``class`` key from being read as a callable spec.

    Both whole-value shapes are collected, because a config file may spell a callable
    either way and the walk already reads both: a ``{``-prefixed blob, where vanilla's loop
    decodes one (:func:`~confarg._parse_cli._takes_whole_value`), and a bare string,
    which is the shorthand for ``{bind: <string>}`` and must buy the same argument flags.  A
    malformed blob is skipped rather than raised on — registration is best-effort, and
    the real error belongs to the parse.  A key that would have to descend through a
    shorthand already collected is skipped too: it is the refinement, not a competitor.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    from confarg._parse_cli import _resolve_field_type, _takes_whole_value  # noqa: PLC0415  # import cycle

    doc: MergeDict = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            key, _, val = tok[2:].partition("=")
            i += 1
        elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            key, val = tok[2:], argv[i + 1]
            i += 2
        else:
            i += 1
            continue
        parts = key.split(".")
        if any(isinstance(_peek_nested(doc, parts[:n]), str) for n in range(1, len(parts))):
            continue
        if val.startswith("{"):
            # Read whole only where vanilla's loop decodes it; elsewhere it is text (BUG-216).
            if not _takes_whole_value(_resolve_field_type(target, parts, union_tag), val):
                continue
            with contextlib.suppress(json.JSONDecodeError):
                decoded = json.loads(val)
                if isinstance(decoded, dict):
                    _set_nested(doc, parts, decoded)
        else:
            _set_nested(doc, parts, val)
    return doc


def _yielded_callable_path(spec: Any) -> str | None:
    """Return a dotted path whose signature lists the arguments of the callable *spec* yields.

    ``None`` when the spec names none: a ``call:`` yields whatever its target returns, and a
    target that is no dotted path names nothing to inspect. An instance's arguments are its
    class's ``__call__``, a bound method's are the method's, a partial's its target's.
    """
    if isinstance(spec, str):
        return spec
    if not isinstance(spec, dict):
        return None
    opener = spec_opener(spec)
    if opener is None:
        return None
    value = spec[opener]
    if opener == _defaults.BIND_KEY:
        return _yielded_callable_path(value)
    if opener == _defaults.CALL_KEY or not isinstance(value, str):
        return None
    return f"{value}.__call__" if opener == _defaults.CLASS_KEY else value


def _spec_openings(flag: str, sub: Any, *, typed: bool = False) -> dict[str, tuple[str, str]]:
    """Return {flag: (target_path, opener)} for the spec *sub* at *flag*, nested target specs included.

    Checks the string shorthand (implicit "bind") and the opener construction reads the
    spec by (:func:`~confarg._callable.spec_opener`). A ``bind`` or ``call`` whose target is
    a spec of its own names two targets: the nested spec's, whose arguments sit below the
    opener (``--<flag>.bind.<field>``, ``--<flag>.bind.args.<param>``), and the callable that
    spec yields, whose arguments sit under the outer ``args`` (``--<flag>.args.<param>``,
    :func:`_yielded_callable_path`). *typed*: the spec fills a field that is no Callable,
    where only ``call`` opens one and a string is a value.

    Dev Notes:
        docs-dev/architecture/callables.md#cli
    """
    if isinstance(sub, str):
        return {} if typed else {flag: (sub, _defaults.BIND_KEY)}
    if not isinstance(sub, dict):
        return {}
    opener = spec_opener(sub)
    if opener is None or (typed and opener != _defaults.CALL_KEY):
        return {}
    value = sub[opener]
    if isinstance(value, str):
        return {flag: (value, opener)}
    if not (isinstance(value, dict) and opener in (_defaults.BIND_KEY, _defaults.CALL_KEY)):
        return {}
    found = _spec_openings(f"{flag}.{opener}", value)
    yielded = _yielded_callable_path(value)
    if yielded is not None:
        found[flag] = (yielded, opener)
    return found


def _collect_fn_paths_from_config(
    config_dict: MergeDict,
    target: Any,
    prefix: str,
    union_tag: str,
) -> dict[str, tuple[str, str]]:
    """Walk target + config_dict to find the targets the callable specs name.

    A spec is a Callable field's value, or a ``call:`` filling a field of any other type
    (:func:`~confarg.typedload._construct._is_typed_call`). Returns {field_flag:
    (target_path, opener)} (:func:`_spec_openings`).
    """
    result: dict[str, tuple[str, str]] = {}
    tp = _resolve_type(target)
    if not _is_struct(tp):
        return result
    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return result

    for name, ft in flds.items():
        flag = f"{prefix}.{name}" if prefix else name
        resolved = _unwrap_optional(_resolve_type(ft))
        if resolved is None:
            continue
        sub = config_dict.get(name)
        if _is_callable(resolved):
            result.update(_spec_openings(flag, sub))
        elif _is_typed_call(sub, ft):
            result.update(_spec_openings(flag, sub, typed=True))
        elif _is_struct(resolved) and isinstance(sub, dict):
            result.update(_collect_fn_paths_from_config(sub, resolved, flag, union_tag))
    return result


def _callable_argument_targets(
    target: Any,
    argv: Sequence[str],
    config_dict: MergeDict,
    union_tag: str,
) -> list[tuple[str, str, str, bool]]:
    """Return ``(field_flag, target_path, mode, grouped)`` for each spec whose arguments argv may spell.

    The specs come from the ``--config`` files argv names (*config_dict*), from its whole
    values, and from its opener flags, which beat the blob they refine, as the merge does.
    The flags below ``field_flag`` are the arguments of ``target_path`` as *mode* reads them
    (:func:`_collect_callable_field_specs`), grouped under the field when it is a Callable
    one. Flag registration and argparse's completion both ask it.
    """
    config_fns = _collect_fn_paths_from_config(config_dict, target, "", union_tag)
    blob_fns = _collect_fn_paths_from_config(_blob_document_from_argv(target, argv, union_tag), target, "", union_tag)
    argv_fns = _collect_fn_paths_from_argv(argv, target, union_tag)
    return [
        (field_flag, target_path, mode, _is_callable_field(target, field_flag, union_tag))
        for field_flag, (target_path, mode) in {**config_fns, **blob_fns, **argv_fns}.items()
    ]


def _index_spelled(flag: str) -> bool:
    """Return whether the flag's own segment is an index spelling (``pt.0``, ``pt.-1``)."""
    return _INDEX_SEGMENT.fullmatch(flag.rsplit(".", 1)[-1]) is not None


def _addresses_fixed_seq_element(target: Any, path: list[str], union_tag: str) -> bool:
    """Return whether *path*'s own segment indexes a fixed-length sequence element.

    The patch-scan twin of the namedtuple walk's hiding: an element flag whose
    parent node is a fixed-length sequence — a ``tuple[X, Y]`` or a namedtuple —
    is an index spelling, hidden from ``--help`` while still accepted, exactly as
    a namedtuple's own per-index flags are (BUG-80).  A varlen collection's
    element flag and a dict key spelled as digits keep their place in help.

    Dev Notes:
        docs-dev/architecture/design-decisions/index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help
    """
    if len(path) <= 1 or _INDEX_SEGMENT.fullmatch(path[-1]) is None:
        return False
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import _resolve_field_type  # noqa: PLC0415

    parent = _resolve_field_type(target, path[:-1], union_tag)
    if parent is None:
        return False
    core = _unwrap_optional(_resolve_type(parent))
    if core is None:
        return False
    return _is_namedtuple(core) or (_is_tuple(core) and _tuple_types(core) is not None)


@dataclasses.dataclass(frozen=True)
class _Descent:
    """Where a registration walk stands: the nodes already on its path, and the flags argv types.

    A node is a struct or a namedtuple, the two shapes a walk enters by their members' names.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered
    """

    on_path: frozenset[Any] = frozenset()
    typed: frozenset[str] = frozenset()

    def entering(self, tps: Iterable[Any]) -> _Descent:
        """Return the descent below a node walked as *tps*, entered whatever is on the path."""
        return dataclasses.replace(self, on_path=self.on_path | _walked_nodes(tps))

    def into(self, path: str, tps: Iterable[Any]) -> _Descent | None:
        """Return the descent below the node at *path*, walked as *tps*, or None where the walk stops.

        The walk stops at a node whose structs and namedtuples are all already on the path,
        unless argv types a flag below it.
        """
        nodes = _walked_nodes(tps)
        if nodes and nodes <= self.on_path and not any(key.startswith(f"{path}.") for key in self.typed):
            return None
        return dataclasses.replace(self, on_path=self.on_path | nodes)


def _walked_nodes(tps: Iterable[Any]) -> frozenset[Any]:
    """Return the structs and namedtuples a node of the types *tps* is walked as."""
    from confarg._parse_cli import _union_branches  # noqa: PLC0415  # import cycle

    return frozenset(node for tp in tps for node in _union_branches(tp) if _is_struct(node) or _is_namedtuple(node))


def _collect_namedtuple_specs(  # noqa: PLR0913, PLR0917  # _specs_for_field's context, plus its help
    core: Any,
    flag: str,
    union_tag: str,
    group: str | None,
    group_description: str,
    help_text: HelpParts,
    descent: _Descent,
) -> list[FlagSpec]:
    """Build FlagSpecs for a namedtuple field: its arity flag, then each field's flags.

    Each field takes, under all three of its own keys — the name, the index, and the
    negative index that counts from the end — the flags that field type takes as a
    struct's field, because vanilla resolves a path through a namedtuple's fields as
    through a struct's (BUG-68, BUG-112) and takes a fixed-length sequence's negative
    indices as a tuple's (BUG-80).  Every index-spelled flag is hidden from help, so
    each field's help names its position.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
        docs-dev/architecture/design-decisions/index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help
    """
    flds = _namedtuple_fields(core)
    n = len(flds)
    docstrings = _get_field_docstrings(core)
    defaults = _namedtuple_defaults(core)
    result: list[FlagSpec] = [
        FlagSpec(
            name=flag,
            nargs=n,
            whole_value=True,
            metavar="VALUE",
            help=help_text.prose,
            note=f"{help_text.note} (positional order: {', '.join(flds)})".strip(),
            group=group,
            group_description=group_description,
        ),
    ]
    from confarg._parse_cli import _namedtuple_position_spellings  # noqa: PLC0415  # import cycle

    below = descent.into(flag, [core])
    if below is not None:
        for i, (fname, ft) in enumerate(flds.items()):
            for key in (fname, *_namedtuple_position_spellings(n, i)):
                result.extend(
                    _specs_for_field(
                        f"{flag}.{key}",
                        fname,
                        ft,
                        _resolve_type(ft),
                        union_tag,
                        group,
                        group_description,
                        docstrings,
                        defaults,
                        below,
                        position=i,
                    ),
                )
    # A field's index spellings end in a numeric segment, and so does a deep
    # namedtuple's own arity flag under one; the recursion already marked the
    # flags it generated, so one pass over the result covers what this level added.
    for spec in result:
        if _index_spelled(spec.name):
            spec.hidden = True
    return result


def _union_cast_flag_specs(
    flag: str,
    cast_types: list[type],
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build ``--<flag>.<scalar>`` force-cast FlagSpecs for a multi-variant union."""
    return [
        FlagSpec(
            name=f"{flag}.{tp.__name__}",
            metavar=tp.__name__.upper(),
            note=f"Force {tp.__name__!r} type for '{flag}' (bypasses the stealing rule).",
            group=group,
            group_description=group_description,
        )
        for tp in cast_types
    ]


def _whole_value_spec(
    flag: str,
    resolved: Any,
    help_text: HelpParts,
    group: str | None,
    group_description: str,
) -> FlagSpec:
    """Return the bare ``--<flag>`` spec assigning the whole field value in one token.

    ``nargs=None``: the vanilla parser consumes exactly one token here and rejects a
    second as a stray positional.  The metavar is ``JSON`` only where that token is
    actually decoded as an object, so a field the predicate declines does not advertise
    a syntax it will not honour.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import _accepts_object_value  # noqa: PLC0415

    return FlagSpec(
        name=flag,
        metavar="JSON" if _accepts_object_value(resolved) else "VALUE",
        help=help_text.prose,
        note=help_text.note,
        group=group,
        group_description=group_description,
    )


def _specs_for_field(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0917  # one branch per type case
    flag: str,
    name: str,
    raw_type: Any,
    resolved: Any,
    union_tag: str,
    group: str | None,
    group_description: str,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
    descent: _Descent,
    *,
    position: int | None = None,
) -> list[FlagSpec]:
    """Return FlagSpecs for one field of a struct type, or of a namedtuple at *position*.

    A node already on *descent*'s path registers its own flags and none of its members'.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered
    """
    help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag, position=position)
    core = _unwrap_optional(resolved)
    if core is None:
        non_none = _union_args_no_none(resolved)
        concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
        if concrete:
            # The bare flag first: a whole variant object carries its own discriminator.
            whole = _whole_value_spec(flag, resolved, help_text, group, group_description)
            specs = [whole, _build_union_tag_spec(flag, union_tag, concrete, group, group_description)]
            by_name: dict[str, FlagSpec] = {s.name: s for s in specs}
            below = descent.into(flag, [resolved])
            for variant in concrete if below is not None else []:
                for spec in _collect_struct_specs(
                    variant,
                    flag,
                    union_tag,
                    group=variant.__name__,
                    group_description=_struct_doc(variant),
                    descent=below,
                ):
                    _merge_or_append_spec(specs, by_name, spec)
            return specs
        # Union with a sequence variant (str | tuple[...], str | list[str]) →
        # a multi-token flag; vanilla consumes greedily, so register nargs="*".
        if _union_has_seq_variant(resolved):
            # The other _takes_multi_tokens disjunct: greedy, and legal with no token.
            seq_specs: list[FlagSpec] = [
                FlagSpec(
                    name=flag,
                    nargs="*",
                    stands_bare=True,
                    metavar="VALUE",
                    help=help_text.prose,
                    note=help_text.note,
                    group=group,
                    group_description=group_description,
                ),
            ]
            seq_specs.extend(
                _union_cast_flag_specs(flag, _scalar_cast_types_in_union(resolved), group, group_description),
            )
            return seq_specs
        # Any other multi-variant leaf union (str | type, int | float, str | Path, …)
        # is a single scalar flag. Register it unconditionally so the field is
        # accepted; add the force-cast escape hatches for the union's own scalars,
        # which the one admission rule lets through (BUG-94).
        return [
            FlagSpec(
                name=flag,
                metavar="VALUE",
                help=help_text.prose,
                note=help_text.note,
                group=group,
                group_description=group_description,
            ),
            *_union_cast_flag_specs(flag, _scalar_cast_types_in_union(resolved), group, group_description),
        ]

    if _is_callable(core):
        specs: list[FlagSpec] = [_build_leaf_spec(flag, raw_type, core, help_text, group, group_description)]
        specs.extend(_build_callable_fn_specs(flag, group, group_description))
        return specs

    if _is_namedtuple(core):
        specs = _collect_namedtuple_specs(core, flag, union_tag, group, group_description, help_text, descent)
        # The combined arity flag is first.  A bare occurrence of it is a missing
        # value -- unless Optional wraps the field: `Pt | None` is a union with a
        # sequence variant as resolved, which consumes greedily and stands bare,
        # so the flag registers the way that union's own flag does and its arity
        # is build()'s to judge (BUG-79).
        if _union_has_seq_variant(resolved):
            specs[0] = dataclasses.replace(
                specs[0],
                nargs="*",
                whole_value=False,
                stands_bare=True,
            )
        else:
            specs[0] = _refusing_bare(specs[0], resolved)
        return specs

    if _is_registered_leaf(core):
        return [_build_leaf_spec(flag, raw_type, core, help_text, group, group_description)]

    if _is_struct(core):
        whole = _whole_value_spec(flag, resolved, help_text, group, group_description)
        below = descent.into(flag, [resolved])
        if below is None:
            return [whole]
        return [whole, *_collect_struct_specs(core, flag, union_tag, flag, _struct_doc(core), descent=below)]

    if _is_dict(core):
        # A dict has no statically known keys, so the bare flag is its only static form;
        # each --<flag>.<key> found in argv is registered dynamically alongside it.
        return [_whole_value_spec(flag, resolved, help_text, group, group_description)]

    spec = _build_leaf_spec(flag, raw_type, core, help_text, group, group_description)
    # `tuple[X, Y] | None` is a union with a sequence variant as resolved, so its
    # flag registers the way that union's own flag does: greedy, bare-legal, with
    # the arity deferred to build() exactly as vanilla's `_union_seq_value`
    # defers it (BUG-79).
    if _union_has_seq_variant(resolved):
        return [
            dataclasses.replace(
                spec,
                nargs="*",
                whole_value=False,
                stands_bare=True,
            ),
        ]
    # Only the fixed-arity spelling reaches here with a fixed type: a plain
    # `tuple[X, Y]` whose bare occurrence is a missing value.
    return [_refusing_bare(spec, resolved)]


def _collect_union_root_specs(
    variants: list[Any],
    prefix: str,
    union_tag: str,
    descent: _Descent,
) -> list[FlagSpec]:
    """Build FlagSpecs for a union target (variants are the concrete struct types)."""
    tag_name = f"{prefix}.{union_tag}" if prefix else union_tag
    paths = [dotted_name(v) for v in variants]
    result: list[FlagSpec] = []
    by_name: dict[str, FlagSpec] = {}
    # A variant field owning the tag's spelling wins it, so the tag flag that
    # would collide is not registered at all.
    if not any(_union_tag_shadowed(v, union_tag) for v in variants):
        tag_spec = FlagSpec(
            name=tag_name,
            metavar="DOTTED.CLASS.PATH",
            note=(
                "Fully-qualified class path selecting the union variant "
                f"(e.g. {paths[0] if paths else 'mypackage.MyClass'}). "
                "Once set, use the variant's field flags."
            ),
            completer=_make_path_completer(paths),
        )
        result.append(tag_spec)
        by_name[tag_spec.name] = tag_spec
    for variant in variants:
        for spec in _collect_struct_specs(
            variant,
            prefix,
            union_tag,
            group=variant.__name__,
            group_description=_struct_doc(variant),
            descent=descent,
        ):
            _merge_or_append_spec(result, by_name, spec)
    return result


def _collect_struct_specs(  # noqa: C901, PLR0913  # a root call starts its own descent; the context is threaded
    target: Any,
    prefix: str,
    union_tag: str,
    group: str | None = None,
    group_description: str = "",
    *,
    descent: _Descent | None = None,
) -> list[FlagSpec]:
    """Recursively build FlagSpecs for all fields of a struct type.

    *descent* is where the walk stands; ``None`` starts it at *target*, the root.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered
    """
    if descent is None:
        descent = _Descent().entering([target])
    setup = _resolve_struct(target)
    if setup is None:
        tp = _resolve_type(target)
        if _is_union(tp):
            non_none = _union_args_no_none(tp)
            concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if concrete:
                return _collect_union_root_specs(concrete, prefix, union_tag, descent)
        return []
    tp, flds, hints = setup
    var_params = _var_params(tp).names
    docstrings = _get_field_docstrings(tp)
    defaults = _struct_defaults(tp)

    result: list[FlagSpec] = []
    for name in flds:
        if name in var_params:
            continue
        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name
        result.extend(
            _specs_for_field(
                flag,
                name,
                raw_type,
                resolved,
                union_tag,
                group,
                group_description,
                docstrings,
                defaults,
                descent,
            ),
        )

    # Handle inheritance-based dispatch: if this struct has subclasses, register
    # a --<union_tag> selector and the union of all subclass fields.
    direct_subs = [s for s in tp.__subclasses__() if _is_struct(s)]
    if direct_subs:
        all_subs = _struct_subclasses(tp)  # recursive, for tab-completion paths
        tag_name = f"{prefix}.{union_tag}" if prefix else union_tag
        by_name: dict[str, FlagSpec] = {s.name: s for s in result}
        if tag_name not in by_name and not _union_tag_shadowed(tp, union_tag):
            paths = [dotted_name(v) for v in all_subs]
            # An empty completer would suppress the shell's own suggestions, so leave it unset.
            tag_spec = FlagSpec(
                name=tag_name,
                metavar="DOTTED.CLASS.PATH",
                note=(
                    f"Fully-qualified class path selecting the {tp.__name__!r} subclass "
                    f"(e.g. mypackage.SubClass). "
                    f"Once set, use the subclass's field flags."
                ),
                group=group,
                group_description=group_description,
                completer=_make_path_completer(paths) if paths else None,
            )
            result.append(tag_spec)
            by_name[tag_name] = tag_spec
        for sub in direct_subs:
            # A subclass stands at its base's path, so the descent is the base's.
            specs = _collect_struct_specs(sub, prefix, union_tag, group, group_description, descent=descent)
            for spec in (s for s in specs if not _base_declares_path(tp, prefix, s.name)):
                _merge_or_append_spec(result, by_name, spec)

    return result


def _config_file_spec(name: str, config_flag: str, note: str) -> FlagSpec:
    """Build the FlagSpec of a ``--<config_flag>[.<subpath>][+]`` config-file flag.

    The one shape every config-file flag registers: zero *or* more paths, refusing a bare
    occurrence with the message vanilla's loop raises for it.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """
    from confarg._parse_cli import _missing_config_path_msg  # noqa: PLC0415  # import cycle

    return FlagSpec(
        name=name,
        nargs="*",
        metavar="FILE",
        note=note,
        bare_error=_missing_config_path_msg(config_flag),
    )


def _holds_a_fragment(tp: Any) -> tuple[bool, bool]:
    """Return whether a node of type *tp* is a mount point, and whether its fragment names a variant.

    A mount point is a struct (a fragment of known keys), a dict (a fragment of unknown keys),
    or a union whose variants are all structs: the fragment then names its variant with the
    union tag, the way a struct fragment names its keys. ``Optional`` is no variant.
    """
    resolved = _resolve_type(tp)
    core = _unwrap_optional(resolved)
    if core is None:
        return all(_is_struct(_resolve_type(v)) for v in _union_args_no_none(resolved)), True
    return _is_struct(core) or _is_dict(core), False


def _collect_subconfig_specs(target: Any, config_flag: str, union_tag: str) -> list[FlagSpec]:
    """Build the ``--<config_flag>.<path>`` entry of every mount point of *target*, at any depth.

    The entries are read off the walk that checks a mount
    (:func:`~confarg._parse_cli._check_mount_subpath`): the names a node declares
    (:func:`~confarg._parse_cli._member_names` -- a union's variants' and a subclass's
    included), each typed by every branch the walk takes to it
    (:func:`~confarg._parse_cli._field_types`), so ``--help`` lists no mount point the parse
    refuses. A path is listed where every branch reaches a node that holds a fragment
    (:func:`_holds_a_fragment`), in depth-first order, and the walk descends below every
    node that declares names, listed or not: a namedtuple holds no fragment, its struct
    field does. A node already on the path is listed but not entered (:class:`_Descent`),
    so a type that holds itself lists its mount point once.

    Dev Notes:
        docs-dev/architecture/design-decisions/every-mount-point-has-a-help-entry.md#every-mount-point-has-a-help-entry
        docs-dev/architecture/design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import (  # noqa: PLC0415
        _field_types,
        _locals_keys,
        _member_names,
        _walk_target,
    )

    walk_target = _walk_target(target, _locals_keys(target, union_tag))
    result: list[FlagSpec] = []

    def visit(path: tuple[str, ...], ends: list[Any], descent: _Descent) -> None:
        for name in dict.fromkeys(n for end in ends for n in _member_names(end)):
            subpath_parts = (*path, name)
            sub_ends = _field_types(walk_target, list(subpath_parts), union_tag)
            if not sub_ends:
                continue
            shapes = [_holds_a_fragment(end) for end in sub_ends]
            if all(holds for holds, _ in shapes):
                subpath = ".".join(subpath_parts)
                help_text = (
                    f"Config file(s) whose contents are merged under the '{subpath}' field. "
                    f"Equivalent to a root config file with a top-level '{subpath}' key. "
                    "Supports TOML, YAML, and JSON."
                )
                if any(names_variant for _, names_variant in shapes):
                    # The node's own flags are per-variant, so the reader cannot guess the
                    # tag from --help without this line.
                    help_text += f" Its top level must name the chosen variant with the '{union_tag}' key."
                result.append(_config_file_spec(f"{config_flag}.{subpath}", config_flag, help_text))
            below = descent.into(".".join(subpath_parts), sub_ends)
            if below is not None:
                visit(subpath_parts, sub_ends, below)

    visit((), [target], _Descent().entering([target]))
    return result


def _scalar_root_spec(target: Any) -> FlagSpec:
    """Build the nameless FlagSpec for a non-struct (scalar) root target.

    :func:`~confarg.cli._prefix.apply_prefix` turns the empty name into the bare
    ``--<cli_prefix>`` flag -- the only CLI spelling a scalar root has -- and drops
    the spec entirely when no prefix is set.

    The spec is the root type's leaf spec reshaped through
    :meth:`FlagSpec.as_single_token`, because vanilla's
    :func:`~confarg._parse_cli._handle_scalar_root` consumes exactly one token: a
    ``list[int]`` root must not pick up the greedy ``nargs="*"`` that
    :func:`_build_leaf_spec` gives a collection *field*.

    Dev Notes:
        docs-dev/architecture/cli-parsing/cli-prefix.md#cli_prefix
    """
    resolved = _resolve_type(target)
    core = _unwrap_optional(resolved)
    spec = _build_leaf_spec(
        "",
        target,
        resolved if core is None else core,
        HelpParts(note="The configuration value."),
        None,
        "",
    )
    return spec.as_single_token()


def build_static_flags(  # noqa: PLR0913 — one keyword per knob, mirroring confarg.load
    target: object,
    *,
    argv: Sequence[str] = (),
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
) -> list[FlagSpec]:
    """Build the collection of static CLI flags for a dataclass type.

    Walks the type structure to produce :class:`~confarg.cli.argparse.FlagSpec` objects
    for every field that can be represented as a CLI flag.  The result is
    framework-agnostic and can be loaded into any CLI adapter.

    Args:
        target: The dataclass type whose fields to describe.
        argv: The CLI argument list, read only to import the classes it names by
            ``union_tag`` before the type walk -- a subclass is invisible to the walk
            until its module has run.  It never adds a flag of its own: ``()`` (the
            default) and ``argv=[]`` still describe exactly the declared type.
        cli_prefix: Namespace every flag lives under, so ``--<prefix>.<field>``
            distinguishes configuration flags from the host framework's own.
            ``""`` (the default) registers bare field names.  A non-struct
            (scalar) target is registered as the bare ``--<prefix>`` flag, and has
            no CLI spelling at all without a prefix -- as in vanilla.
        union_tag: Discriminator field name (default ``"class"``).
        config_flag: Name of the config-file flag (default ``"config"``).
            Pass ``""`` to omit config-file flag specs.
        config_subkeys: Whether to register ``--<config_flag>.<path>`` flags for
            every mount point of the target, at any depth (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` flag.

    Returns:
        A list of :class:`~confarg.cli.argparse.FlagSpec` objects, one per CLI flag.
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import _locals_keys  # noqa: PLC0415

    import_tagged_classes(argv, target, union_tag=union_tag, config_flag=config_flag)
    flags = _collect_struct_specs(target, prefix="", union_tag=union_tag)
    if not _is_struct_like(_resolve_type(target)):
        flags.insert(0, _scalar_root_spec(target))

    if config_flag:
        # The help names the flag as typed, prefix included: apply_prefix renames specs, not their help.
        typed_flag = in_prefix(config_flag, cli_prefix)
        flags.append(
            _config_file_spec(
                config_flag,
                config_flag,
                "Config file(s) to merge at lowest priority (below env vars and CLI flags). "
                "Multiple files are merged left-to-right; later files override earlier ones. "
                "Supports TOML, YAML, and JSON. "
                f"Use --{typed_flag}.FIELD FILE to scope a file's contents under a specific field "
                f"(e.g. --{typed_flag}.db db.toml merges db.toml as if its keys were nested under 'db').",
            ),
        )
        if config_subkeys:
            flags.extend(_collect_subconfig_specs(target, config_flag, union_tag))
            for key in _locals_keys(target, union_tag):
                # --config.<locals> FILE declares locals from the CLI; not a real field,
                # so _collect_subconfig_specs does not emit it.
                flags.append(
                    _config_file_spec(
                        f"{config_flag}.{key}",
                        config_flag,
                        f"Config file(s) declaring local variables in the {key!r} namespace.",
                    ),
                )

    return apply_prefix(flags, cli_prefix)


def _collect_config_argv_specs(argv: Sequence[str], config_flag: str) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<config_flag>.<subpath>[+]`` flags found in argv.

    Covers the deeper subpaths and ``+`` append flags that static registration does not.
    """
    from confarg._parse_cli import _config_subpath  # noqa: PLC0415  # import cycle

    specs: list[FlagSpec] = []
    seen: set[str] = set()
    prefix = f"--{config_flag}."
    for tok in argv:
        if not tok.startswith(prefix):
            continue
        name = tok.split("=", 1)[0][2:]
        if name in seen:
            continue
        seen.add(name)
        subpath = _config_subpath(name, config_flag)
        action = "appended to" if subpath.endswith("+") else "merged under"
        specs.append(
            _config_file_spec(
                name,
                config_flag,
                f"Config file(s) whose contents are {action} the '{subpath.rstrip('+')}' field path.",
            ),
        )
    return specs


def _collect_callable_key_argv_specs(
    target: object,
    argv: Sequence[str],
    union_tag: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<callable>.<key>`` flags found in argv but not in a signature.

    The signature-driven specs run first and win, so this pass only catches what no
    signature describes: a key of a nested ``bind`` target spec, and an argument the named
    target does not carry — or that names no target at all, the field having no opener
    anywhere (BUG-28). Below a field of any other type the spec is a typed call: its
    ``call`` and ``args`` keys and what is below them.
    The vanilla parser accepts any key below a callable field (:func:`~confarg._parse_cli._addresses_callable_key`), so
    registration follows the same rule and hands the token to the collector as a plain
    string; whether the kwarg is acceptable is construction's answer to give, identically
    in all five front-ends.

    Append and delete flags are skipped: they take no value, or a variable number of them,
    and :func:`_collect_patch_argv_specs` already registers every one of them in the shape
    its mode demands.  Claiming ``--f.<key>-`` here made all three adapters ask for an
    argument the delete flag does not take (BUG-29).

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import (  # noqa: PLC0415
        _addresses_callable_key,
        _looks_like_flag,
        _normalize_eq_args,
        _parse_flag_mode,
    )

    specs: list[FlagSpec] = []
    for tok in _normalize_eq_args(list(argv)):
        if not _looks_like_flag(tok):
            continue
        key = tok[2:]
        _path, append_mode, delete_mode, _delete_idx, _is_list_delete = _parse_flag_mode(key)
        if append_mode or delete_mode:
            continue
        if key in existing_names or not _addresses_callable_key(target, key.split("."), union_tag):
            continue
        existing_names.add(key)
        specs.append(FlagSpec(name=key, metavar="VALUE", note=f"Value for '{key}' in the callable spec."))
    return specs


def _collect_leaf_tag_argv_specs(
    target: object,
    argv: Sequence[str],
    union_tag: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build FlagSpecs for the flat tagged-leaf flags (``--<leaf>.class``, ``--<leaf>.<param>``) typed in argv.

    An explicit ``class`` tag opens a registered leaf and builds it from its
    ``__init__`` parameters; the flat spelling of that hatch is what the environment
    says with ``PFX_<FIELD>__CLASS`` / ``PFX_<FIELD>__<PARAM>``, and vanilla accepts it
    because its type walk treats a registered leaf structurally -- the tag segment
    through the ``union_tag`` rule, a parameter through the leaf's ``__init__`` fields.
    Registration accepts exactly what that walk accepts: a flag naming no tag and no
    parameter stays unregistered, for the framework to reject as vanilla's
    ``no_such_field`` does.  A registered leaf that *is* the target answers too, at the
    empty prefix (BUG-71): the root has no field to descend from, and its tag flag's
    only segment is the tag -- the walk answers that segment whatever the target.

    Registered only when typed, like a typed call's opener, and for the same reason: a
    registered leaf's ordinary spelling is its scalar, and one flag per ``__init__``
    parameter would clutter ``--help`` for the escape hatch
    (docs-dev/architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in).

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import (  # noqa: PLC0415
        _looks_like_flag,
        _normalize_eq_args,
        _parse_flag_mode,
        _walk_path,
    )

    specs: list[FlagSpec] = []
    for tok in _normalize_eq_args(list(argv)):
        if not _looks_like_flag(tok):
            continue
        key = tok[2:]
        _path, append_mode, delete_mode, _delete_idx, _is_list_delete = _parse_flag_mode(key)
        if append_mode or delete_mode or key in existing_names:
            # Patch flags are registered by _collect_patch_argv_specs, in the shape
            # their mode demands.
            continue
        parts = key.split(".")
        # Which prefix of the path names a registered leaf? The walk's own answer: the
        # shortest one a branch accepting the whole path stood on a registered leaf at,
        # the walk having forked at every union on the way (``UUID | None``). Stone 0 is
        # the root target itself (BUG-71); a struct field answers no -- its sub-flags are
        # registered statically.
        found = min(
            (
                (k, stone.node)
                for branch in _walk_path(target, parts, union_tag)
                if branch.end is not None
                for k, stone in enumerate(branch.stones)
                if _is_registered_leaf(stone.node)
            ),
            key=operator.itemgetter(0),
            default=None,
        )
        if found is None:
            continue
        j, leaf = found
        leaf_flag = ".".join(parts[:j])
        existing_names.add(key)
        leaf_desc = f"the '{leaf_flag}' registered leaf" if leaf_flag else "the registered leaf target"
        if parts[-1] == union_tag and not _union_tag_shadowed(leaf, union_tag):
            specs.append(
                FlagSpec(
                    name=key,
                    metavar="DOTTED.CLASS.PATH",
                    note=f"Class path opening {leaf_desc} from its constructor parameters.",
                    completer=_make_path_completer([dotted_name(leaf)]),
                ),
            )
        else:
            specs.append(
                FlagSpec(
                    name=key,
                    metavar=parts[-1].upper(),
                    note=f"Constructor parameter '{parts[-1]}' of {leaf_desc}.",
                ),
            )
    return specs


def _collect_patch_argv_specs(  # noqa: C901, PLR0912  # one branch per flag kind (delete/append/tag/patch/cast)
    target: object,
    argv: Sequence[str],
    union_tag: str,
    config_flag: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build FlagSpecs for collection-patch flags found in argv.

    Scans for list index/append/delete and dict-subkey flags
    (``--field.N``, ``--field+``, ``--field.N-``, ``--field.key``) whose dotted
    path the *target* type confirms reaches a list, tuple, set, or dict, plus ``.json``
    casts.  Their values are written from argv by ``_parse_cli``, like every flag's.
    Delete flags register value-less (``nargs=0``); an append registers
    ``nargs="*"`` and ``stands_bare``, since it takes zero *or* more items, and a subkey or
    element flag inherits its arity and ``stands_bare`` from the type it addresses --
    multi-token when a field flag of that type would be (``--map.k`` on a
    ``dict[str, list[int]]``), one token on a scalar (``--map.k`` on a ``dict[str, int]``).

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import (  # noqa: PLC0415
        _addresses_key,
        _locals_keys,
        _looks_like_flag,
        _names_tag_by_fallback,
        _normalize_eq_args,
        _parse_flag_mode,
        _registered_when_typed,
        _resolve_field_type,
        _walk_target,
        detect_force_cast,
    )

    # Same graft the vanilla parser uses, so `--<key>.<name>` registers through
    # the identical path as any other dict subkey.
    target = _walk_target(target, _locals_keys(target, union_tag))

    specs: list[FlagSpec] = []
    args = _normalize_eq_args(list(argv))
    for tok in args:
        if not _looks_like_flag(tok):
            continue
        key = tok[2:]
        if _addresses_key(key, config_flag):
            continue  # config files are registered by _collect_config_argv_specs
        if key in existing_names:
            continue
        path, append_mode, delete_mode, _delete_idx, _is_list_delete = _parse_flag_mode(key)
        if not (append_mode or delete_mode):
            path, force_cast = detect_force_cast(path, target, union_tag)
            if force_cast == "json":
                # .json is registered only when typed. An empty path is the root `--json` cast.
                existing_names.add(key)
                target_desc = f"'{'.'.join(path)}'" if path else "the whole config"
                specs.append(
                    FlagSpec(name=key, metavar="JSON", note=f"Parse the value as JSON for {target_desc}."),
                )
                continue
            if force_cast and not _registered_when_typed(target, path, union_tag):
                # A scalar cast on a plain leaf field (--host.str): registered only
                # when typed, like `.json`, so `--help` stays clean (BUG-72). Struct,
                # collection, dict, callable and registered-leaf parents keep their
                # own spellings, and their cast spelling stays refused (BUG-93).
                at = _resolve_field_type(target, path, union_tag)
                if at is not None and _scalar_cast_parent_is_leaf(at):
                    existing_names.add(key)
                    specs.append(
                        FlagSpec(
                            name=key,
                            metavar=SCALAR_CAST_TYPES[force_cast].__name__.upper(),
                            note=f"Force {force_cast!r} type for '{'.'.join(path)}'.",
                        ),
                    )
                continue
            # else: cast on a collection element (--field.N.str) falls through to
            # dynamic collection-patch registration below.
        if not (delete_mode or append_mode or _registered_when_typed(target, path, union_tag)):
            continue
        existing_names.add(key)
        target_path = ".".join(path)
        if delete_mode:
            specs.append(
                FlagSpec(
                    name=key,
                    nargs=0,
                    note=f"Delete the element or key at '{target_path}'.",
                    hidden=_addresses_fixed_seq_element(target, path, union_tag),
                ),
            )
        elif append_mode:
            # nargs="*" and yet legal with no item at all: the shape no clicklike option
            # can express, so `stands_bare` tells the adapters to drop the bare
            # occurrences from the argv their framework parses
            # (docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare).
            specs.append(
                FlagSpec(
                    name=key,
                    nargs="*",
                    metavar="ITEM",
                    stands_bare=True,
                    note=f"Append element(s) to the list at '{target_path}'.",
                ),
            )
        elif _names_tag_by_fallback(target, path, union_tag):
            # A tag takes the one class-path token vanilla's scan consumes for it.
            specs.append(
                FlagSpec(
                    name=key,
                    metavar="DOTTED.CLASS.PATH",
                    note=f"Class path written at '{target_path}', for build() to judge.",
                ),
            )
        else:
            # A subkey or element flag has the shape of the type it addresses, so it stands
            # bare exactly when a field flag of that type would, and refuses its bare
            # occurrence exactly when a field flag of that type would too
            # (docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare).
            # It registers greedily exactly where the loop is told the host binds a run,
            # so a one-token type leaves the token after its value a stray (BUG-179).
            at = _resolve_field_type(target, path, union_tag)
            specs.append(
                _refusing_bare(
                    FlagSpec(
                        name=key,
                        nargs="*" if at is not None and _binds_a_run(at) else None,
                        metavar="VALUE",
                        stands_bare=at is not None and _takes_multi_tokens(at),
                        note=f"Set the collection element at '{target_path}'.",
                        hidden=_addresses_fixed_seq_element(target, path, union_tag),
                    ),
                    at,
                ),
            )
    return specs


def _collect_unentered_argv_specs(
    target: object,
    argv: Sequence[str],
    union_tag: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build the FlagSpecs typed in argv below a node the static walk did not enter.

    The static walk stops at a node already on its path, so a type that holds itself
    (``child: Node | None``) registers ``--child`` and not ``--child.a``. Walking it again with
    that stop lifted along every path argv types reaches each typed flag at the depth vanilla
    reads it, in the shape the static walk gives it there. Only typed names the static walk
    did not register are kept, and with no group, as the other argv-scanned flags.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import _looks_like_flag, _normalize_eq_args  # noqa: PLC0415

    typed = frozenset(tok[2:] for tok in _normalize_eq_args(list(argv)) if _looks_like_flag(tok))
    if not typed:
        return []
    static = {spec.name for spec in _collect_struct_specs(target, "", union_tag)}
    specs: list[FlagSpec] = []
    for spec in _collect_struct_specs(target, "", union_tag, descent=_Descent(typed=typed).entering([target])):
        if spec.name in typed and spec.name not in static and spec.name not in existing_names:
            existing_names.add(spec.name)
            specs.append(dataclasses.replace(spec, group=None, group_description=""))
    return specs


def build_dynamic_flags(  # one branch per argv-scanned flag family (config/locals/callable/patch)
    target: object,
    argv: Sequence[str],
    *,
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
) -> list[FlagSpec]:
    """Build CLI flags discoverable only from argv.

    Scans ``argv`` and any config files it references for ``--<field>.bind``,
    ``--<field>.class``, and ``--<field>.call`` tokens.  For each found path, imports
    the target and generates :class:`~confarg.cli.argparse.FlagSpec` objects for its
    parameters (``--<field>.<param>``: the target's arguments).

    Also registers a spec for every ``--<config_flag>.<subpath>[+]`` token found
    in ``argv``, so scoped and append config-file flags at any depth are accepted
    by the host framework (duplicates of static flags are skipped at load time).

    Also registers the collection-patch flags (``--field.N``, ``--field+``,
    ``--field.N-``, ``--field.key``) and ``.json`` casts found in ``argv``, the
    flat tagged-leaf flags (``--<leaf>.class``, ``--<leaf>.<param>``), the union-tag
    flags the walk reaches by its fallback (``--<path>.class``) at any other path, and
    the flags below a node the static walk did not enter because it was already on the
    path (``--child.child.a`` on a type that holds itself).

    Registration is best-effort: no exception escapes into ``populate_*``.  A failure
    returns no dynamic flag and emits a :class:`~confarg.exceptions.ConfargWarning`
    naming it, since otherwise the only symptom is the host framework later rejecting a
    flag that should exist.  Turn it into an error with
    ``warnings.filterwarnings("error", ConfargWarning)``.

    Args:
        target: The top-level dataclass type.
        argv: The CLI argument list seen so far (e.g. ``sys.argv[1:]`` at
            completion time, or the full argv at parse time).
        cli_prefix: Namespace the flags live under.  argv is stripped of it before
            the scan, so the dotted paths resolve against *target*, and the specs
            are renamed back into the namespace on the way out.
        union_tag: Discriminator field name.
        config_flag: Name of the config-file flag.

    Returns:
        A list of additional :class:`~confarg.cli.argparse.FlagSpec` objects.

    Dev Notes:
        docs-dev/architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags
    """
    try:  # noqa: PLW0717  # best-effort: any failure degrades silently
        # Strip first: the scans below resolve dotted paths against *target*, which
        # knows nothing of the prefix (docs-dev/architecture/cli-parsing/cli-prefix.md#cli_prefix).
        argv_list = strip_argv_prefix(argv, cli_prefix)
        # A subclass is invisible to the walks below until its module has run, and the
        # tag is the only thing that says which module that is
        # (docs-dev/architecture/design-decisions/a-named-tag-is-imported-before-registration.md).
        import_tagged_classes(argv_list, target, union_tag=union_tag, config_flag=config_flag)
        config_dict = _partial_config_from_argv(argv_list, config_flag) if config_flag else {}

        existing_names: set[str] = set()
        # First, as the static flags it stands in for are loaded before every dynamic one.
        result = _collect_unentered_argv_specs(target, argv_list, union_tag, existing_names)
        for field_flag, target_path, mode, grouped in _callable_argument_targets(
            target,
            argv_list,
            config_dict,
            union_tag,
        ):
            result.extend(_collect_callable_field_specs(field_flag, target_path, mode, existing_names, grouped=grouped))
        result.extend(_collect_callable_key_argv_specs(target, argv_list, union_tag, existing_names))
        result.extend(_collect_leaf_tag_argv_specs(target, argv_list, union_tag, existing_names))
        if config_flag:
            result.extend(_collect_config_argv_specs(argv_list, config_flag))
        result.extend(_collect_patch_argv_specs(target, argv_list, union_tag, config_flag, existing_names))
    except Exception as exc:  # noqa: BLE001 — best-effort; must not crash populate_parser
        warnings.warn(
            f"Dynamic CLI flag registration failed ({type(exc).__name__}: {exc});"
            " no dynamic flags were registered, so flags discoverable only from argv"
            " (collection patches, '.json' casts, callable arguments, scoped"
            f" --{config_flag} flags) may be rejected as unknown.",
            ConfargWarning,
            stacklevel=2,
        )
        return []
    else:
        return apply_prefix(result, cli_prefix)
