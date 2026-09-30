# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Collect CLI-provided values from a flat ``{dotted.flag: value}`` dict into a nested dict.

Backend-neutral: every CLI adapter (argparse, click, cyclopts) first flattens its
framework-specific parse result into a plain dict of dotted flag names, then calls
:func:`_collect_ns_fields` to walk the target type and copy matching entries into
the nested structure expected by the merge pipeline.  The result must equal what the
vanilla parser produces for the same argv.

Dev Notes:
    docs-dev/architecture/cli-adapters/parity.md#byte-identical-merged-dicts
"""

from __future__ import annotations

import contextlib
import os
import sys
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

from confarg import _defaults
from confarg._api import build
from confarg._callable import _ESCAPED_DIRECTIVES, _PLAIN_DIRECTIVES, _Directives, active_directives, promote_bare_spec
from confarg._cast import JSON_CAST_NAME, SCALAR_CAST_TYPES, resolve_forced_value
from confarg._import import _import_dotted
from confarg._merge import LIST_REPLACE_BASE_KEY, _deep_merge, _DeleteSentinel, _set_nested
from confarg._parse_cli import (
    _accepts_object_value,
    _collect_cli_patch_ops,
    _collect_config_file_pairs,
    _looks_like_flag,
    _parse_json_arg,
    _resolve_field_type,
    _segment_names_real_field,
    _try_parse_json_list,
)
from confarg._pipeline import _merge_sources
from confarg._tags import collect_tags
from confarg._types import (
    _dataclass_subclasses,
    _elem_type,
    _fixed_seq_types,
    _is_callable,
    _is_dict,
    _is_namedtuple,
    _is_struct,
    _is_struct_like,
    _is_union,
    _is_varlen_collection,
    _namedtuple_fields,
    _resolve_struct,
    _resolve_type,
    _StrToken,
    _union_args_no_none,
    _union_has_scalar_variant,
    _union_has_seq_variant,
    _union_has_varlen_variant,
    _UnionSeqToken,
    _unwrap_optional,
)
from confarg.cli._argv import bare_only_flag_names
from confarg.cli._build import _takes_multi_tokens
from confarg.cli._prefix import strip_argv_prefix, strip_flat_prefix
from confarg.exceptions import ConfargError, SymbolImportError, UnknownArgumentError
from confarg.typedload._coerce import _is_registered_leaf, _try_coerce

#: Sentinel distinguishing "no cast flag present" from a cast that legitimately
#: resolves to ``None`` (e.g. ``--foo.json null``).
_NO_CAST: Any = object()


def _coerce_scalar(tp: Any, v: Any) -> Any:
    """Eagerly coerce a single CLI string value to its field type, mirroring _parse_cli.

    Non-strings pass through unchanged.  Multi-variant unions, dicts, ``Any``, and
    unknown types fall through to a bare :class:`_StrToken` (coercion deferred to
    ``construct()``), exactly as :func:`_try_coerce` does for the vanilla path.
    """
    if not isinstance(v, str):
        return v
    token = _StrToken(v)
    return _try_coerce(tp, token) if tp is not None else token


def _json_array_override(v: Any) -> list[Any] | None:
    """Return a parsed list when a collection field's value is a lone JSON-array token.

    A ``nargs="*"`` flag delivers a single inline JSON array (``['[1, 2]']``) as a
    one-element list holding the raw string. Parsed with the vanilla
    ``_try_parse_json_list`` and returned raw (plain values, not ``_StrToken``), as
    vanilla stores it.
    """
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str) and v[0].startswith("["):
        return _try_parse_json_list(v[0])
    return None


def _coerce_leaf_value(core: Any, v: Any) -> Any:
    """Eagerly coerce a CLI leaf value (scalar or list) to its field type, as vanilla does.

    A list owes its element type to whichever shape owns it: the one element type of a
    varlen collection, the per-position types of a fixed-length sequence
    (:func:`~confarg._types._fixed_seq_types`, the same answer vanilla's
    ``_consume_fixed_tuple_args`` coerces by), and no type at all otherwise.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    parsed = _json_array_override(v)
    if parsed is not None:
        return parsed
    if isinstance(v, list):
        if _is_varlen_collection(core):
            et = _elem_type(core)
            return [_coerce_scalar(et, item) for item in v]
        fixed = _fixed_seq_types(core)
        if fixed is not None:
            return [_coerce_scalar(fixed[i] if i < len(fixed) else None, item) for i, item in enumerate(v)]
        return [_coerce_scalar(None, item) for item in v]
    return _coerce_scalar(core, v)


def _collect_union_seq_value(resolved: Any, v: Any, flag: str) -> Any:
    """Shape a multi-variant union's CLI value, mirroring the vanilla parse path.

    A framework-provided single-element list collapses to a bare scalar when the
    union has a scalar variant (so ``--input foo`` stays ``'foo'``), marked with
    ``_UnionSeqToken`` so ``construct`` can fall back to a one-element list if no
    scalar variant accepts it (e.g. ``--input hello`` for ``bool | list[str]`` →
    ``['hello']``); otherwise the str-tokenized list (or scalar) is returned
    unchanged.

    An empty list raises ``ConfargError`` when the union has no varlen variant
    (e.g. ``str | tuple[str, str]``), like vanilla's ``_consume_union_seq_args``.
    """
    parsed = _json_array_override(v)
    if parsed is not None:
        return parsed
    if isinstance(v, list):
        if not v and not _union_has_varlen_variant(resolved):
            token = f"--{flag}"
            raise ConfargError.missing_value(token)
        if len(v) == 1 and _union_has_scalar_variant(resolved):
            return _UnionSeqToken(v[0]) if isinstance(v[0], str) else v[0]
        return [_str_token(item) for item in v]
    return _str_token(v)


def _find_scalar_cast_override(flat: dict[str, Any], flag: str) -> Any:
    """Return the pinned value for an explicit scalar cast flag, or ``_NO_CAST`` if absent.

    Recognizes ``flag.str``/``flag.int``/``flag.float``/``flag.bool`` via the shared
    :func:`resolve_forced_value`.  ``.json`` is handled for every field type in
    :func:`_collect_ns_fields`, not here.
    """
    for cast_name in SCALAR_CAST_TYPES:
        raw = flat.get(f"{flag}.{cast_name}")
        if raw is not None:
            return resolve_forced_value(cast_name, raw, flag=f"--{flag}.{cast_name}")
    return _NO_CAST


