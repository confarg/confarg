# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Expression resolution for ${...} field references and computations.

Dev Notes:
    docs-dev/architecture/expressions/README.md
"""

from __future__ import annotations

import ast
import copy
import io
import keyword
import math
import operator
import re
import tokenize
import unicodedata
from collections import deque
from functools import lru_cache
from typing import TYPE_CHECKING, Any, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

from confarg.exceptions import (
    CircularReferenceError,
    ExpressionEvalError,
    MissingReferenceError,
    UnsafeExpressionError,
)

#: A position in the data, one segment per key or list index. Segments are never joined
#: into a dotted string, which a key holding a dot (``example.com``) would make ambiguous.
_Path = tuple[str, ...]

#: A Python string literal, triple-quoted or not. A backslash escapes the next
#: character whatever the prefix (``r'\''`` is one literal), so a prefix never moves
#: where a literal ends, which is all delimiting needs to know.
_STRING_LITERAL_RE = re.compile(r"""('''|\"\"\"|'|")(?:\\.|(?!\1)[^\\])*\1""", re.DOTALL)

#: The characters that can close an expression body or hide a brace from it.
_BODY_DELIMITER_RE = re.compile(r"""[{}'"]""")


class _ExpressionSpan(NamedTuple):
    """One ``${...}`` found in a string, or a ``$${...}`` escape of one."""

    start: int
    end: int
    #: The text between the braces; ``None`` for an escape, which is never evaluated.
    body: str | None


def _body_end(text: str, start: int) -> int | None:
    """Index of the ``}`` closing the expression body that begins at *start*.

    That is the first ``}`` outside a string literal and outside a brace pair the body
    opened itself, as for an f-string replacement field. ``None`` when nothing closes
    the body, including when a string literal in it is never closed.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#delimiting-an-expression
    """
    depth = 0
    index = start
    while (delimiter := _BODY_DELIMITER_RE.search(text, index)) is not None:
        char = delimiter.group()
        index = delimiter.end()
        if char == "{":
            depth += 1
        elif char == "}":
            if not depth:
                return delimiter.start()
            depth -= 1
        else:
            literal = _STRING_LITERAL_RE.match(text, delimiter.start())
            if literal is None:
                return None
            index = literal.end()
    return None


def _find_expressions(text: str) -> Iterator[_ExpressionSpan]:
    """Yield each ``${...}`` and ``$${...}`` escape of *text*, left to right.

    An escape is delimited exactly like the expression it spells, and a ``${`` whose
    body is empty or never closed is plain text.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#delimiting-an-expression
    """
    search = 0
    while (opening := text.find("${", search)) != -1:
        end = _body_end(text, opening + 2)
        escaped = opening > 0 and text[opening - 1] == "$"
        if end is None or (end == opening + 2 and not escaped):
            search = opening + 1
            continue
        if escaped:
            yield _ExpressionSpan(opening - 1, end + 1, None)
        else:
            yield _ExpressionSpan(opening, end + 1, text[opening + 2 : end])
        search = end + 1


def contains_expression(value: object) -> bool:
    """Return ``True`` when expression resolution would rewrite *value*.

    Matches both a real ``${...}`` and an escaped ``$${...}`` (which resolution
    unescapes to a literal ``${...}``). Every check that inspects a value before
    ``build()`` must use this predicate to leave such values untouched.

    Dev Notes:
        docs-dev/architecture/expressions/deferral-rule.md#deferral-rule
    """
    return isinstance(value, str) and next(_find_expressions(value), None) is not None


# Whitelisted free functions
_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "len": len,
}

# Whitelisted string methods
_SAFE_METHODS: set[str] = {
    "upper",
    "lower",
    "strip",
    "split",
    "replace",
    "startswith",
    "endswith",
    "join",
}

# Allowed AST node types
_ALLOWED_NODES: set[type] = {
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.Call,
    ast.IfExp,
    ast.Load,
    # Operator nodes
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
}

# Binary operator dispatch
_BINOP_MAP: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Unary operator dispatch
_UNARYOP_MAP: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

# Comparison operator dispatch
_CMPOP_MAP: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _parse_body(body: str) -> ast.Expression:
    """Parse the text of one ``${...}`` as a Python expression.

    Whitespace around the body is layout, as in an f-string replacement field and for
    :func:`eval`, so ``${ a }`` means ``${a}``; :func:`ast.parse` alone would read the
    leading blank as an indent.
    """
    return ast.parse(body.strip(), mode="eval")


@lru_cache(maxsize=2048)
def _parse_expression(content: str) -> ast.Expression:
    """Parse one ``${...}`` body, as written, into a cached AST.

    Every parse site in resolution — reference extraction, validation and evaluation —
    goes through here, so a unique expression is parsed however many times it appears
    but at most once, and is the only place anchor markers are swapped for the stand-in
    names that let them parse (:func:`_name_anchor`). The text anywhere else is the text
    the user wrote, so a message quoting it never shows a stand-in. Once parsed, each
    stand-in's id becomes a :class:`_StandIn`, which no name the body writes is. A name
    Python would read as another is refused here too (:func:`_refuse_normalized_names`),
    so no parse site reads ``ﬁle`` as ``file``.

    A stand-in parses and so caches like anything else; what it *denotes* differs per
    node, which is why :func:`_parse_anchored` rewrites the tree on the way out rather
    than the text on the way in.

    Dev Notes:
        docs-dev/architecture/expressions/resolution.md#resolution-algorithm
    """
    named, stand_ins = _name_anchor(content)
    tree = _parse_body(named)
    _refuse_normalized_names(named)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in stand_ins:
            node.id = _StandIn(_marker_text(stand_ins[node.id]))
    return tree


class _NormalizedNameError(SyntaxError):
    """A name the body writes that Python reads as another, refused as a body that does not parse."""

    def __init__(self, written: str) -> None:
        self.written = written
        self.read = unicodedata.normalize("NFKC", written)
        super().__init__(f"name {written!r} reads as {self.read!r}")


def _reads_as_written(name: str) -> bool:
    """Return ``True`` when Python reads the identifier *name* as itself.

    Python NFKC-normalizes every identifier it parses (PEP 3131), so ``ﬁle`` is the name
    ``file``; a string is never normalized. The one answer for both directions: a body
    writing such a name is refused (:func:`_refuse_normalized_names`), and a path segment
    is never spelled as one (:func:`_spells_as_name`).

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    return unicodedata.is_normalized("NFKC", name)


def _refuse_normalized_names(body: str) -> None:
    """Raise :class:`_NormalizedNameError` for the first name *body* writes that Python reads as another.

    Each name is checked as the tokenizer sees it, before normalization, which the tree no
    longer shows. Being a :class:`SyntaxError`, the refusal is a body that does not parse to
    every parse site: reference extraction skips it, mounting leaves it as written, and
    validation reports it, pointing at the subscript, the spelling that reads a key as written.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    for ttype, tstr, _, _ in _significant_tokens(body.strip()):
        if ttype == tokenize.NAME and not _reads_as_written(tstr):
            raise _NormalizedNameError(tstr)


def resolve_expressions(
    data: dict[str, Any],
) -> dict[str, Any]:
    """Resolve ${...} expressions in a merged config dict.

    Args:
        data: The merged configuration dict.

    Returns:
        A new dict with all ${...} expression strings replaced by their values.
        Returns data unchanged if no expressions are found.

    Raises:
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    # 1. Scan for expressions
    expr_fields = _scan_expressions(data)
    if not expr_fields:
        return data

    data = copy.deepcopy(data)

    # 2. Extract references and build dependency graph
    deps = _dependency_graph(data, expr_fields)

    # 3. Topological sort
    order = _topological_sort(deps)

    # 4. Validate AST for all expressions
    for path in order:
        for span in _find_expressions(expr_fields[path]):
            if span.body is not None:  # not escaped
                _validate_ast(span.body)

    # 5. Resolve in order, building namespace incrementally
    for path in order:
        raw_str = expr_fields[path]
        result = _resolve_single(raw_str, data, path)
        _set_nested_by_path(data, path, result)

    return data


def _scan_expressions(data: dict[str, Any]) -> dict[_Path, str]:
    """Walk merged dict, find string values containing ${...}.

    Returns:
        Dict mapping each expression's position, one segment per key or list index, to its
        raw string: ``{"a.b": "${x}"}`` is at ``("a.b",)``, ``{"a": {"b": "${x}"}}`` at
        ``("a", "b")``.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-position-is-a-sequence-of-segments
    """
    result: dict[_Path, str] = {}
    for key, value in data.items():
        _collect_expressions(value, (key,), result)
    return result


def _collect_expressions(value: Any, path: _Path, out: dict[_Path, str]) -> None:
    """Recursively collect expression strings from a value into *out*."""
    if isinstance(value, dict):
        for k, v in value.items():
            _collect_expressions(v, (*path, k), out)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _collect_expressions(item, (*path, str(i)), out)
    elif contains_expression(value):
        out[path] = value


def _dependency_graph(data: dict[str, Any], expr_fields: dict[_Path, str]) -> dict[_Path, set[_Path]]:
    """Map each expression's path to the paths of the expressions it reads, which resolve first.

    A reference reads every expression its path reaches, not just one sitting exactly there:
    any below it, since ``${svc}`` hands on or stringifies the whole subtree, and one above
    it, since ``${a.b.c}`` reads into what ``a.b`` resolves to. A reference to an ancestor
    of the expression that makes it therefore reads that expression itself, the cycle it is;
    the root, ``()``, is an ancestor of every expression. The reference is first named as
    the scan names it (:func:`_scan_path`), so ``xs[-1]`` reaches the element the scan calls
    ``xs.1``.

    Dev Notes:
        docs-dev/architecture/expressions/resolution.md#a-reference-reads-everything-its-path-reaches
    """
    below: dict[_Path, list[_Path]] = {}
    for path in expr_fields:
        for depth in range(len(path) + 1):
            below.setdefault(path[:depth], []).append(path)
    deps: dict[_Path, set[_Path]] = {}
    for path, raw_str in expr_fields.items():
        read: set[_Path] = set()
        for ref in _extract_references(raw_str, path):
            segments = _scan_path(data, ref)
            read.update(below.get(segments, ()))
            read.update(segments[:depth] for depth in range(1, len(segments)) if segments[:depth] in expr_fields)
        deps[path] = read
    return deps


def _scan_path(data: dict[str, Any], parts: Sequence[str]) -> _Path:
    """Return the path *parts* reads in *data*, named as :func:`_scan_expressions` names it.

    Each segment is taken by :func:`_step`, the walk evaluation reads the value with, so the
    name is that of the node evaluation will reach: ``xs[-1]`` is ``xs.1`` in a two-item list.
    From the first segment *data* does not answer on — a missing key, or one inside an
    expression's value, unknown until it resolves — the path is kept as written.
    """
    named: list[str] = []
    current: Any = data
    for depth, part in enumerate(parts):
        try:
            segment, current = _step(current, part, parts)
        except MissingReferenceError:
            return (*named, *parts[depth:])
        named.append(segment)
    return tuple(named)


def _extract_references(expr_str: str, node_path: _Path = ()) -> set[_Path]:
    """Extract the field paths referenced in expression string, one segment per key or index.

    *node_path* is where the expression sits, which is what an anchor stand-in is
    resolved against, so the paths returned are absolute either way. A path is kept as
    spelled: naming it as the data does is :func:`_scan_path`'s business.

    Returns:
        Set of paths (e.g. ``{("db", "host"), ("db", "port")}``).
    """
    refs: set[_Path] = set()
    for span in _find_expressions(expr_str):
        if span.body is None:
            continue  # escaped $${...}
        try:
            tree = _parse_anchored(span.body, node_path)
        except SyntaxError:
            continue
        _collect_names(tree, refs)
    return refs


def _function_name(node: ast.Call) -> str | None:
    """Return the name of the free function *node* calls, or ``None`` for any other callee.

    The one place a name is read as a function: the callee of a call. Anywhere else — an
    operand, an argument, a method receiver, the base of a dotted path — a name is a config
    key, even one spelled like a whitelisted function, so ``${max}`` reads the key ``max``
    and ``${max(max, 5)}`` calls the builtin on it. The rule is syntactic, so the
    mount-time prefixer applies it without seeing the data.

    Dev Notes:
        docs-dev/architecture/expressions/safety-model.md#a-function-is-named-only-by-a-call
    """
    return node.func.id if isinstance(node.func, ast.Name) else None


def _method_name(node: ast.Call) -> str | None:
    """Return the name of the method *node* calls, or ``None`` when its callee is no attribute.

    The one place a call is read as a method call: ``<receiver>.<name>(...)``. Its callee is
    never a config path, so ``x.upper()`` reads ``x`` and calls ``upper`` on it, even when
    ``x`` holds a key ``upper``; validation checks the name, evaluation the receiver.

    Dev Notes:
        docs-dev/architecture/expressions/safety-model.md#a-method-is-a-string-method
    """
    return node.func.attr if isinstance(node.func, ast.Attribute) else None


def _collect_names_from_call(node: ast.Call, refs: set[tuple[str, ...]]) -> None:
    """Collect field references from a Call node: its arguments, and its callee unless that names a function.

    A method call depends on its receiver, never on the path its callee spells.
    """
    if _method_name(node) is not None:
        _collect_names(cast("ast.Attribute", node.func).value, refs)
    elif _function_name(node) is None:
        _collect_names(node.func, refs)
    for arg in node.args:
        _collect_names(arg, refs)
    for kw in node.keywords:
        _collect_names(kw.value, refs)


def _collect_names(node: ast.AST, refs: set[tuple[str, ...]]) -> None:
    """Collect Name nodes and the config paths of Attribute/Subscript chains as field references.

    A stand-in :class:`_AnchorResolver` left in the tree names the configuration root, the
    empty path.
    """
    if isinstance(node, ast.Name):
        refs.add(() if _anchor_dot_count(node.id) is not None else (node.id,))
        return
    if isinstance(node, ast.Attribute | ast.Subscript):
        parts = _attribute_chain(node)
        if parts is not None:
            refs.add(tuple(parts))
        else:
            for child in ast.iter_child_nodes(node):
                _collect_names(child, refs)
        return
    if isinstance(node, ast.Call):
        _collect_names_from_call(node, refs)
        return
    for child in ast.iter_child_nodes(node):
        _collect_names(child, refs)


def _ast_int_value(node: ast.AST) -> int | None:
    """Return the integer value of an AST node if it is an int literal or -int literal (a bool is neither)."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and type(node.operand.value) is int
    ):
        return -node.operand.value
    return None


def _key_segment(key: object) -> str | None:
    """Return the path segment the subscript key *key* spells, or ``None`` when it spells none.

    A string is the key itself (``'web-1'``), an integer the list index (``0``, ``-1``); a
    bool, a float or any other key is no segment. Asked of a constant key by
    :func:`_subscript_segment` and of an evaluated one by :func:`_segment`, so ``svc[k]``
    spells the segment ``svc['web']`` does once ``k`` is ``'web'``.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    return str(key) if isinstance(key, str) or type(key) is int else None


def _subscript_segment(index: ast.expr) -> str | None:
    """Return the path segment a subscript's *index* spells, or ``None`` for a computed one.

    A string constant is the key itself (``['web-1']``), an integer constant the list index
    (``[0]``, ``[-1]``).
    """
    return _key_segment(index.value if isinstance(index, ast.Constant) else _ast_int_value(index))


def _segment(node: ast.Attribute | ast.Subscript, namespace: dict[str, Any] | None = None) -> str | None:
    """Return the one path segment *node* adds to its base, or ``None`` when it spells none.

    A dot's name, or what :func:`_subscript_segment` reads in a subscript's index. A computed
    index spells no segment, unless *namespace* is given: it is then evaluated against it and
    spells what :func:`_key_segment` reads in its value. Asked of each link by
    :func:`_attribute_chain`, and of the first segment after a root stand-in by
    :class:`_AnchorResolver`.
    """
    if isinstance(node, ast.Attribute):
        return node.attr
    segment = _subscript_segment(node.slice)
    if segment is None and namespace is not None:
        return _key_segment(_evaluate_ast(node.slice, namespace))
    return segment


def _attribute_chain(node: ast.Attribute | ast.Subscript, namespace: dict[str, Any] | None = None) -> list[str] | None:
    """Return the config path *node* reads, segment by segment, or ``None`` when it reads none.

    The one answer to "which config path does this node read?": a dot and a constant
    subscript each spell one segment, so ``db.host``, ``db['host']`` and ``db["host"]`` are
    ``["db", "host"]``, ``servers[0].host`` is ``["servers", "0", "host"]`` and
    ``svc['web-1']`` is ``["svc", "web-1"]``. ``None`` when the chain is not rooted at a name
    (``f(x).a``), or when a subscript is computed (``svc[k]``) and no *namespace* is given.
    Reference collection asks it of the syntax alone; evaluation passes its *namespace*, so
    a computed key spells the segment its value does (``["svc", "web"]`` once ``k`` is
    ``'web'``), and ``None`` only when that value is no segment.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute | ast.Subscript):
        segment = _segment(current, namespace)
        if segment is None:
            return None
        parts.append(segment)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    parts.reverse()
    return parts


def _topological_sort(deps: dict[_Path, set[_Path]]) -> list[_Path]:
    """Kahn's algorithm. Raises CircularReferenceError on cycles.

    Linear in the graph size (``V + E``): a reverse adjacency list records, for
    each node, who depends on it, so releasing a node touches only its direct
    dependents rather than rescanning the whole graph.
    """
    if not deps:
        return []

    in_degree: dict[_Path, int] = dict.fromkeys(deps, 0)
    dependents: dict[_Path, list[_Path]] = {node: [] for node in deps}
    for node, node_deps in deps.items():
        for dep in node_deps:
            if dep in deps:
                in_degree[node] += 1
                dependents[dep].append(node)

    queue: deque[_Path] = deque(node for node, degree in in_degree.items() if degree == 0)
    order: list[_Path] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in dependents[node]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(deps):
        remaining = set(deps.keys()) - set(order)
        msg = f"Circular reference detected among: {', '.join(sorted('.'.join(path) for path in remaining))}"
        raise CircularReferenceError(msg)

    return order


def _validate_ast(expr_str: str) -> None:
    """Parse expression and validate AST contains only allowed nodes.

    Raises UnsafeExpressionError for disallowed constructs.
    """
    try:
        tree = _parse_expression(expr_str)
    except _NormalizedNameError as exc:
        msg = (
            f"Name {exc.written!r} reads as {exc.read!r} in expression {expr_str!r}, as Python normalizes"
            f" names (NFKC): write {exc.read!r}, or read the key as written with a subscript,"
            f" [{exc.written!r}] or ::[{exc.written!r}] at the root"
        )
        raise UnsafeExpressionError(msg) from exc
    except SyntaxError as exc:
        msg = f"Invalid expression syntax: {expr_str!r}"
        raise UnsafeExpressionError(msg) from exc

    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            msg = f"Disallowed construct in expression: {type(node).__name__}"
            raise UnsafeExpressionError(msg)
        # Check for dunder attribute access
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            msg = f"Access to dunder attribute '{node.attr}' is not allowed"
            raise UnsafeExpressionError(msg)
        # Check function calls are whitelisted
        if isinstance(node, ast.Call):
            _validate_call(node)


def _validate_call(node: ast.Call) -> None:
    """Validate that a Call node targets a whitelisted function/method."""
    function = _function_name(node)
    if function is not None:
        if function not in _SAFE_FUNCTIONS:
            msg = f"Function '{function}' is not allowed"
            raise UnsafeExpressionError(msg)
    elif (method := _method_name(node)) is not None:
        if method not in _SAFE_METHODS:
            msg = f"Method '{method}' is not allowed"
            raise UnsafeExpressionError(msg)
    else:
        raise UnsafeExpressionError.indirect_call()


def _eval_name(node: ast.Name, namespace: dict[str, Any]) -> Any:
    """Read the config key *node* names; a callee never reaches here (see :func:`_function_name`)."""
    if node.id in _SAFE_FUNCTIONS and node.id not in namespace:
        raise MissingReferenceError.uncalled(node.id, "function", node.id, node.id)
    return _get_nested(namespace, [node.id])


def _eval_path_or(node: ast.Attribute | ast.Subscript, namespace: dict[str, Any]) -> Any:
    """Read the config path *node* spells; failing that, index its evaluated base by the key it spells.

    The path comes first, so ``svc['web'].host`` reads what ``svc.web.host`` reads, and a
    computed key spells its path once evaluated, so ``svc[k]`` reads what ``svc['web']``
    reads when ``k`` is ``'web'``. What no path answers is Python's own subscript: an index
    into a string (``name[0]``), a key that is no string (``m[0]`` on ``{0: ...}``), a key
    that spells no segment (``m[flag]``). A dot is that subscript with its name as the key,
    so ``svc[k].host`` reads what ``svc[k]['host']`` reads; it is never ``getattr``, so no
    attribute of a value — a bound method above all — is reachable. When the subscript fails
    too, the path's own miss is reported rather than a ``KeyError``, with how to call a
    string method a dot named.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
        docs-dev/architecture/expressions/safety-model.md#a-dot-reads-a-key-never-an-attribute
    """
    parts = _attribute_chain(node, namespace)
    missing: MissingReferenceError | None = None
    if parts is not None:
        try:
            return _get_nested(namespace, parts)
        except MissingReferenceError as exc:
            missing = exc
    try:
        base = _evaluate_ast(node.value, namespace)
        return base[node.attr if isinstance(node, ast.Attribute) else _evaluate_ast(node.slice, namespace)]
    except (AttributeError, LookupError, TypeError):
        if missing is None or parts is None:
            raise
        if isinstance(node, ast.Attribute) and node.attr in _SAFE_METHODS:
            path = ".".join(parts)
            raise MissingReferenceError.uncalled(path, "method", node.attr, ast.unparse(node)) from None
        raise missing from None


def _eval_binop(node: ast.BinOp, namespace: dict[str, Any]) -> Any:
    left = _evaluate_ast(node.left, namespace)
    right = _evaluate_ast(node.right, namespace)
    op_func = _BINOP_MAP.get(type(node.op))
    if op_func is None:
        msg = f"Unsupported binary operator: {type(node.op).__name__}"
        raise ExpressionEvalError(msg)
    try:
        return op_func(left, right)
    except Exception as exc:
        raise ExpressionEvalError(str(exc)) from exc


def _eval_unaryop(node: ast.UnaryOp, namespace: dict[str, Any]) -> Any:
    operand = _evaluate_ast(node.operand, namespace)
    op_func = _UNARYOP_MAP.get(type(node.op))
    if op_func is None:
        msg = f"Unsupported unary operator: {type(node.op).__name__}"
        raise ExpressionEvalError(msg)
    return op_func(operand)


def _eval_compare(node: ast.Compare, namespace: dict[str, Any]) -> Any:
    left = _evaluate_ast(node.left, namespace)
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        right = _evaluate_ast(comparator, namespace)
        op_func = _CMPOP_MAP.get(type(op))
        if op_func is None:
            msg = f"Unsupported comparison: {type(op).__name__}"
            raise ExpressionEvalError(msg)
        if not op_func(left, right):
            return False
        left = right
    return True


def _eval_boolop(node: ast.BoolOp, namespace: dict[str, Any]) -> Any:
    if isinstance(node.op, ast.And):
        result: Any = True
        for value in node.values:
            result = _evaluate_ast(value, namespace)
            if not result:
                return result
        return result
    # ast.Or
    result = False
    for value in node.values:
        result = _evaluate_ast(value, namespace)
        if result:
            return result
    return result


def _eval_ifexp(node: ast.IfExp, namespace: dict[str, Any]) -> Any:
    if _evaluate_ast(node.test, namespace):
        return _evaluate_ast(node.body, namespace)
    return _evaluate_ast(node.orelse, namespace)


def _eval_method(node: ast.Call, method: str, namespace: dict[str, Any]) -> Any:
    """Return the bound string method *node* calls, refusing any receiver that is no string.

    The receiver is evaluated, never the callee's path, and its type is known only now: a
    date's ``replace`` or a dict holding a key ``upper`` is refused here, as unsafe.

    Dev Notes:
        docs-dev/architecture/expressions/safety-model.md#a-method-is-a-string-method
    """
    receiver = _evaluate_ast(cast("ast.Attribute", node.func).value, namespace)
    if not isinstance(receiver, str):
        msg = f"Method '{method}' is called on a {type(receiver).__name__}; it is allowed only on a string"
        raise UnsafeExpressionError(msg)
    return getattr(receiver, method)


def _eval_call(node: ast.Call, namespace: dict[str, Any]) -> Any:
    if (function := _function_name(node)) is not None:
        func = _SAFE_FUNCTIONS[function]
    elif (method := _method_name(node)) is not None:
        func = _eval_method(node, method, namespace)
    else:
        raise UnsafeExpressionError.indirect_call()
    args = [_evaluate_ast(a, namespace) for a in node.args]
    kwargs = {cast("str", kw.arg): _evaluate_ast(kw.value, namespace) for kw in node.keywords}
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        raise ExpressionEvalError(str(exc)) from exc


_AST_EVALUATORS: dict[type, Any] = {
    ast.Expression: lambda n, ns: _evaluate_ast(n.body, ns),
    ast.Constant: lambda n, _ns: n.value,
    ast.Name: _eval_name,
    ast.Attribute: _eval_path_or,
    ast.Subscript: _eval_path_or,
    ast.BinOp: _eval_binop,
    ast.UnaryOp: _eval_unaryop,
    ast.Compare: _eval_compare,
    ast.BoolOp: _eval_boolop,
    ast.IfExp: _eval_ifexp,
    ast.Call: _eval_call,
}


def _evaluate_ast(node: ast.AST, namespace: dict[str, Any]) -> Any:
    """Recursively evaluate AST node against namespace."""
    evaluator = _AST_EVALUATORS.get(type(node))
    if evaluator is None:
        msg = f"Cannot evaluate node type: {type(node).__name__}"
        raise ExpressionEvalError(msg)
    return evaluator(node, namespace)


def _eval_expr(tree: ast.Expression, namespace: dict[str, Any], context: str) -> Any:
    """Evaluate a parsed expression, wrapping an unexpected failure in ``ExpressionEvalError``.

    ``MissingReferenceError``, ``UnsafeExpressionError`` and an ``ExpressionEvalError`` the
    interpreter already raised propagate unchanged. Anything else — typically raised by a
    whitelisted function the expression called — becomes an ``ExpressionEvalError`` quoting
    *context*: the whole string for a pure expression, the ``${...}`` fragment alone for one
    embedded in an interpolation.
    """
    try:
        return _evaluate_ast(tree, namespace)
    # Load-bearing: without it the catch-all below would re-wrap the typed errors.
    except (MissingReferenceError, UnsafeExpressionError, ExpressionEvalError):
        raise
    except Exception as exc:
        msg = f"Error in expression {context!r}: {exc}"
        raise ExpressionEvalError(msg) from exc


def _resolve_single(expr_str: str, namespace: dict[str, Any], node_path: _Path = ()) -> Any:
    """Resolve a single expression string.

    Handles three cases:
    1. Pure ${expr} — typed result
    2. Interpolation (text around ${...}) — string result
    3. Escaped $${...} — literal ${...}

    *node_path* is where the expression sits, which is what an anchor marker
    (``.``, ``::``) is resolved against.
    """
    spans = list(_find_expressions(expr_str))
    # Check if the entire string is a single ${expr}
    if len(spans) == 1 and spans[0].body is not None and (spans[0].start, spans[0].end) == (0, len(expr_str)):
        # Pure expression — return typed result
        tree = _parse_anchored(spans[0].body, node_path)
        return _eval_expr(tree, namespace, expr_str)

    # Interpolation or escape mode: build string from parts
    result_parts: list[str] = []
    last_end = 0
    for span in spans:
        # Add literal text before this match
        result_parts.append(expr_str[last_end : span.start])

        if span.body is None:
            # Escaped $${...} — strip one $, producing the literal ${...}
            result_parts.append(expr_str[span.start + 1 : span.end])
        else:
            # Real expression — evaluate and stringify
            tree = _parse_anchored(span.body, node_path)
            value = _eval_expr(tree, namespace, expr_str[span.start : span.end])
            result_parts.append(str(value))

        last_end = span.end

    # Add any trailing literal text
    result_parts.append(expr_str[last_end:])
    return "".join(result_parts)


def _get_nested(data: dict[str, Any], parts: Sequence[str]) -> Any:
    """Retrieve the value at the path *parts* from a nested dict/list, one segment per key or index.

    Segments are taken as given, never re-split, so a key holding a dot (``['example.com']``)
    is one segment.
    """
    current: Any = data
    for part in parts:
        _, current = _step(current, part, parts)
    return current


def _list_index(segment: str) -> int | None:
    """Return the list index *segment* spells, or ``None`` when it spells none.

    Only the spelling ``str()`` gives an integer is an index — ``0``, ``1``, ``-1`` — so a
    string subscript ``['1']`` reads what the integer subscript ``[1]`` does, and nothing
    else :func:`int` happens to parse does: ``+1``, `` 1``, ``1_0``, ``01``, ``-0`` or a
    non-ASCII digit spell no index. The one answer for the walk (:func:`_step`) and for the
    spelling of a path (:func:`_segment_link`), which writes an index as the integer.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    try:
        index = int(segment)
    except ValueError:
        return None
    return index if str(index) == segment else None


def _step(node: Any, part: str, path: Sequence[str]) -> tuple[str, Any]:
    """Take the segment *part* of *path* down from *node*: return how the scan names it, and what it reaches.

    The one walk over the data: evaluation reads a value with it (:func:`_get_nested`) and
    the dependency graph names a reference with it (:func:`_scan_path`), so a reference can
    never depend on one node and read another. A dict key names itself; a list index is
    named by its position, as :func:`_collect_expressions` names an element, so ``-1`` of a
    two-item list is ``1``; only a segment :func:`_list_index` reads is one.

    Raises:
        MissingReferenceError: If *part* reaches nothing from *node*; the message names *path*.
    """
    if isinstance(node, dict):
        if part not in node:
            raise MissingReferenceError.field_not_found(".".join(path))
        return part, node[part]
    if isinstance(node, list | tuple):
        idx = _list_index(part)
        if idx is None:
            raise MissingReferenceError.field_not_found(".".join(path), f"'{part}' is not a valid index")
        if not -len(node) <= idx < len(node):
            raise MissingReferenceError.field_not_found(".".join(path), f"index {idx} out of range")
        position = idx + len(node) if idx < 0 else idx
        return str(position), node[position]
    raise MissingReferenceError.field_not_found(".".join(path), f"cannot traverse into {type(node).__name__}")


def _set_nested_by_path(data: dict[str, Any], path: _Path, value: Any) -> None:
    """Replace the value at *path*, a position :func:`_scan_expressions` named, by *value*.

    The container is reached by :func:`_get_nested`, the one walk over the data. The scan
    only descends into dicts and lists, so the container is one of the two, and a list
    element is named by its position.
    """
    container = _get_nested(data, path[:-1])
    container[path[-1] if isinstance(container, dict) else int(path[-1])] = value


# ---------------------------------------------------------------------------
# Reference anchoring
# ---------------------------------------------------------------------------

#: Adjacent colons that spell the configuration root.
_ROOT_MARKER_COLONS = 2

#: Layout tokens that carry no operand meaning when scanning for anchors.
_IGNORED_TOKENS = frozenset(
    {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER, tokenize.COMMENT},
)

#: Token kinds a marker may follow while still being ordinary attribute access.
_ANCHOR_BLOCKING_TYPES = frozenset({tokenize.NUMBER, tokenize.STRING})
_ANCHOR_BLOCKING_OPS = frozenset({")", "]", "}", "."})

#: Bracket pairs, tracked so a ``::`` inside a subscript stays a slice step.
_OPEN_BRACKETS = frozenset({"(", "[", "{"})
_CLOSE_BRACKETS = frozenset({")", "]", "}"})


def _marker_text(levels: int) -> str:
    """Spell the marker *levels* stands for: ``::`` at the root, else that many dots."""
    return "::" if levels == 0 else "." * levels


class _StandIn(str):
    """The id of a name standing for an anchor marker in a parsed tree, spelled as that marker.

    Told apart by its type, never by its text: a parsed body yields plain strings only, and
    so does a path segment, so neither a name the user writes (``__ROOT__``) nor a key
    spelled like a marker (``::['..']``) is ever read as an anchor.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#implementation-constraints
    """

    __slots__ = ()

    @property
    def levels(self) -> int:
        """How far the marker climbs: one per dot, and ``0`` for ``::``, the configuration root."""
        return 0 if self == _marker_text(0) else len(self)


#: The stand-in for the configuration root, which :func:`_path_to_ast` hangs a root key off.
_ROOT_ANCHOR = _StandIn(_marker_text(0))


def _anchor_dot_count(name: str) -> int | None:
    """Return the level count *name* anchors to, or ``None`` when it is no stand-in."""
    return name.levels if isinstance(name, _StandIn) else None


def _is_dot_run(text: str) -> bool:
    """Return ``True`` for a token made only of dots (``.``, or the ``...`` ellipsis)."""
    return set(text) == {"."}


def _is_colon(text: str) -> bool:
    """Return ``True`` for a single colon token."""
    return text == ":"


def _line_starts(text: str) -> list[int]:
    """Absolute offset at which each line of *text* begins."""
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _replace_spans(text: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply (start, end, replacement) edits to *text*, rightmost first."""
    for begin, finish, repl in sorted(edits, reverse=True):
        text = text[:begin] + repl + text[finish:]
    return text


def _significant_tokens(expr_content: str) -> list[tuple[int, str, int, int]]:
    """``(type, string, start, end)`` per token that carries operand meaning.

    Offsets are absolute within *expr_content*, which is what :func:`_replace_spans` edits.
    """
    starts = _line_starts(expr_content)
    return [
        (tok.type, tok.string, starts[tok.start[0] - 1] + tok.start[1], starts[tok.end[0] - 1] + tok.end[1])
        for tok in tokenize.generate_tokens(io.StringIO(expr_content).readline)
        if tok.type not in _IGNORED_TOKENS
    ]


def _run_end(toks: list[tuple[int, str, int, int]], start: int, matches: Callable[[str], bool]) -> tuple[int, int]:
    """Index just past, and end offset of, a run of adjacent *matches* tokens from *start*."""
    end = toks[start][3]
    index = start + 1
    while index < len(toks) and matches(toks[index][1]) and toks[index][2] == end:
        end = toks[index][3]
        index += 1
    return index, end


class _AnchorMarker(NamedTuple):
    """One anchor marker that begins an operand, as :func:`_anchor_markers` finds it."""

    offset: int
    length: int
    #: How far a dot run climbs — one per dot — and ``0`` for ``::``, the configuration root.
    levels: int
    #: Whether a name follows, and so spells the first segment after the marker (``.host``),
    #: rather than a subscript (``.['web-1']``) or nothing at all (``.``).
    before_name: bool


def _anchor_markers(expr_content: str) -> list[_AnchorMarker]:
    """Each anchor marker that begins an operand, and whether a name follows it.

    Token-based: the dots of ``1.5`` or ``','.join(x)`` are not markers, while the one
    in ``a if .b else c`` is. A ``::`` inside brackets is a slice step and not a marker,
    which keeps ``items[::2]`` spellable; reach the root there with ``items[(::step)]``.
    The one answer to "what follows this marker?": the stand-in that replaces it owns a
    dot only before a name (:func:`_name_anchor`), and only before a name can ``::`` be
    dropped (:func:`_strip_anchor`).

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    try:
        toks = _significant_tokens(expr_content)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []  # malformed: let ast.parse report it with its own message
    found: list[_AnchorMarker] = []
    brackets: list[str] = []
    prev_type: int | None = None
    prev_str = ""
    index = 0
    while index < len(toks):
        ttype, tstr, begin, _ = toks[index]
        # A keyword tokenizes as NAME but cannot own an attribute, so a marker
        # after `if`/`else`/`and`/... still starts a new operand.
        blocked = (
            prev_type in _ANCHOR_BLOCKING_TYPES
            or (prev_type == tokenize.NAME and not keyword.iskeyword(prev_str))
            or (prev_type == tokenize.OP and prev_str in _ANCHOR_BLOCKING_OPS)
        )
        if ttype == tokenize.OP and tstr in _OPEN_BRACKETS:
            brackets.append(tstr)
        elif ttype == tokenize.OP and tstr in _CLOSE_BRACKETS and brackets:
            brackets.pop()
        dots = ttype == tokenize.OP and _is_dot_run(tstr)
        # Only a subscript can hold a slice, and parentheses inside one open a fresh
        # operand context — which is what makes `items[(::step)]` reach the root.
        colons = ttype == tokenize.OP and _is_colon(tstr) and (not brackets or brackets[-1] != "[")
        if blocked or not (dots or colons):
            prev_type, prev_str = ttype, tstr
            index += 1
            continue
        index, end = _run_end(toks, index, _is_dot_run if dots else _is_colon)
        run = expr_content[begin:end]
        # A keyword cannot be an attribute, so `. if c else d` names the node itself.
        before_name = index < len(toks) and toks[index][0] == tokenize.NAME and not keyword.iskeyword(toks[index][1])
        if dots:
            found.append(_AnchorMarker(begin, end - begin, len(run), before_name))
        elif len(run) == _ROOT_MARKER_COLONS:
            found.append(_AnchorMarker(begin, end - begin, 0, before_name))
        prev_type, prev_str = tokenize.OP, run[-1]
    return found


def _spells_as_name(segment: str) -> bool:
    """Return ``True`` when *segment* can be written as a name, ``.segment`` or a base ``segment``.

    It must parse back as itself: an identifier that is no keyword (``import``) and that
    Python reads as written (:func:`_reads_as_written`: ``ﬁle`` would read ``file``, and is
    refused). A dunder is excluded too, because validation refuses it after a dot.
    """
    return (
        segment.isidentifier()
        and not keyword.iskeyword(segment)
        and not segment.startswith("__")
        and _reads_as_written(segment)
    )


def _segment_link(base: ast.expr, segment: str) -> ast.Attribute | ast.Subscript:
    """Read *segment* off *base*: a dot when it spells as a name, else a constant subscript.

    A segment that spells a list index (``0``, ``-1``: :func:`_list_index`) is subscripted
    by the integer, the others by the string, so ``xs[0]`` and ``svc['web-1']`` read what
    ``xs.0`` and ``svc.web-1`` name, and a YAML integer key stays reachable when the path
    read misses.
    """
    if _spells_as_name(segment):
        return ast.Attribute(value=base, attr=segment, ctx=ast.Load())
    index = _list_index(segment)
    return ast.Subscript(value=base, slice=ast.Constant(segment if index is None else index), ctx=ast.Load())


def _path_to_ast(parts: Sequence[str]) -> ast.expr:
    """Build the tree that reads the path *parts*, and that unparses to source reading it too.

    The one spelling of a path as an expression: a segment is a dot or a constant
    subscript (:func:`_segment_link`), each one segment to :func:`_attribute_chain`. A first
    segment that spells as no name hangs off the root stand-in (``::['web-1'].p``), the only
    spelling of a root key that is no identifier, which :class:`_AnchorResolver` reads back.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    first, *rest = parts
    built: ast.expr = (
        ast.Name(id=first, ctx=ast.Load())
        if _spells_as_name(first)
        else _segment_link(ast.Name(id=_ROOT_ANCHOR, ctx=ast.Load()), first)
    )
    for part in rest:
        built = _segment_link(built, part)
    return built


def _strip_anchor(expr_content: str) -> str:
    """Rewrite configuration-root references as plain paths (``::foo.bar`` -> ``foo.bar``).

    Once every file is mounted the configuration root *is* the dict root, so dropping
    the marker is exactly what a root reference means there; this is
    :func:`canonicalize_references`' rewrite. Parsing needs none of it: a body is parsed
    as written, its markers named (:func:`_parse_expression`), which is how ``build()``
    and ``resolve()`` accept a ``::`` that never went through :func:`confarg.merge`.

    Node-relative markers are left alone: they mean nothing without the path of the
    node that wrote them. So is a root marker no name follows: no plain path reads a
    root key that is no identifier (``::['web-1']``), or the root itself.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path
    """
    return _replace_spans(
        expr_content,
        [
            (marker.offset, marker.offset + marker.length, "")
            for marker in _anchor_markers(expr_content)
            if marker.levels == 0 and marker.before_name
        ],
    )


def _stand_in_spelling(levels: int, pad: str) -> str:
    """Spell the stand-in for a marker climbing *levels* as a name, *pad* lengthening its underscores."""
    return f"__{pad}ROOT__" if levels == 0 else f"__{pad}UP{levels}__"


def _name_anchor(expr_content: str) -> tuple[str, dict[str, int]]:
    """Swap each anchor marker for a parseable name (``..foo`` -> ``__UP2__.foo``).

    Return the named text, and the level count each name it wrote stands for. The name is
    one the body spells nowhere: a body that writes ``__ROOT__`` has its root marker named
    ``___ROOT__``, so :func:`_parse_expression` tells each stand-in from a written name by
    its spelling alone. A name Python would read as a stand-in's (``__ROOT__`` in fullwidth letters) is refused
    by that same parse (:func:`_refuse_normalized_names`), so it needs no padding here.

    The stand-in owns a dot only when a name follows the marker: ``.[0]`` becomes
    ``__UP1__[0]`` and a bare ``.`` becomes ``__UP1__``, each a path to
    :func:`_attribute_chain`, as ``x[0]`` and ``x`` are.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#implementation-constraints
    """
    markers = _anchor_markers(expr_content)
    if not markers:
        return expr_content, {}
    written = {tstr for ttype, tstr, _, _ in _significant_tokens(expr_content) if ttype == tokenize.NAME}
    pad = ""
    while any(_stand_in_spelling(marker.levels, pad) in written for marker in markers):
        pad += "_"
    edits = [
        (
            marker.offset,
            marker.offset + marker.length,
            _stand_in_spelling(marker.levels, pad) + ("." if marker.before_name else ""),
        )
        for marker in markers
    ]
    return _replace_spans(expr_content, edits), {
        _stand_in_spelling(marker.levels, pad): marker.levels for marker in markers
    }


class _Unnamer(ast.NodeTransformer):
    """Fold a dot read off a stand-in into one name, the marker then the segment (``..host``).

    The marker carries its own dot, so the attribute's would be one too many: ``...host``.
    """

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:  # NodeTransformer dispatches on the class name
        """Spell ``<stand-in>.<attr>`` as the name ``<marker><attr>``, else recurse."""
        if isinstance(node.value, ast.Name) and _anchor_dot_count(node.value.id) is not None:
            return ast.copy_location(ast.Name(id=node.value.id + node.attr, ctx=node.ctx), node)
        return self.generic_visit(node)


def _unparse(tree: ast.AST) -> str:
    """Unparse *tree* as a ``${...}`` body, each stand-in written as the marker it stands for.

    A stand-in's text is its marker already (:class:`_StandIn`), so only the dot read off
    one is folded into it; *tree* itself is left as it is.
    """
    return ast.unparse(_Unnamer().visit(copy.deepcopy(tree)))


def _anchor_prefix(node_path: _Path, levels: int, scope: str = "document") -> _Path:
    """Path a run of *levels* dots stands for at *node_path*.

    One dot is the container holding the expression, so *levels* segments are dropped
    from the node's own path and the result is ``()`` at the root of *scope*.  A list
    index is an ordinary segment, the same path model :func:`_get_nested` uses, and so is
    a key holding a dot. The one answer to "does this run climb above the root?", for
    resolution and for the clamp a file is loaded under (:func:`check_anchor_depth`).

    Raises:
        MissingReferenceError: If the run climbs above the root of *scope*.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    if levels > len(node_path):
        raise MissingReferenceError.anchor_above_root(".".join(node_path), len(node_path), levels, scope)
    return node_path[: len(node_path) - levels]


def check_anchor_depth(value: str, node_path: _Path, scope: str = "file") -> None:
    """Raise if a relative reference in *value* climbs above the root of its scope.

    Called while a file is loaded, where *node_path* is the position within *that
    file*, one segment per key or list index: a fragment may look at itself with dots,
    but reaching outside takes ``::``, so what the fragment means cannot depend on how
    deep it is mounted. Checking here needs no mount prefix, which is why it also holds
    for a fragment appended by ``--config.<path>+``, whose index is not knowable yet.

    Raises:
        MissingReferenceError: If a dot run climbs past the root of *scope*.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    for span in _find_expressions(value):
        if span.body is None:
            continue  # escaped $${...}
        for marker in _anchor_markers(span.body):
            _anchor_prefix(node_path, marker.levels, scope)


class _AnchorResolver(ast.NodeTransformer):
    """Replace each anchor stand-in by the absolute path it denotes at *node_path*.

    Works on the tree and never on source, because an absolute path may hold a list
    index or a key that is no identifier (``dbs.0.host``): expressible as an
    ``ast.Attribute`` chain, which :func:`_attribute_chain` reads straight back, but
    not as Python anyone could parse.

    Only the stand-in is rewritten; every segment the expression spells after it keeps
    its own node, so ``.m[0]`` and ``.[0]`` stay subscripts, which an integer key answers
    when the path read misses. The configuration root has no path to stand for, so there
    the first segment after the stand-in becomes the base name instead (``::['web-1']``
    reads ``web-1``); a stand-in left in the tree names the root itself (``${::}``,
    ``${::[k]}``), which :func:`_collect_names` reads as a reference to the whole of it.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#implementation-constraints
    """

    def __init__(self, node_path: _Path) -> None:
        self._node_path = node_path

    def _anchored(self, node: ast.expr) -> _Path | None:
        """Return the path the stand-in *node* names, or ``None`` when *node* is no stand-in."""
        levels = _anchor_dot_count(node.id) if isinstance(node, ast.Name) else None
        if levels is None:
            return None
        return () if levels == 0 else _anchor_prefix(self._node_path, levels)

    def _visit_segment(self, node: ast.Attribute | ast.Subscript) -> ast.AST:
        """Make the segment *node* spells on a stand-in for the root its base name, else recurse."""
        segment = _segment(node) if self._anchored(node.value) == () else None
        if segment is not None:
            return ast.copy_location(ast.Name(id=segment, ctx=ast.Load()), node)
        return self.generic_visit(node)

    visit_Attribute = _visit_segment  # NodeTransformer dispatches on the class name
    visit_Subscript = _visit_segment

    def visit_Name(self, node: ast.Name) -> ast.AST:  # NodeTransformer dispatches on the class name
        """Rewrite a stand-in into the path of the node it names, unless that is the root.

        The path may itself hang off the root stand-in (:func:`_path_to_ast`), so it is
        visited in turn.
        """
        anchored = self._anchored(node)
        return self.visit(ast.copy_location(_path_to_ast(anchored), node)) if anchored else node


def _parse_anchored(expr_content: str, node_path: _Path) -> ast.Expression:
    """Parse one ``${...}`` body, resolving any anchor stand-in against *node_path*.

    The parse cache is shared, so the tree is copied before it is rewritten.
    """
    tree = _parse_expression(expr_content)
    if not any(isinstance(node, ast.Name) and _anchor_dot_count(node.id) is not None for node in ast.walk(tree)):
        return tree
    rewritten = _AnchorResolver(node_path).visit(copy.deepcopy(tree))
    ast.fix_missing_locations(rewritten)
    return cast("ast.Expression", rewritten)


class _Prefixer(ast.NodeTransformer):
    """Rewrite each file-anchored reference base ``name`` into the path ``<prefix>.name``.

    Replacing the base ``Name`` of ``servers[0].host`` with ``db.servers`` yields
    ``db.servers[0].host``; a method receiver works the same (``x.upper()`` →
    ``db.x.upper()``), and so does a name spelled like a function anywhere but as a
    callee (``max`` → ``db.max``, but ``max(a)`` → ``max(db.a)``). The prefix is a tuple of
    segments, spelled by :func:`_path_to_ast`, so ``("xs", "0")`` prefixes ``p`` into
    ``xs[0].p`` and ``("web-1",)`` into ``::['web-1'].p``. Correct only while
    :data:`_ALLOWED_NODES` has no construct that binds names (lambdas, comprehensions).

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """

    def __init__(self, prefix: _Path) -> None:
        self._parts = prefix

    def visit_Call(self, node: ast.Call) -> ast.AST:  # NodeTransformer dispatches on the AST class name
        """Prefix the arguments, and the callee only when it names no function."""
        if _function_name(node) is None:
            return self.generic_visit(node)
        node.args = [self.visit(arg) for arg in node.args]
        node.keywords = [self.visit(keyword) for keyword in node.keywords]
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:  # NodeTransformer dispatches on the AST class name
        """Return *node* unchanged for an anchor, else prefixed."""
        if _anchor_dot_count(node.id) is not None:
            return node
        return ast.copy_location(_path_to_ast([*self._parts, node.id]), node)


def _prefix_content(expr_content: str, prefix: _Path) -> str:
    """Prefix every file-anchored reference in one ``${...}`` body by *prefix*.

    A body that does not parse is returned as written: the merge never validates an
    expression, so it reaches resolution, which refuses it quoting the file's own text, as
    it does for a file loaded at the root.

    Dev Notes:
        docs-dev/architecture/invariants.md#merge-stays-unvalidated
    """
    try:
        tree = _parse_expression(expr_content)
    except SyntaxError:
        return expr_content
    # The parse cache is shared, and _Prefixer rewrites the tree in place.
    tree = _Prefixer(prefix).visit(copy.deepcopy(tree))
    return _unparse(tree)


def _map_expressions(value: str, fn: Callable[[str], str]) -> str:
    """Apply *fn* to the body of each real ``${...}``, leaving ``$${...}`` escapes alone."""
    out: list[str] = []
    last = 0
    for span in _find_expressions(value):
        out.append(value[last : span.start])
        out.append(value[span.start : span.end] if span.body is None else "${" + fn(span.body) + "}")
        last = span.end
    out.append(value[last:])
    return "".join(out)


def _map_strings(data: Any, fn: Callable[[str], str]) -> Any:
    """Rebuild *data*, applying *fn* to every expression-bearing string leaf."""
    if isinstance(data, dict):
        return {k: _map_strings(v, fn) for k, v in data.items()}
    if isinstance(data, list):
        return [_map_strings(v, fn) for v in data]
    if isinstance(data, tuple):
        return tuple(_map_strings(v, fn) for v in data)
    if contains_expression(data):
        # Preserve a str subclass (_StrToken) rather than flattening it to str.
        return type(data)(_map_expressions(cast("str", data), fn))
    return data


def prefix_references(data: Any, prefix: _Path) -> Any:
    """Return *data* with every file-anchored reference prefixed by *prefix*.

    Called on one configuration file's own content, mounted at *prefix* inside the
    configuration, one segment per key or list index; every bare reference of the file
    gets the same prefix.  Anchored
    references — the configuration root (``${::foo}``) and node-relative ones
    (``${.foo}``, ``${..foo}``) — are left untouched, the first because it does not
    depend on the mount and the second because it moves with the node.  An empty
    *prefix* returns *data* itself, unchanged.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    if not prefix:
        return data
    return _map_strings(data, lambda content: _prefix_content(content, prefix))


def canonicalize_references(data: Any) -> Any:
    """Return *data* with configuration-root references rewritten as plain paths.

    Run once every file has been mounted, by which point ``${::x}`` and a bare
    ``${x}`` mean the same thing.

    Node-relative references are deliberately left as they are: resolving one here
    would write the index an element currently holds into the merged dict, so
    reordering the list, or lifting the element into a file of its own, would break
    it silently.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path
    """
    return _map_strings(data, _strip_anchor)
