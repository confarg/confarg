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
from collections import deque
from functools import lru_cache
from typing import TYPE_CHECKING, Any, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

from confarg.exceptions import (
    CircularReferenceError,
    ExpressionEvalError,
    MissingReferenceError,
    UnsafeExpressionError,
)

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
    """Parse one ``${...}`` body into a cached AST.

    The root marker is stripped before parsing, so the cache is keyed by the raw
    expression text. Every parse site in resolution — reference extraction,
    validation and evaluation — goes through here, so a unique expression is
    parsed however many times it appears but at most once.

    A node-relative reference reaches here as a stand-in name, which parses and so
    caches like anything else; what it *denotes* differs per node, which is why
    :func:`_parse_anchored` rewrites the tree on the way out rather than the text
    on the way in.

    Dev Notes:
        docs-dev/architecture/expressions/resolution.md#resolution-algorithm
    """
    return _parse_body(_strip_anchor(content))


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

    # 2. Swap anchor markers for stand-in names so every body parses; what each one
    #    denotes is settled per node by _parse_anchored, below.
    expr_fields = {path: name_anchors(raw_str) for path, raw_str in expr_fields.items()}

    data = copy.deepcopy(data)

    # 3. Extract references and build dependency graph
    expr_paths = set(expr_fields.keys())
    deps: dict[str, set[str]] = {}
    for path, raw_str in expr_fields.items():
        refs = _extract_references(raw_str, path)
        # Filter refs to only those that are themselves expressions
        # Non-expression refs are "free" (already resolved)
        deps[path] = refs & expr_paths

    # 4. Topological sort
    order = _topological_sort(deps)

    # 5. Validate AST for all expressions
    for path in order:
        for span in _find_expressions(expr_fields[path]):
            if span.body is not None:  # not escaped
                _validate_ast(span.body)

    # 6. Resolve in order, building namespace incrementally
    for path in order:
        raw_str = expr_fields[path]
        result = _resolve_single(raw_str, data, path)
        _set_nested_by_path(data, path, result)

    return data


def _scan_expressions(
    data: dict[str, Any],
    prefix: str = "",
) -> dict[str, str]:
    """Walk merged dict, find string values containing ${...}.

    Returns:
        Dict mapping dotted paths to raw expression strings.
    """
    result: dict[str, str] = {}
    for key, value in data.items():
        full_path = f"{prefix}.{key}" if prefix else key
        _collect_expressions(value, full_path, result)
    return result


def _collect_expressions(value: Any, path: str, out: dict[str, str]) -> None:
    """Recursively collect expression strings from a value into *out*."""
    if isinstance(value, dict):
        for k, v in value.items():
            _collect_expressions(v, f"{path}.{k}", out)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _collect_expressions(item, f"{path}.{i}", out)
    elif contains_expression(value):
        out[path] = value


def _extract_references(expr_str: str, node_path: str = "") -> set[str]:
    """Extract dotted field paths referenced in expression string.

    *node_path* is where the expression sits, which is what an anchor stand-in is
    resolved against, so the paths returned are absolute either way.

    Returns:
        Set of dotted paths (e.g. {"db.host", "db.port"}).
    """
    refs: set[str] = set()
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


def _collect_names_from_call(node: ast.Call, refs: set[str]) -> None:
    """Collect field references from a Call node: its arguments, and its callee unless that names a function."""
    _min_attribute_parts = 2
    if _function_name(node) is None:
        parts = _attribute_chain(node.func) if isinstance(node.func, ast.Attribute) else None
        if parts is not None and len(parts) >= _min_attribute_parts and parts[-1] in _SAFE_METHODS:
            # Method call like x.upper(): add the receiver path, not the method name.
            refs.add(".".join(parts[:-1]))
        else:
            # Indirect call — descend into the func expression.
            _collect_names(node.func, refs)
    for arg in node.args:
        _collect_names(arg, refs)
    for kw in node.keywords:
        _collect_names(kw.value, refs)


def _collect_names(node: ast.AST, refs: set[str]) -> None:
    """Collect Name nodes and the config paths of Attribute/Subscript chains as field references."""
    if isinstance(node, ast.Name):
        refs.add(node.id)
        return
    if isinstance(node, ast.Attribute | ast.Subscript):
        parts = _attribute_chain(node)
        if parts is not None:
            refs.add(".".join(parts))
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