def _find_json_cast(flat: dict[str, Any], flag: str, field_type: Any, union_tag: str) -> Any:
    """Return the decoded value for a ``flag.json`` cast, or ``_NO_CAST`` if it does not apply.

    ``.json`` applies to any field type *unless* ``json`` names a real member of
    ``field_type`` (a struct/namedtuple field, or a dict key), in which case the real
    field wins and ``flag.json`` is an ordinary sub-path handled by the type walk.
    """
    raw = flat.get(f"{flag}.{JSON_CAST_NAME}")
    if raw is None or _segment_names_real_field(field_type, JSON_CAST_NAME, union_tag):
        return _NO_CAST
    return resolve_forced_value(JSON_CAST_NAME, raw, flag=f"--{flag}.{JSON_CAST_NAME}")


def apply_root_json(flat: dict[str, Any], target: Any, union_tag: str, result: dict[str, Any]) -> None:
    """Fold a root-level ``--json`` object into ``result`` as a base, in place.

    The mirror of the vanilla ``_handle_root_cast`` root fold: a bare ``--json`` injects
    the whole config, but per-field CLI flags (already collected into ``result``) win, so
    the decoded object is deep-merged *underneath* ``result``.  A real root field named
    ``json`` wins over the cast (same rule as :func:`_find_json_cast`).  The decoded value
    must be a JSON object for a structured target; for a non-struct (scalar) root it
    becomes ``__root__`` whatever its shape.  Called once at the top level by each
    adapter's context builder.
    """
    raw = flat.get(JSON_CAST_NAME)
    if raw is None or _segment_names_real_field(target, JSON_CAST_NAME, union_tag):
        return
    flag = f"--{JSON_CAST_NAME}"
    decoded = resolve_forced_value(JSON_CAST_NAME, raw, flag=flag)
    if not _is_struct_like(_resolve_type(target)):
        # Non-struct root: the decoded value *is* the configuration, whatever its
        # shape, as in vanilla's _handle_root_cast. setdefault keeps the bare
        # `--<cli_prefix>` flag winning, the same way the deep merge below lets
        # per-field flags win over the injected object.
        result.setdefault(_defaults.ROOT_KEY, decoded)
        return
    if not isinstance(decoded, dict):
        raise ConfargError.root_cast_not_object(flag, decoded)
    merged = _deep_merge(decoded, result, union_tag=union_tag)
    result.clear()
    result.update(merged)


def _str_token(v: Any) -> Any:
    """Wrap str in _StrToken; pass through non-str unchanged."""
    return _StrToken(v) if isinstance(v, str) else v


def _fixed_arity_whole_value(v: Any, core: Any, flag: str) -> Any:
    """Decode the lone whole-value token of a fixed-arity flag, or return :data:`_NO_CAST`.

    A ``FlagSpec.whole_value`` flag registers greedily, so the framework hands its single
    ``'[13, 42]'`` / ``'{"x": 13}'`` token over as a one-element list.  Both halves defer to
    the decoders the other branches use -- :func:`_json_array_override` for the array,
    :func:`_accepts_object_value` plus :func:`_parse_json_arg` for the object -- so a
    fixed-arity field cannot drift from what vanilla decodes for the same token.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    parsed = _json_array_override(v)
    if parsed is not None:
        return parsed
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str):
        token = v[0]
        if token.startswith("{") and _accepts_object_value(core):
            return _parse_json_arg(token, f"--{flag}")
    return _NO_CAST


def _require_fixed_arity(arity: int, tokens: Any, flag: str, core: Any) -> None:
    """Raise unless *tokens* is exactly the token run a fixed-arity flag consumes.

    The adapters' half of the guard vanilla spells as one
    :func:`~confarg._parse_cli._require_value` per positional token
    (:func:`~confarg._parse_cli._consume_fixed_tuple_args`): a fixed arity is not one of the
    shapes a bare flag is reserved for, so a token run that stops short -- argv running out, or
    the next flag arriving -- is a missing value and not a shorter tuple, and a token run that
    overshoots does not grow the tuple either, because vanilla stops consuming at the arity and
    meets the next token as a stray positional.  Argparse and cyclopts register such a flag
    greedily, because ``FlagSpec.whole_value`` needs a variable token count, so the framework
    hands over however many tokens it found and both bounds are nobody else's to check; click
    and typer register the exact count and enforce both themselves.

    How many tokens the run takes is what :func:`_fixed_arity_whole_value` answers, asked of the
    *first* token alone: a whole value is one token whatever its arity, so ``--pair '[13]'``
    stays the arity error ``build()`` owns rather than a flag left without a value, and the ``9``
    in ``--pair '[13]' 9`` is surplus rather than the token that completes it.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    if not isinstance(tokens, list):
        return
    # A whole value is one token; a positional run is the full arity.  Asked of `tokens[:1]`
    # because the decoder wants the lone token it decodes, and here the run may be longer.
    consumed = 1 if _fixed_arity_whole_value(tokens[:1], core, flag) is not _NO_CAST else arity
    if len(tokens) < consumed:
        token = f"--{flag}"
        raise ConfargError.missing_value(token)
    if len(tokens) > consumed:
        raise UnknownArgumentError.unexpected_positional(tokens[consumed])


