# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Expression resolution for ${...} field references and computations."""

from __future__ import annotations

import ast
import copy
import math
import operator
import re
from collections import deque
from typing import Any

from confarg.exceptions import (
    CircularReferenceError,
    ExpressionEvalError,
    MissingReferenceError,
    UnsafeExpressionError,
)

# Regex: matches escaped $${...} (no capture) and real ${...} (content in group 1)
_EXPR_RE = re.compile(r"\$\$\{[^}]*\}|\$\{([^}]+)\}")

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
    deps: dict[str, set[str]] = {}
    for path, raw_str in expr_fields.items():
        refs = _extract_references(raw_str)
        # Filter refs to only those that are themselves expressions
        # Non-expression refs are "free" (already resolved)
        deps[path] = refs & set(expr_fields.keys())

    # 3. Topological sort
    order = _topological_sort(deps)

    # 4. Validate AST for all expressions
    for path in order:
        raw_str = expr_fields[path]
        for m in _EXPR_RE.finditer(raw_str):
            expr_content = m.group(1)
            if expr_content is not None:  # not escaped
                _validate_ast(expr_content)

    # 5. Resolve in order, building namespace incrementally
    for path in order:
        raw_str = expr_fields[path]
        result = _resolve_single(raw_str, data)
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
    elif isinstance(value, str) and _EXPR_RE.search(value):
        out[path] = value


def _extract_references(expr_str: str) -> set[str]:
    """Extract dotted field paths referenced in expression string.

    Returns:
        Set of dotted paths (e.g. {"db.host", "db.port"}).
    """
    refs: set[str] = set()
    for m in _EXPR_RE.finditer(expr_str):
        expr_content = m.group(1)
        if expr_content is None:
            continue  # escaped $${...}
        try:
            tree = ast.parse(expr_content, mode="eval")
        except SyntaxError:
            continue
        _collect_names(tree, refs)
    return refs


def _collect_names_from_call(node: ast.Call, refs: set[str]) -> None:
    """Collect field references from a Call node, distinguishing methods from free functions."""
    _min_attribute_parts = 2
    if isinstance(node.func, ast.Attribute):
        parts = _attribute_chain(node.func)
        if parts is not None and len(parts) >= _min_attribute_parts and parts[-1] in _SAFE_METHODS:
            # Method call like x.upper(): add the receiver path, not the method name.
            obj_path = ".".join(parts[:-1])
            if obj_path not in _SAFE_FUNCTIONS:
                refs.add(obj_path)
            for arg in node.args:
                _collect_names(arg, refs)
            for kw in node.keywords:
                _collect_names(kw.value, refs)
            return
        _collect_names(node.func, refs)
    elif not isinstance(node.func, ast.Name):
        # Indirect call — descend into the func expression.
        _collect_names(node.func, refs)
    # Free function call: skip the function name itself, collect args.
    for arg in node.args:
        _collect_names(arg, refs)
    for kw in node.keywords:
        _collect_names(kw.value, refs)


def _collect_names(node: ast.AST, refs: set[str]) -> None:
    """Collect Name nodes and dotted Attribute chains from AST as field references."""
    if isinstance(node, ast.Name):
        if node.id not in _SAFE_FUNCTIONS:
            refs.add(node.id)
        return
    if isinstance(node, ast.Attribute):
        parts = _attribute_chain(node)
        if parts is not None:
            if parts[0] not in _SAFE_FUNCTIONS:
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
    """Return the integer value of an AST node if it is an int literal or -int literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        return -node.operand.value
    return None


def _attribute_chain(node: ast.Attribute | ast.Subscript) -> list[str] | None:
    """Extract dotted name chain from nested Attribute/Subscript nodes.

    Returns e.g. ["db", "host"] for ``db.host``, ["servers", "0", "host"] for
    ``servers[0].host``, ["servers", "-1", "host"] for ``servers[-1].host``,
    or None if base is not a Name.
    """
    parts: list[str] = []
    if isinstance(node, ast.Attribute):
        parts.append(node.attr)
        current: ast.AST = node.value
    else:
        # Subscript at top (shouldn't be called directly, but handle it)
        idx = _ast_int_value(node.slice)
        if idx is not None:
            parts.append(str(idx))
        else:
            return None
        current = node.value
    while True:
        if isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        elif isinstance(current, ast.Subscript):
            idx = _ast_int_value(current.slice)
            if idx is not None:
                parts.append(str(idx))
                current = current.value
            else:
                return None
        else:
            break
    if isinstance(current, ast.Name):
        parts.append(current.id)
        parts.reverse()
        return parts
    return None


def _compute_in_degrees(deps: dict[str, set[str]]) -> dict[str, int]:
    """Count how many deps-graph neighbours each node depends on (Kahn's algorithm setup)."""
    in_degree: dict[str, int] = dict.fromkeys(deps, 0)
    for node, node_deps in deps.items():
        for dep in node_deps:
            if dep in deps:
                in_degree[node] += 1
    return in_degree


def _topological_sort(deps: dict[str, set[str]]) -> list[str]:
    """Kahn's algorithm. Raises CircularReferenceError on cycles."""
    if not deps:
        return []

    in_degree = _compute_in_degrees(deps)
    queue: deque[str] = deque(node for node, degree in in_degree.items() if degree == 0)

    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for other, other_deps in deps.items():
            if node in other_deps and other not in order:
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)

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
        tree = ast.parse(expr_str, mode="eval")
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
    if isinstance(node.func, ast.Name):
        if node.func.id not in _SAFE_FUNCTIONS:
            msg = f"Function '{node.func.id}' is not allowed"
            raise UnsafeExpressionError(msg)
    elif isinstance(node.func, ast.Attribute):
        if node.func.attr not in _SAFE_METHODS and node.func.attr not in _SAFE_FUNCTIONS:
            msg = f"Method '{node.func.attr}' is not allowed"
            raise UnsafeExpressionError(msg)
    else:
        msg = "Indirect function calls are not allowed"
        raise UnsafeExpressionError(msg)