def _subscript_segment(index: ast.expr) -> str | None:
    """Return the path segment a subscript's *index* spells, or ``None`` for a computed one.

    A string constant is the key itself (``['web-1']``), an integer constant the list index
    (``[0]``, ``[-1]``).
    """
    if isinstance(index, ast.Constant) and isinstance(index.value, str):
        return index.value
    number = _ast_int_value(index)
    return None if number is None else str(number)


def _attribute_chain(node: ast.Attribute | ast.Subscript) -> list[str] | None:
    """Return the config path *node* reads, segment by segment, or ``None`` when it reads none.

    The one answer to "which config path does this node read?": a dot and a constant
    subscript each spell one segment, so ``db.host``, ``db['host']`` and ``db["host"]`` are
    ``["db", "host"]``, ``servers[0].host`` is ``["servers", "0", "host"]`` and
    ``svc['web-1']`` is ``["svc", "web-1"]``. ``None`` when a subscript is computed
    (``svc[k]``) or the chain is not rooted at a name (``f(x).a``). Reference collection and
    evaluation both ask it.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute | ast.Subscript):
        segment = current.attr if isinstance(current, ast.Attribute) else _subscript_segment(current.slice)
        if segment is None:
            return None
        parts.append(segment)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    parts.reverse()
    return parts


def _topological_sort(deps: dict[str, set[str]]) -> list[str]:
    """Kahn's algorithm. Raises CircularReferenceError on cycles.

    Linear in the graph size (``V + E``): a reverse adjacency list records, for
    each node, who depends on it, so releasing a node touches only its direct
    dependents rather than rescanning the whole graph.
    """
    if not deps:
        return []

    in_degree: dict[str, int] = dict.fromkeys(deps, 0)
    dependents: dict[str, list[str]] = {node: [] for node in deps}
    for node, node_deps in deps.items():
        for dep in node_deps:
            if dep in deps:
                in_degree[node] += 1
                dependents[dep].append(node)

    queue: deque[str] = deque(node for node, degree in in_degree.items() if degree == 0)
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in dependents[node]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(deps):
        remaining = set(deps.keys()) - set(order)
        msg = f"Circular reference detected among: {', '.join(sorted(remaining))}"
        raise CircularReferenceError(msg)

    return order


def _validate_ast(expr_str: str) -> None:
    """Parse expression and validate AST contains only allowed nodes.

    Raises UnsafeExpressionError for disallowed constructs.
    """
    try:
        tree = _parse_expression(expr_str)
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
    elif isinstance(node.func, ast.Attribute):
        if node.func.attr not in _SAFE_METHODS and node.func.attr not in _SAFE_FUNCTIONS:
            msg = f"Method '{node.func.attr}' is not allowed"
            raise UnsafeExpressionError(msg)
    else:
        msg = "Indirect function calls are not allowed"
        raise UnsafeExpressionError(msg)


def _eval_name(node: ast.Name, namespace: dict[str, Any]) -> Any:
    """Read the config key *node* names; a callee never reaches here (see :func:`_function_name`)."""
    if node.id in _SAFE_FUNCTIONS and node.id not in namespace:
        detail = f"'{node.id}' is a function only when called, as in {node.id}(...)"
        raise MissingReferenceError.field_not_found(node.id, detail)
    return _get_nested(namespace, [node.id])


def _eval_path_or(node: ast.Attribute | ast.Subscript, namespace: dict[str, Any], access: Callable[[Any], Any]) -> Any:
    """Read the config path *node* spells; failing that, apply *access* to its evaluated base.

    The path comes first, so ``svc['web'].host`` reads what ``svc.web.host`` reads. What no
    path answers is Python's own access: a method off a string (``name.upper``), an index into
    one (``name[0]``), a computed key (``svc[k]``), a key that is no string. When that fails
    too, the path's own miss is reported rather than ``'dict' object has no attribute ...``.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#spelling-a-path
    """
    parts = _attribute_chain(node)
    missing: MissingReferenceError | None = None
    if parts is not None:
        try:
            return _get_nested(namespace, parts)
        except MissingReferenceError as exc:
            missing = exc
    try:
        return access(_evaluate_ast(node.value, namespace))
    except (AttributeError, LookupError, TypeError):
        if missing is None:
            raise
        raise missing from None


def _eval_attribute(node: ast.Attribute, namespace: dict[str, Any]) -> Any:
    return _eval_path_or(node, namespace, lambda base: getattr(base, node.attr))


def _eval_subscript(node: ast.Subscript, namespace: dict[str, Any]) -> Any:
    return _eval_path_or(node, namespace, lambda base: base[_evaluate_ast(node.slice, namespace)])


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


def _eval_call(node: ast.Call, namespace: dict[str, Any]) -> Any:
    function = _function_name(node)
    func = _SAFE_FUNCTIONS[function] if function is not None else _evaluate_ast(node.func, namespace)
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
    ast.Attribute: _eval_attribute,
    ast.Subscript: _eval_subscript,
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


def _resolve_single(expr_str: str, namespace: dict[str, Any], node_path: str = "") -> Any:
    """Resolve a single expression string.

    Handles three cases:
    1. Pure ${expr} — typed result
    2. Interpolation (text around ${...}) — string result
    3. Escaped $${...} — literal ${...}

    *node_path* is where the expression sits, which is what an anchor stand-in
    (``__UP1__``, ``__ROOT__``) is resolved against.
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