def _fixed_arity_occurrence_runs(argv: Sequence[str], flag: str) -> list[list[str]]:
    """Return every ``--<flag>`` occurrence's token run, in argv order.

    The argv half of the fixed-arity guard: a greedy registration hands the collector
    only the *surviving* occurrence's run -- argparse's plain store keeps the last,
    cyclopts' converter the last too (BUG-62) -- so whether every occurrence had its
    tokens is read off the argv the user typed, as the latest-writer question is
    (:func:`_arity_flag_writes_last`).  A run ends where vanilla's own consumption
    ends, at the next token that looks like a flag or at the end of argv; the value
    half of ``--flag=value`` opens the run as its first token, however it is spelled,
    and the tokens after it complete it exactly as they complete a bare occurrence's
    run.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    bare = f"--{flag}"
    runs: list[list[str]] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == bare:
            run: list[str] = []
        elif token.startswith(f"{bare}="):
            run = [token[len(bare) + 1 :]]
        else:
            i += 1
            continue
        i += 1
        while i < len(argv) and not _looks_like_flag(argv[i]):
            run.append(argv[i])
            i += 1
        runs.append(run)
    return runs


def _tokens_past_whole_field_delete(argv: Sequence[str], flag: str, value: Any) -> Any:
    """Return *value* with the plain-occurrence tokens a whole-field delete ended dropped.

    The adapters' half of the reset vanilla's ``_handle_delete_token`` owns: there the
    delete pops the token accumulation at its path, so the occurrence after it starts a
    new list.  A framework's parse result carries no order, so the repeated-flag
    convention hands the collector every plain occurrence's tokens in one list -- the
    ones spelled before the delete end up *inside* the value of the occurrence after
    it.  The surviving tokens are read off argv, as the other argv-order questions are
    (:func:`_fixed_arity_occurrence_runs` is the precedent for a reader of this shape).

    Returns *value* unchanged when argv does not spell ``--<flag>-`` at all, when no
    plain occurrence follows it (the delete survives the patch scan and wins on its
    own), or when *value* is not the accumulated plain tokens -- its length does not
    add up to the occurrence runs argv spells -- because a value argv cannot account
    for is not this reader's to rewrite.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#a-whole-field-delete-ends-the-token-accumulation
    """
    if not isinstance(value, list):
        return value
    bare = f"--{flag}"
    delete = f"--{flag}-"
    total = 0
    kept: list[str] | None = None  # becomes the accumulator at the first delete
    followed_by_occurrence = False
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == delete:
            kept = []
            followed_by_occurrence = False
            i += 1
            continue
        if token != bare and not token.startswith(f"{bare}="):
            i += 1
            continue
        run: list[str] = [] if token == bare else [token[len(bare) + 1 :]]
        i += 1
        while i < len(argv) and not _looks_like_flag(argv[i]):
            run.append(argv[i])
            i += 1
        total += len(run)
        if kept is not None:
            kept.extend(run)
            followed_by_occurrence = True
    if kept is None or not followed_by_occurrence or len(value) != total:
        return value
    return kept


def _whole_value(flat: dict[str, Any], flag: str, resolved: Any) -> Any:
    """Return the bare ``--<flag>`` value decoded the way the vanilla parser decodes it.

    A ``{``-prefixed token becomes the object it spells (malformed JSON raises the same
    ``ConfargError`` vanilla raises); anything else is left for the caller's own branch.
    Returns :data:`_NO_CAST` when the flag carries no whole value to decode.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    if flag not in flat:
        return _NO_CAST
    v = flat[flag]
    if isinstance(v, str) and v.startswith("{") and _accepts_object_value(resolved):
        return _parse_json_arg(v, f"--{flag}")
    return _NO_CAST


def _merge_blob_into_spec(
    blob: dict[str, Any],
    spec: dict[str, Any],
    bind: dict[str, Any],
    bind_key: str,
) -> dict[str, Any]:
    """Merge a pre-existing blob dict with the newly assembled spec, combining bind entries."""
    merged = {**blob, **{k: v for k, v in spec.items() if k != bind_key}}
    blob_bind = blob.get(bind_key, {})
    if isinstance(blob_bind, dict) and bind:
        merged[bind_key] = {**blob_bind, **bind}
    elif bind:
        merged[bind_key] = bind
    return merged


def _collect_fn_identity(flat: dict[str, Any], flag: str, d: _Directives) -> dict[str, Any]:
    """Extract fn/class/call identity entries from flat into a spec dict.

    Keyed by the *active* (plain or escaped) directive names, as in a config file.
    """
    spec: dict[str, Any] = {}
    for name in d.openers:
        src_key = f"{flag}.{name}"
        if src_key in flat:
            spec[name] = _str_token(flat[src_key])
    return spec


def _collect_factory_kwargs(
    flat: dict[str, Any],
    flag_prefix: str,
    bind_prefix: str,
    reserved: set[str],
) -> dict[str, Any]:
    """Collect top-level factory kwargs (positional result fields) from flat namespace."""
    kwargs: dict[str, Any] = {}
    for k, v in flat.items():
        if k.startswith(flag_prefix) and k not in reserved and not k.startswith(bind_prefix):
            tail = k[len(flag_prefix) :]
            if "." not in tail:
                kwargs[tail] = _str_token(v)
    return kwargs


def _collect_bind_sections(flat: dict[str, Any], flag: str, d: _Directives) -> dict[str, dict[str, Any]]:
    """Nest the ``--<flag>.<bind>.<path>`` entries of the flat namespace, one dict per spelling.

    Both spellings are collected: the active one is the directive, and the one the opener
    left inactive is a kwarg, not a directive — but still a subtree, which construction
    is the one to accept or reject.  Neither depends on an opener being present, and
    dotted tails nest, so the sections match what the vanilla parser writes for the very
    same flags.

    Dev Notes:
        docs-dev/architecture/callables.md#plain-and-escaped-directives
    """
    other = _PLAIN_DIRECTIVES.bind if d.bind == _ESCAPED_DIRECTIVES.bind else _ESCAPED_DIRECTIVES.bind
    sections: dict[str, dict[str, Any]] = {}
    for key in (d.bind, other):
        prefix = f"{flag}.{key}."
        subtree: dict[str, Any] = {}
        for k, v in flat.items():
            if k.startswith(prefix):
                _set_nested(subtree, k[len(prefix) :].split("."), _str_token(v))
        if subtree:
            sections[key] = subtree
    return sections


def _collect_callable_spec(
    flat: dict[str, Any],
    flag: str,
    result: dict[str, Any],
    whole: Any = _NO_CAST,
) -> None:
    """Build and store the callable spec dict from flat namespace entries for flag.

    Directive flags come in a plain and an escaped (single-underscore) form; the opener
    selects the mode via :func:`~confarg._callable.active_directives`.  An opener spelled
    inside the whole-value blob counts as one: vanilla deep-merges the blob and its
    sibling flags into a single spec before anything reads an opener, so a blob's
    ``class`` must buy its sibling ``--<field>.<param>`` init kwargs exactly as the
    ``--<field>.class`` flag does.
    """
    blob = (flat[flag] if whole is _NO_CAST else whole) if flag in flat else _NO_CAST
    blob_keys: dict[str, Any] = blob if isinstance(blob, dict) else {}

    def _has(name: str) -> bool:
        return f"{flag}.{name}" in flat or name in blob_keys

    d = active_directives(_has)
    bind_prefix = f"{flag}.{d.bind}."
    flag_prefix = f"{flag}."
    reserved = {f"{flag}.{name}" for name in d.openers}

    spec = _collect_fn_identity(flat, flag, d)

    spec.update(_collect_bind_sections(flat, flag, d))
    bind: dict[str, Any] = spec.get(d.bind, {})

    # Every sibling --<field>.<param> flag is collected, opener or no opener: the vanilla
    # parser writes the whole subtree below the field verbatim and leaves construction to
    # read it -- as an init kwarg under 'class:'/'fn: Class.method', as the ordinary data a
    # directive word in the inactive spelling is, or as the error a stray name earns.
    # Collecting only under an opener dropped the rest silently instead (BUG-28).
    spec.update(_collect_factory_kwargs(flat, flag_prefix, bind_prefix, reserved))

    if blob is not _NO_CAST:
        if isinstance(blob, str):
            if not spec:
                _set_nested(result, flag.split("."), _StrToken(blob))
                return
            # The bare string is the shorthand for {fn: <string>}, so the sibling flags
            # refine the target it names instead of erasing it.  An opener flag is not a
            # refinement but a second spelling of that target, and still wins outright.
            if not any(_has(opener) for opener in d.openers):
                # Opener first, as the vanilla parser writes it: the merged dicts must
                # match key for key, not just compare equal.
                spec = {**promote_bare_spec(_StrToken(blob)), **spec}
        elif isinstance(blob, dict):
            spec = _merge_blob_into_spec(blob, spec, bind, d.bind)

    if spec:
        _set_nested(result, flag.split("."), spec)


def _tag_named_struct(class_tag: Any) -> Any:
    """Return the struct type a class tag names, or ``None`` when it names none.

    ``None`` covers both failure modes -- the import fails, or the class is not a struct
    -- because every caller's response is the same: leave the tag where its channel put
    it and move on.  Vanilla stores the raw string and lets ``construct()`` raise the
    import error, so no caller reports the failure itself.
    """
    try:
        cls = _import_dotted(str(class_tag))
    except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
        return None
    return cls if isinstance(cls, type) and _is_struct(_resolve_type(cls)) else None


def _collect_named_variant(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    flag: str,
    class_tag: Any,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
    argv: Sequence[str],
    *,
    base: Any = None,
    write_tag: bool = True,
    siblings: Sequence[Any] = (),
) -> None:
    """Write a class tag back, then descend into the struct it names — and its siblings.

    The tag is written before the import resolves: vanilla keeps
    ``--<path>.<union_tag>`` as a raw string and lets ``construct()`` raise the import
    error naming the bad path, so a tag whose import fails must still reach the merged
    dict (BUG-45).  *write_tag* is off only for a tag a ``--config`` file set: it
    already reaches the merge at its own priority, and re-emitting it at CLI priority
    would make the merged dict differ from vanilla's.  *base* names the class the walk
    is already inside; a tag naming it adds nothing, so the descent stops there.

    *siblings* names the other variants the path holds — a union field's struct
    variants, or a base class's subclasses — and each is descended into after the named
    one, in its own guard: vanilla keeps every argv flag, coerced by whichever variant
    owns the name, and leaves ``build()`` to reject the ones the tagged variant does not
    know, so descending only into the named variant dropped the rest silently (BUG-69).
    A tag whose import fails names no struct, so the siblings are all that is walked,
    and one variant's failure costs no other variant its flags.

    Dev Notes:
        docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags
    """
    if write_tag:
        tag_path = ([*flag.split(".")] if flag else []) + [union_tag]
        _set_nested(result, tag_path, _str_token(class_tag))
    cls = _tag_named_struct(class_tag)
    walked: set[Any] = set()
    for variant in (cls, *siblings):
        if variant is None or variant is base or variant in walked:
            continue
        walked.add(variant)
        with contextlib.suppress(SymbolImportError, TypeError, ValueError, NameError, AttributeError):
            _collect_ns_fields(flat, variant, flag, union_tag, result, tags, argv)


def _collect_ns_union_field(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    flag: str,
    resolved: Any,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
    argv: Sequence[str],
) -> None:
    """Handle a multi-variant union field.

    When the class-tag is present, descend into the named variant and then the others:
    a flag of another variant reaches the merged dict as it does in vanilla, and
    ``build()`` rejects it for the named one (BUG-69).  When the tag is absent,
    collect all struct variant fields so structural inference in typedload can select
    the right one.
    """
    non_none = _union_args_no_none(resolved)
    concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
    if not concrete:
        return
    tag_key = f"{flag}.{union_tag}"
    if tag_key in flat:
        _collect_named_variant(flat, flag, flat[tag_key], union_tag, result, tags, argv, siblings=concrete)
    else:
        for variant in concrete:
            _collect_ns_fields(flat, variant, flag, union_tag, result, tags, argv)


def _collect_ns_inheritance(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    tp: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
    argv: Sequence[str],
) -> None:
    """Handle inheritance dispatch for a base class with subclasses.

    The subclass to descend into is whichever the configuration names at this path -- a
    ``--<path>.<union_tag>`` flag in *flat*, or a tag a ``--config`` file sets, which
    *tags* carries.  Both go through :func:`_collect_named_variant`, which writes only
    the flag's tag back into *result*: a file's tag already reaches the merge at its
    own priority, and re-emitting it at CLI priority would make the merged dict differ
    from vanilla's.

    Dev Notes:
        docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags
    """
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    from_flat = tag_key in flat
    class_tag = flat[tag_key] if from_flat else tags.get(prefix)
    if class_tag is None:
        return
    _collect_named_variant(
        flat,
        prefix,
        class_tag,
        union_tag,
        result,
        tags,
        argv,
        base=tp,
        write_tag=from_flat,
        siblings=_dataclass_subclasses(tp),
    )


def _namedtuple_deep_fields(fields: Mapping[str, Any]) -> list[tuple[Any, list[str]]]:
    """Return ``[(field_type, [spelled keys])]`` for a namedtuple's struct-shaped fields.

    A struct-shaped field — a struct, or another namedtuple, however wrapped — is
    collected by the per-field dispatch rather than as a scalar sub-flag, at each of
    its own spellings, the name and the index alike (BUG-68).  One helper answers the
    question for every caller: the scalar sub-flag collector (which skips them), the
    presence scan and the deep dispatch itself.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    result: list[tuple[Any, list[str]]] = []
    for i, (fname, ftype) in enumerate(fields.items()):
        fcore = _unwrap_optional(ftype)
        if _is_struct(fcore) or _is_namedtuple(fcore):
            result.append((ftype, [fname, str(i)]))
    return result


def _deep_flag_present(flat: dict[str, Any], flag: str, deep_fields: list[tuple[Any, list[str]]]) -> bool:
    """Return whether argv's flat parse result holds any entry under a deep sub-flag."""
    for _ftype, spellings in deep_fields:
        for spelled in spellings:
            sub_flag = f"{flag}.{spelled}"
            if flat.get(sub_flag) is not None:
                return True
            prefix = f"{sub_flag}."
            if any(key.startswith(prefix) and value is not None for key, value in flat.items()):
                return True
    return False


def _collect_deep_sub_flags(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    flag: str,
    deep_fields: list[tuple[Any, list[str]]],
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, Any],
    argv: Sequence[str],
) -> None:
    """Collect a namedtuple's struct-shaped fields, at each of their spellings, into *result*.

    The writes land at the paths the flags spell, as vanilla's own writes do, so a
    deep sub-flag refines whatever is already at its path — a whole value's decoded
    object, or the arity flag's promoted positions — rather than replacing the
    sibling dict a pre-merged value would (BUG-68).
    """
    for ftype, spellings in deep_fields:
        for spelled in spellings:
            _collect_field(flat, ftype, f"{flag}.{spelled}", union_tag, result, tags, argv)