def _eval_name(node: ast.Name, namespace: dict[str, Any]) -> Any:
    if node.id in _SAFE_FUNCTIONS:
        return _SAFE_FUNCTIONS[node.id]
    return _get_nested(namespace, node.id)


def _eval_attribute(node: ast.Attribute, namespace: dict[str, Any]) -> Any:
    parts = _attribute_chain(node)
    if parts is not None:
        try:
            return _get_nested(namespace, ".".join(parts))
        except MissingReferenceError:
            pass
    return getattr(_evaluate_ast(node.value, namespace), node.attr)


def _eval_subscript(node: ast.Subscript, namespace: dict[str, Any]) -> Any:
    return _evaluate_ast(node.value, namespace)[_evaluate_ast(node.slice, namespace)]


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
    func = _evaluate_ast(node.func, namespace)
    args = [_evaluate_ast(a, namespace) for a in node.args]
    kwargs = {kw.arg: _evaluate_ast(kw.value, namespace) for kw in node.keywords}
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


def _resolve_single(expr_str: str, namespace: dict[str, Any]) -> Any:
    """Resolve a single expression string.

    Handles three cases:
    1. Pure ${expr} — typed result
    2. Interpolation (text around ${...}) — string result
    3. Escaped $${...} — literal ${...}
    """
    # Check if the entire string is a single ${expr}
    stripped = expr_str.strip()
    m = re.fullmatch(r"\$\{([^}]+)\}", stripped)
    if m and stripped == expr_str:
        # Pure expression — return typed result
        tree = ast.parse(m.group(1), mode="eval")
        try:
            return _evaluate_ast(tree, namespace)
        except (MissingReferenceError, UnsafeExpressionError):
            raise
        except ExpressionEvalError:
            raise
        except Exception as exc:
            msg = f"Error in expression {expr_str!r}: {exc}"
            raise ExpressionEvalError(msg) from exc

    # Interpolation or escape mode: build string from parts
    result_parts: list[str] = []
    last_end = 0
    for m in _EXPR_RE.finditer(expr_str):
        # Add literal text before this match
        start = m.start()
        result_parts.append(expr_str[last_end:start])

        if m.group(1) is None:
            # Escaped $${...} — produce literal ${...}
            escaped_text = m.group(0)  # e.g. "$${foo}"
            result_parts.append(escaped_text[1:])  # strip one $, producing "${foo}"
        else:
            # Real expression — evaluate and stringify
            tree = ast.parse(m.group(1), mode="eval")
            try:
                value = _evaluate_ast(tree, namespace)
            except (MissingReferenceError, UnsafeExpressionError):
                raise
            except ExpressionEvalError:
                raise
            except Exception as exc:
                msg = f"Error in expression {m.group(0)!r}: {exc}"
                raise ExpressionEvalError(msg) from exc
            result_parts.append(str(value))

        last_end = m.end()

    # Add any trailing literal text
    result_parts.append(expr_str[last_end:])
    return "".join(result_parts)


def _get_nested(data: dict[str, Any], path: str) -> Any:
    """Retrieve value from nested dict/list by dotted path."""
    parts = path.split(".")
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