def _get_nested(data: dict[str, Any], parts: list[str]) -> Any:
    """Retrieve the value at the path *parts* from a nested dict/list, one segment per key or index.

    Segments are taken as given, never re-split, so a key holding a dot (``['example.com']``)
    is one segment.
    """
    path = ".".join(parts)
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise MissingReferenceError.field_not_found(path)
            current = current[part]
        elif isinstance(current, list | tuple):
            try:
                idx = int(part)
            except ValueError:
                raise MissingReferenceError.field_not_found(path, f"'{part}' is not a valid index") from None
            try:
                current = current[idx]
            except IndexError:
                raise MissingReferenceError.field_not_found(path, f"index {idx} out of range") from None
        else:
            raise MissingReferenceError.field_not_found(path, f"cannot traverse into {type(current).__name__}")
    return current


def _set_nested_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Set value in nested dict by dotted path."""
    parts = path.split(".")
    current: Any = data
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list | tuple):
            current = current[int(part)]
        else:
            msg = f"Cannot set path '{path}': cannot traverse into {type(current).__name__}"
            raise MissingReferenceError(msg)
    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        current[int(last)] = value
    else:
        msg = f"Cannot set path '{path}'"
        raise MissingReferenceError(msg)


# ---------------------------------------------------------------------------
# Reference anchoring
# ---------------------------------------------------------------------------

#: Transient stand-in for a configuration-root anchor while an expression is parsed.
#: ``::`` is not valid Python, so it is swapped for this name before
#: :func:`ast.parse` and swapped back on the way out.
_ROOT_ANCHOR = "__ROOT__"

#: Transient stand-in for a node-relative anchor: a run of *n* dots becomes ``__UP<n>__``.
_UP_ANCHOR_RE = re.compile(r"^__UP(\d+)__$")

#: Cheap test for a stand-in anywhere in an expression body, to skip the rewrite.
_ANCHOR_NAME_RE = re.compile(r"__(?:ROOT|UP\d+)__")

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


def _up_anchor(dots: int) -> str:
    """Return the transient stand-in name for a run of *dots* dots."""
    return f"__UP{dots}__"


def _anchor_dot_count(name: str) -> int | None:
    """Return the level count *name* anchors to, or ``None`` when it is not an anchor name."""
    if name == _ROOT_ANCHOR:
        return 0
    match = _UP_ANCHOR_RE.match(name)
    return int(match.group(1)) if match else None


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


def _anchor_markers(expr_content: str) -> list[tuple[int, int, int]]:
    """``(offset, length, levels)`` of each anchor marker that begins an operand.

    *levels* is how far a dot run climbs — one per dot — and ``0`` marks ``::``, the
    configuration root. Token-based: the dots of ``1.5`` or ``','.join(x)`` are not
    markers, while the one in ``a if .b else c`` is. A ``::`` inside brackets is a
    slice step and not a marker, which keeps ``items[::2]`` spellable; reach the root
    there with ``items[(::step)]``.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    try:
        toks = _significant_tokens(expr_content)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []  # malformed: let ast.parse report it with its own message
    found: list[tuple[int, int, int]] = []
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
        if dots:
            found.append((begin, end - begin, len(run)))
        elif len(run) == _ROOT_MARKER_COLONS:
            found.append((begin, end - begin, 0))
        prev_type, prev_str = tokenize.OP, run[-1]
    return found