def _namedtuple_sub_flags(flat: dict[str, Any], flag: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Collect a namedtuple's per-name and per-index sub-flags, keys as spelled.

    Both spellings of one field are stored, name and index alike: vanilla writes
    each flag at the key the user spelled and leaves construction to reconcile
    them, so a ``--pt.0`` beside ``--pt.x`` reaches the merged dict as
    ``{'x': 13, '0': 9}`` and ``build()`` owns the refusal (BUG-65).  Each value
    is coerced to its field's type, as the vanilla parser's own dispatch
    coerces the same flag: a raw token here would put a str in the merged dict where
    vanilla puts the number, and an expression over the field would read the token
    (BUG-66).  A struct-shaped field is not a scalar and is skipped: its spellings
    belong to the deep dispatch (BUG-68).
    """
    deep = {spelled for _ftype, spellings in _namedtuple_deep_fields(fields) for spelled in spellings}
    sub: dict[str, Any] = {}
    for i, (fname, ftype) in enumerate(fields.items()):
        for key, spelled in ((f"{flag}.{fname}", fname), (f"{flag}.{i}", str(i))):
            if spelled in deep:
                continue
            if flat.get(key) is not None:
                sub[spelled] = _coerce_leaf_value(ftype, flat[key])
    return sub


def _namedtuple_arity_value(core: Any, nargs_value: Any, whole: Any) -> Any:
    """Return what the arity flag alone supplies: the decoded whole value, or its tokens.

    Positional tokens are coerced to their per-field types, as vanilla's
    ``_consume_fixed_tuple_args`` coerces them.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    if whole is not _NO_CAST:
        return whole
    if isinstance(nargs_value, list):
        fixed = _fixed_seq_types(core) or []
        return [_coerce_scalar(fixed[i] if i < len(fixed) else None, item) for i, item in enumerate(nargs_value)]
    return _str_token(nargs_value)


def _arity_flag_writes_last(argv: Sequence[str], flag: str) -> bool:
    """Return whether the last ``--<flag>`` occurrence follows every ``--<flag>.<sub>`` one.

    The argv-order half of the namedtuple contract (BUG-66): a framework's parse result
    carries no command-line order, so which flag at a namedtuple field is the latest
    writer is read off the argv the user typed, as the patch and ``--config`` scans
    are.  A token that looks like a flag is one here for the same reason it is one in
    the vanilla scan, so the two readers cannot disagree about where an occurrence
    ends.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    bare = f"--{flag}"
    sub_prefix = f"--{flag}."
    last_bare = last_sub = -1
    for i, token in enumerate(argv):
        if token == bare or token.startswith(f"{bare}="):
            last_bare = i
        elif token.startswith(sub_prefix):
            last_sub = i
    return last_bare > last_sub


def _collect_ns_namedtuple(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    core: Any,
    flag: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, Any],
    argv: Sequence[str],
) -> None:
    """Collect a namedtuple field from the flat namespace.

    Sub-flags are stored under the keys the user spelled, name and index alike,
    and construction reconciles them — a collection-time priority would rewrite
    keys vanilla keeps, and drop a ``--pt.0`` a ``--pt.x`` rides with (BUG-65).
    When sub-flags and the arity flag are both set, the arity value is re-keyed
    by field name, as vanilla's own promotion does, and the sub-flags join it at
    their own keys — they are merged, not exclusive — unless the arity flag is
    the latest writer, in which case it overwrites the field wholesale, as the
    vanilla scan's own last write does.  A lone whole-value token refines the
    same way, by name when it spells an object and by position when it spells an
    array.  A struct-shaped field's spellings take the per-field dispatch, at
    whatever depth they sit (BUG-68): the same priority holds a level down, the
    writes land on the paths the flags spell, and a deep sub-flag typed after
    the arity flag joins it while an arity flag typed last takes the field.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    fields = _namedtuple_fields(core)
    field_names = list(fields)
    deep_fields = _namedtuple_deep_fields(fields)
    sub = _namedtuple_sub_flags(flat, flag, fields)
    nargs_value = flat.get(flag)
    path = flag.split(".")

    if nargs_value is None:
        if sub:
            _set_nested(result, path, sub)
        _collect_deep_sub_flags(flat, flag, deep_fields, union_tag, result, tags, argv)
        return

    whole = _fixed_arity_whole_value(nargs_value, core, flag)

    if not sub and not _deep_flag_present(flat, flag, deep_fields):
        # Store what the flag spelled and let build() judge its arity, as the same-arity
        # tuple field does — the framework no longer counts the tokens for us.
        _set_nested(result, path, _namedtuple_arity_value(core, nargs_value, whole))
        return

    if _arity_flag_writes_last(argv, flag):
        # The latest arguments overwrite the earlier ones: the arity flag superseded
        # every sub-flag before it, so its value is the whole field.
        _set_nested(result, path, _namedtuple_arity_value(core, nargs_value, whole))
        return

    if isinstance(whole, dict):
        _set_nested(result, path, {**whole, **sub})
        _collect_deep_sub_flags(flat, flag, deep_fields, union_tag, result, tags, argv)
        return

    value = _namedtuple_arity_value(core, nargs_value, whole)
    base = value if isinstance(value, list) else [value]
    merged: dict[str, Any] = {fname: base[i] for i, fname in enumerate(field_names) if i < len(base)}
    merged.update(sub)
    _set_nested(result, path, merged)
    _collect_deep_sub_flags(flat, flag, deep_fields, union_tag, result, tags, argv)


def _collect_ns_optional_seq(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    resolved: Any,
    core: Any,
    flag: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, Any],
    argv: Sequence[str],
    whole: Any,
) -> None:
    """Collect an ``Optional[<sequence>]`` field, shaping its flag as vanilla shapes the union.

    The resolved type is the one vanilla dispatches -- ``tuple[int, int] | None`` is a
    union with a sequence variant there, consumed greedily and shaped by
    ``_union_seq_value`` -- so the flag's tokens go through
    :func:`_collect_union_seq_value` rather than through the fixed-arity and
    namedtuple branches the unwrapped *core* would pick: a bare occurrence owes its
    value, and the run is stored raw, its per-position coercion deferred to
    ``build()`` (BUG-61).

    A namedtuple's sub-flags keep their own spelling, collected and coerced by
    :func:`_namedtuple_sub_flags` and merged in argv order, as on the plain spelling
    (:func:`_arity_flag_writes_last` decides): the arity flag written last replaces
    the field wholesale, a sub-flag written last descends into whatever the arity
    flag left -- which ``_set_nested`` promotes to the ``'*'`` shape, the same
    promotion vanilla's own descent gives the optional spelling.  An explicit
    scalar cast flag wins over the flag's own value, as in the multi-variant union
    branch.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#unions-with-sequence-variants
    """
    path = flag.split(".")
    cast_val = _find_scalar_cast_override(flat, flag)
    if cast_val is not _NO_CAST:
        _set_nested(result, path, cast_val)
        return
    fields = _namedtuple_fields(core) if _is_namedtuple(core) else {}
    deep_fields = _namedtuple_deep_fields(fields)
    sub = _namedtuple_sub_flags(flat, flag, fields) if fields else {}
    if flag not in flat:
        if sub:
            _set_nested(result, path, sub)
        _collect_deep_sub_flags(flat, flag, deep_fields, union_tag, result, tags, argv)
        return
    v = _tokens_past_whole_field_delete(argv, flag, flat[flag])
    if whole is _NO_CAST:
        # The list spelling of the decode _whole_value does for the str one: a
        # `{...}` a namedtuple accepts is the object it spells, not an ordinary token.
        whole = _fixed_arity_whole_value(v, core, flag)
    value = whole if whole is not _NO_CAST else _collect_union_seq_value(resolved, v, flag)
    _set_nested(result, path, value)
    if not _arity_flag_writes_last(argv, flag):
        for fname, fval in sub.items():
            _set_nested(result, [*path, fname], fval)
        _collect_deep_sub_flags(flat, flag, deep_fields, union_tag, result, tags, argv)


def _collect_ns_union_root(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    variants: list[Any],
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
    argv: Sequence[str],
) -> None:
    """Collect CLI values for a root-level union target (variants are concrete struct types)."""
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    if tag_key in flat:
        tag_path = ([*prefix.split(".")] if prefix else []) + [union_tag]
        _set_nested(result, tag_path, _str_token(flat[tag_key]))
    for variant in variants:
        _collect_ns_fields(flat, variant, prefix, union_tag, result, tags, argv)


def _collect_ns_fields(  # noqa: PLR0913  # one branch per type case
    flat: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str] = MappingProxyType({}),
    argv: Sequence[str] = (),
) -> None:
    """Walk target and copy matching flat-namespace entries into nested dict.

    *tags* is ``{field_path: class_path}`` for every class tag the configuration names
    outside *flat* -- a ``--config`` file's, typically -- so inheritance dispatch sees the
    same subclass the vanilla type walk does.  *argv* is the prefix-stripped command
    line, read back wherever a decision needs the order the user typed the flags in.
    """
    setup = _resolve_struct(target)
    if setup is None:
        tp = _resolve_type(target)
        if _is_union(tp):
            non_none = _union_args_no_none(tp)
            concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if concrete:
                _collect_ns_union_root(flat, concrete, prefix, union_tag, result, tags, argv)
                return
        if "" in flat:
            # Non-struct root: the empty key is the bare `--<cli_prefix>` flag, left
            # behind by strip_flat_prefix. Mirrors vanilla's _handle_scalar_root.
            result[_defaults.ROOT_KEY] = _coerce_scalar(tp, flat[""])
        return
    _tp, flds, hints = setup

    for name in flds:
        if name == union_tag:
            continue

        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name

        _collect_field(flat, resolved, flag, union_tag, result, tags, argv)

    _collect_ns_inheritance(flat, _tp, prefix, union_tag, result, tags, argv)