def _path_to_ast(parts: list[str]) -> ast.expr:
    """Build the ``Name``/``Attribute`` chain that reads the dotted path *parts*."""
    built: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
    for part in parts[1:]:
        built = ast.Attribute(value=built, attr=part, ctx=ast.Load())
    return built


def _marker_text(levels: int) -> str:
    """Spell the marker *levels* stands for: ``::`` at the root, else that many dots."""
    return "::" if levels == 0 else "." * levels


def _strip_anchor(expr_content: str) -> str:
    """Rewrite configuration-root references as plain paths (``::foo.bar`` -> ``foo.bar``).

    In a standalone dict the configuration root *is* the dict root, so dropping the
    marker is exactly what a root reference means there.  Every parse site goes
    through this, so ``build()`` and ``resolve()`` accept the marker even though
    :func:`confarg.merge` normally canonicalizes it away first.

    Node-relative markers are left alone: they mean nothing without the path of the
    node that wrote them, and :func:`resolve_expressions` has already replaced them
    by the time any parse site runs.
    """
    return _replace_spans(
        expr_content,
        [(o, o + n, "") for o, n, levels in _anchor_markers(expr_content) if levels == 0],
    )


def _name_anchor(expr_content: str) -> str:
    """Swap each anchor marker for a parseable name (``..foo`` -> ``__UP2__.foo``)."""
    return _replace_spans(
        expr_content,
        [
            (o, o + n, (_ROOT_ANCHOR if levels == 0 else _up_anchor(levels)) + ".")
            for o, n, levels in _anchor_markers(expr_content)
        ],
    )


def _unname_anchor(expr_content: str) -> str:
    """Turn ``__UP2__.foo`` back into ``..foo`` after unparsing.

    Token-based, so a string literal containing the name is left intact.  The dot the
    stand-in owns is consumed with it, because the marker it restores carries its own.
    """
    try:
        toks = _significant_tokens(expr_content)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return expr_content
    edits: list[tuple[int, int, str]] = []
    for index, (ttype, tstr, begin, finish) in enumerate(toks):
        levels = _anchor_dot_count(tstr) if ttype == tokenize.NAME else None
        if levels is None:
            continue
        nxt = toks[index + 1] if index + 1 < len(toks) else None
        end = nxt[3] if nxt is not None and nxt[1] == "." and nxt[2] == finish else finish
        edits.append((begin, end, _marker_text(levels)))
    return _replace_spans(expr_content, edits)


def _anchor_prefix(node_path: str, levels: int) -> str:
    """Dotted prefix a run of *levels* dots stands for at *node_path*.

    One dot is the container holding the expression, so *levels* segments are dropped
    from the node's own path and the result is ``""`` at the root of the document.  A
    list index is an ordinary segment, the same path model :func:`_get_nested` uses.

    Raises:
        MissingReferenceError: If the run climbs above the root of the document.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    segments = node_path.split(".") if node_path else []
    if levels > len(segments):
        raise MissingReferenceError.anchor_above_root(node_path, levels)
    kept = segments[: len(segments) - levels]
    return ".".join(kept) + "." if kept else ""


def check_anchor_depth(value: str, node_path: str, scope: str = "file") -> None:
    """Raise if a relative reference in *value* climbs above the root of its scope.

    Called while a file is loaded, where *node_path* is the position within *that
    file*: a fragment may look at itself with dots, but reaching outside takes
    ``::``, so what the fragment means cannot depend on how deep it is mounted.
    Checking here needs no mount prefix, which is why it also holds for a fragment
    appended by ``--config.<path>+``, whose index is not knowable yet.

    Raises:
        MissingReferenceError: If a dot run climbs past the root of *scope*.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    depth = len(node_path.split(".")) if node_path else 0
    for span in _find_expressions(value):
        if span.body is None:
            continue  # escaped $${...}
        for _, _, levels in _anchor_markers(span.body):
            if levels > depth:
                raise MissingReferenceError.anchor_above_root(node_path, levels, scope)