def _collect_field(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915  # one branch per type case
    flat: dict[str, Any],
    resolved: Any,
    flag: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, Any],
    argv: Sequence[str],
) -> None:
    """Collect one declared field of a struct, at *flag*, into *result*.

    The one per-field dispatch: every path the walk reaches a declared field by --
    a struct's field, or a namedtuple's reached through either of its sub-flag
    spellings (BUG-68) -- hands the field to this same decision-maker, so a field
    behaves the same at every depth.  *resolved* names the field's type as the
    caller's walk resolved it; *result* is written at ``flag.split(".")``.
    """
    core = _unwrap_optional(resolved)

    # `--flag.json` forces a raw-JSON value for any field type, unless `json` names a
    # real member of the field (real field wins). Handled before the type dispatch so
    # struct/namedtuple/callable/collection fields honour it too.
    json_val = _find_json_cast(flat, flag, core if core is not None else resolved, union_tag)
    if json_val is not _NO_CAST:
        _set_nested(result, flag.split("."), json_val)
        return

    # A bare `--<flag> '{...}'` assigns the whole field; sibling `--<flag>.<sub>`
    # entries are collected on top of it below, as they refine it in vanilla.
    whole = _whole_value(flat, flag, resolved)

    if core is None:
        # Struct unions: the whole object carries its own class-tag; variant fields refine it
        if whole is not _NO_CAST:
            _set_nested(result, flag.split("."), whole)
        _collect_ns_union_field(flat, flag, resolved, union_tag, result, tags, argv)
        # Scalar unions: collect plain value or explicit scalar cast
        cast_val = _find_scalar_cast_override(flat, flag)
        if cast_val is not _NO_CAST:
            _set_nested(result, flag.split("."), cast_val)
        elif flag in flat and whole is _NO_CAST:
            v = _tokens_past_whole_field_delete(argv, flag, flat[flag])
            _set_nested(result, flag.split("."), _collect_union_seq_value(resolved, v, flag))
        return

    # Optional[<sequence>]: the union is the type vanilla dispatches, so the flag's
    # tokens take the union's shaping, not the branches the unwrapped core picks
    # (BUG-61).
    if _union_has_seq_variant(resolved):
        _collect_ns_optional_seq(flat, resolved, core, flag, union_tag, result, tags, argv, whole)
        return

    # A fixed-length sequence -- tuple[X, Y] or a namedtuple -- owes every one of its
    # tokens, for the leaf branch below and the namedtuple branch alike.  Asked of
    # *resolved* rather than of `core`, because that is the type vanilla dispatches on:
    # `tuple[int, int] | None` is a union with a sequence variant there, so it consumes
    # greedily and owes nothing (BUG-58).
    if (fixed := _fixed_seq_types(resolved)) is not None and flag in flat:
        # A greedy registration keeps only the surviving occurrence's run, so the
        # bounds are asked of every occurrence's run, read off argv; a parse result
        # argv cannot account for falls back to the run the framework handed over.
        runs = _fixed_arity_occurrence_runs(argv, flag)
        for run in runs or [flat[flag]]:
            _require_fixed_arity(len(fixed), run, flag, core)

    if _is_namedtuple(core):
        _collect_ns_namedtuple(flat, core, flag, union_tag, result, tags, argv)
        return

    if _is_registered_leaf(core):
        # A registered leaf is opaque to implicit decisions, but a tag inside a whole
        # value still opens it -- and the tag can only be seen once the token is
        # decoded, so the blob is honored before the scalar coercion, as in vanilla.
        if whole is not _NO_CAST:
            _set_nested(result, flag.split("."), whole)
        elif flag in flat:
            _set_nested(result, flag.split("."), _coerce_leaf_value(core, flat[flag]))
        # The flat spelling of the same hatch (BUG-56): the tag selector and the
        # leaf's __init__-parameter flags sit beside the scalar, collected by the
        # same struct-shaped walk vanilla's type walk performs. The tag is written
        # back as a raw string, not resolved, for the BUG-45 reason: construct()
        # raises the import error naming the bad path.
        tag_key = f"{flag}.{union_tag}"
        if tag_key in flat:
            _set_nested(result, [*flag.split("."), union_tag], _str_token(flat[tag_key]))
        _collect_ns_fields(flat, core, flag, union_tag, result, tags, argv)
        return

    if _is_struct(core):
        if whole is not _NO_CAST:
            _set_nested(result, flag.split("."), whole)
        elif flag in flat:
            # A token no blob decoded is the one vanilla's own _consume_value
            # leaves behind: stored raw, for build() to refuse loudly as it does
            # for the dict field -- dropping it silently built the field's
            # default instead (BUG-82).
            _set_nested(result, flag.split("."), _str_token(flat[flag]))
        _collect_ns_fields(flat, core, flag, union_tag, result, tags, argv)
        return

    if _is_dict(core):
        # Keys are collected by the argv patch scan and deep-merged over this value.
        if whole is not _NO_CAST:
            _set_nested(result, flag.split("."), whole)
        elif flag in flat:
            _set_nested(result, flag.split("."), _coerce_leaf_value(core, flat[flag]))
        return

    if _is_callable(core):
        _collect_callable_spec(flat, flag, result, whole)
        return

    cast_val = _find_scalar_cast_override(flat, flag)
    if cast_val is not _NO_CAST:
        _set_nested(result, flag.split("."), cast_val)
    elif flag in flat:
        # The one accumulation site for a varlen collection's tokens: the only flat
        # value a whole-field delete can span.
        v = _tokens_past_whole_field_delete(argv, flag, flat[flag])
        _set_nested(result, flag.split("."), _coerce_leaf_value(core, v))


def _promote_patched_lists(ops: Mapping[str, Any], collected: dict[str, Any]) -> None:
    """Promote every collected plain list an op dict addresses into its ``'*'`` base.

    The list-op half of the channel split: vanilla stores a plain occurrence and the
    patch after it in one ``ctx.data``, where its own descent
    (:func:`~confarg._merge._set_nested`, ``_accumulate_list_delete``,
    ``_merge_append_ops``) promotes the stored list into the ``'*'`` base and records
    the op beside it, for ``build()`` to apply.  The adapters deep-merge the scan's ops
    over the collected values, and ``_deep_merge`` applies list ops on sight -- right
    for its usual job of joining two priorities, wrong within one channel -- so the
    collected lists the ops address are promoted into the recorded shape first, and
    the merge that follows only lays the op keys beside the base.

    Args:
        ops: The patch scan's op tree, read but never modified.
        collected: The flat collector's dict, promoted in place.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#a-patch-op-records-against-a-list-the-channel-collected
    """
    for key, val in ops.items():
        if not isinstance(val, dict):
            continue
        node = collected.get(key)
        if isinstance(node, list):
            collected[key] = {LIST_REPLACE_BASE_KEY: node}
        elif isinstance(node, dict):
            _promote_patched_lists(val, node)


def _restore_patch_deletes(ops: dict[str, Any], result: dict[str, Any]) -> None:
    """Put back every key delete *ops* recorded that the merge into *result* consumed.

    Within one channel a ``--<field>.<key>-`` flag is a *record*, not an operation: the
    vanilla loop stores the sentinel and leaves ``_merge_sources`` to apply it against the
    lower-priority sources.  The adapters reach the same dict by deep-merging the patch
    scan's ops over the flat collector's values, and :func:`~confarg._merge._deep_merge`
    applies a delete instead of storing it, because its usual job is to join two different
    priorities.  Re-asserting the sentinels afterwards is what makes the two halves add up
    to one channel again.

    Only dict-key deletes carry a sentinel; list index deletes travel as index lists under
    ``"-"``/``"~"`` and are applied by the merge, exactly as vanilla applies them.

    Dev Notes:
        docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity
    """
    for key, val in ops.items():
        if isinstance(val, _DeleteSentinel):
            result[key] = val
        elif isinstance(val, dict) and isinstance(node := result.get(key), dict):
            _restore_patch_deletes(val, node)