def name_anchors(value: str) -> str:
    """Return *value* with each expression's anchor markers swapped for stand-in names.

    ``${.x}`` becomes ``${__UP1__.x}`` and ``${::x}`` becomes ``${__ROOT__.x}``, which
    parse.  What each stand-in denotes depends on where the expression sits, so it is
    :class:`_AnchorResolver` that turns it into a path, once the node is known.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """
    return _map_expressions(value, _name_anchor)


class _AnchorResolver(ast.NodeTransformer):
    """Replace each anchor stand-in by the absolute path it denotes at *node_path*.

    Works on the tree and never on source, because an absolute path may hold a list
    index or a key that is no identifier (``dbs.0.host``): expressible as an
    ``ast.Attribute`` chain, which :func:`_attribute_chain` reads straight back, but
    not as Python anyone could parse.

    Only the stand-in and the segment it owns are rewritten; whatever the expression
    spells after them keeps its own node, so ``.a['__class__']`` stays a subscript and
    never becomes an attribute the evaluator would ``getattr``.

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#implementation-constraints
    """

    def __init__(self, node_path: str) -> None:
        self._node_path = node_path

    def _absolute(self, parts: list[str]) -> list[str] | None:
        """Return *parts* with a leading stand-in expanded, or ``None`` if it has none."""
        levels = _anchor_dot_count(parts[0])
        if levels is None:
            return None
        prefix = "" if levels == 0 else _anchor_prefix(self._node_path, levels)
        return [segment for segment in prefix.split(".") if segment] + parts[1:]

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:  # NodeTransformer dispatches on the class name
        """Rewrite ``<stand-in>.name`` into the absolute path to ``name``, else recurse."""
        absolute = self._absolute([node.value.id, node.attr]) if isinstance(node.value, ast.Name) else None
        if absolute:
            return ast.copy_location(_path_to_ast(absolute), node)
        return self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> ast.AST:  # NodeTransformer dispatches on the class name
        """Rewrite a bare stand-in, which names the anchored node itself."""
        absolute = self._absolute([node.id])
        return ast.copy_location(_path_to_ast(absolute), node) if absolute else node


def _parse_anchored(expr_content: str, node_path: str) -> ast.Expression:
    """Parse one ``${...}`` body, resolving any anchor stand-in against *node_path*.

    The parse cache is shared, so the tree is copied before it is rewritten.
    """
    tree = _parse_expression(expr_content)
    if not _ANCHOR_NAME_RE.search(expr_content):
        return tree
    rewritten = _AnchorResolver(node_path).visit(copy.deepcopy(tree))
    ast.fix_missing_locations(rewritten)
    return cast("ast.Expression", rewritten)


class _Prefixer(ast.NodeTransformer):
    """Rewrite each file-anchored reference base ``name`` into ``<prefix>.name``.

    Replacing the base ``Name`` of ``servers[0].host`` with ``db.servers`` yields
    ``db.servers[0].host``; a method receiver works the same (``x.upper()`` →
    ``db.x.upper()``), and so does a name spelled like a function anywhere but as a
    callee (``max`` → ``db.max``, but ``max(a)`` → ``max(db.a)``). Correct only while
    :data:`_ALLOWED_NODES` has no construct that binds names (lambdas, comprehensions).

    Dev Notes:
        docs-dev/architecture/expressions/reference-anchoring.md#reference-anchoring
    """

    def __init__(self, prefix: str) -> None:
        self._parts = prefix.split(".")

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


def _prefix_content(expr_content: str, prefix: str) -> str:
    """Prefix every file-anchored reference in one ``${...}`` body by *prefix*."""
    tree = _parse_body(_name_anchor(expr_content))
    tree = _Prefixer(prefix).visit(tree)
    ast.fix_missing_locations(tree)
    return _unname_anchor(ast.unparse(tree))


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


def prefix_references(data: Any, prefix: str) -> Any:
    """Return *data* with every file-anchored reference prefixed by *prefix*.

    Called when one configuration file's content is mounted at *prefix* inside a
    larger document; every bare reference of the file gets the same prefix.  Anchored
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