def _bare_multi_token_flags(argv: Sequence[str], target: object, union_tag: str) -> list[str]:
    """Return the flag names in *argv* standing bare on a path whose flag takes many tokens.

    A multi-token flag consumes greedily and is content with no token at all, so
    ``--users`` with nothing after it is a legal command that *clears* the collection.
    No clicklike option can express "zero or more", so those occurrences are dropped from
    the argv the framework parses (:func:`~confarg.cli._argv.drop_bare_occurrences`) and
    the clear reaches no parse result; it is read back here instead, from the argv the
    user typed.  A patch path (``map.k``, ``grid.0``) answers the predicate too and is
    returned with the rest: the flat collector walks declared fields and passes it by, and
    the patch scan has already read it off the same argv, so the entry is inert -- and it
    matches what argparse, which parses the argv as typed, collected for itself.

    The gate is :func:`~confarg.cli._build._takes_multi_tokens`, the same predicate the specs
    set ``stands_bare`` from, so a field that would report ``Missing value`` in vanilla is
    left for the framework to reject here.  It is the multi-token *shape*, not "is there
    something to clear": a union with a sequence variant but no varlen one
    (``str | tuple[str, str]``) is included on purpose, since the empty value it stores is
    what raises vanilla's error, in :func:`_collect_union_seq_value`.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """
    names: list[str] = []
    for name in sorted(bare_only_flag_names(argv)):
        ft = _resolve_field_type(target, name.split("."), union_tag)
        if ft is not None and _takes_multi_tokens(ft):
            names.append(name)
    return names


def _merge_from_flat(  # noqa: PLR0913  # mirrors confarg.merge's keyword-only signature
    flat: dict[str, Any],
    target: object,
    *,
    argv: Sequence[str] | None,
    env: Mapping[str, str] | None,
    env_prefix: str | None,
    env_separator: str,
    cli_prefix: str,
    config_flag: str,
    files: Sequence[str | Path],
    env_config: str | None,
    union_tag: str,
) -> dict[str, Any]:
    """Merge every source into a raw dict, starting from an adapter's flat parse result.

    The shared tail of ``merge_namespace`` / ``merge_context`` / ``merge_app``: each
    adapter flattens its framework's parse result to ``{dotted.flag: value}`` and hands
    it here, so the three cannot drift.  Patch ops and ``--config`` ordering are read
    from *argv* rather than from *flat*, because a framework's parse result carries no
    command-line order.

    Args:
        flat: The adapter's parse result as ``{dotted.flag: value}``.
        target: The target type, used to guide the type walk.
        argv: CLI arguments to rescan for patch ops and config-file order.
            ``None`` means ``sys.argv[1:]``.
        env: Environment variable mapping; ``None`` means ``os.environ``.
        env_prefix: Prefix that env vars must start with.
        env_separator: Separator splitting env var names into nested keys.
        cli_prefix: Namespace the flags were registered under; stripped from both
            *flat* and *argv* so everything downstream stays prefix-blind.
        config_flag: Flag name used to specify config files.
        files: Config file paths to load at lowest priority.
        env_config: Name of an env var holding a config file path.
        union_tag: Field name used as a discriminator tag in unions.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#the-quartet
    """
    if env is None:
        env = os.environ

    # Strip the prefix at both inputs, so the type walk and the argv rescan below
    # resolve paths against *target* alone
    # (docs-dev/architecture/cli-parsing/cli-prefix.md#cli_prefix).
    flat = strip_flat_prefix(flat, cli_prefix)

    # Patch ops, --config order and the class tags are read from argv, not the framework's
    # parse result (docs-dev/architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity).
    argv_ = sys.argv[1:] if argv is None else list(argv)
    argv_ = strip_argv_prefix(argv_, cli_prefix)

    # The same scan registration uses, so a tag a --config file sets steers the type walk
    # here exactly as it steers vanilla's
    # (docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags).
    tags = collect_tags(argv_, target, union_tag=union_tag, config_flag=config_flag)

    # A bare multi-token occurrence never reaches the framework's parse result, so the
    # empty value it stores is put back where the flag's own value would have been -- and
    # only there: an occurrence that did carry items already holds them
    # (docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare).
    for name in _bare_multi_token_flags(argv_, target, union_tag):
        flat.setdefault(name, [])

    cli_data: dict[str, Any] = {}
    _collect_ns_fields(flat, target, prefix="", union_tag=union_tag, result=cli_data, tags=tags, argv=argv_)

    # cli_data goes in as the patch base: a bare callable shorthand collected above is the
    # spec a delete flag refines, and the scan opens it before this merge lands on it
    # (docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags).
    patch_ops = _collect_cli_patch_ops(argv_, target, config_flag, union_tag, cli_data)
    # A collected list the ops address is their recorded base, not the list they apply
    # to (BUG-67), exactly as the deletes below are re-asserted as records.
    _promote_patched_lists(patch_ops, cli_data)
    cli_data = _deep_merge(cli_data, patch_ops)
    _restore_patch_deletes(patch_ops, cli_data)
    apply_root_json(flat, target, union_tag, cli_data)  # fold root `--json` under collected fields
    cli_configs = _collect_config_file_pairs(argv_, config_flag, target, union_tag) if config_flag else []

    return _merge_sources(
        target,
        cli_data,
        cli_configs,
        env=env,
        env_prefix=env_prefix,
        env_separator=env_separator,
        config_flag=config_flag,
        files=files,
        env_config=env_config,
        union_tag=union_tag,
    )


def _construct_from_merged(target: object, merged: dict[str, Any], union_tag: str) -> Any:
    """Construct *target* from an already-merged dict; the shared tail of every ``from_*``."""
    return build(target, merged, union_tag=union_tag)
