# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for field references and expressions (${...} syntax)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest

import confarg
from confarg._types import _StrToken
from confarg.dictexpr._expressions import (
    _SAFE_FUNCTIONS,
    _anchor_markers,
    _anchor_prefix,
    _extract_references,
    _name_anchor,
    _prefix_content,
    _scan_expressions,
    _topological_sort,
    _unname_anchor,
    _validate_ast,
    contains_expression,
    resolve_expressions,
)
from confarg.exceptions import (
    CircularReferenceError,
    ExpressionEvalError,
    MissingReferenceError,
    UnsafeExpressionError,
)
from tests.conftest import (
    WithDefaults,
)

# ---------------------------------------------------------------------------
# contains_expression: the canonical "would resolution rewrite this?" predicate
# ---------------------------------------------------------------------------


class TestContainsExpression:
    """The single predicate every pre-resolution value gate must consult.

    Eager leaf coercion and the three CLI adapters' parse-time domain checks all
    defer on it, so it must agree exactly with what ``resolve_expressions``
    rewrites — no narrower (a gate would eat an expression) and no wider (a gate
    would wave through a value it could have rejected).
    """

    @pytest.mark.parametrize(
        "value",
        [
            "${a}",
            "${a.b.c}",
            "${a * 1.5}",
            "pre-${a}-post",
            "${a}:${b}",
            "$${a}",
            _StrToken("${a}"),
        ],
    )
    def test_true_for_rewritten_values(self, value: object) -> None:
        """Real and escaped expressions, bare or embedded, are all deferred."""
        assert contains_expression(value) is True

    @pytest.mark.parametrize(
        "value",
        ["", "plain", "$a", "${", "}", "${}", "$", "100%", 42, 4.5, None, True, ["${a}"], {"k": "${a}"}],
    )
    def test_false_for_untouched_values(self, value: object) -> None:
        """Non-strings and strings resolution leaves alone are not deferred."""
        assert contains_expression(value) is False

    def test_agrees_with_the_resolver_scan(self) -> None:
        """Every leaf the predicate accepts is a leaf ``_scan_expressions`` collects."""
        data = {"real": "${a}", "escaped": "$${a}", "embedded": "x${a}y", "plain": "a", "open": "${"}
        scanned = set(_scan_expressions(data))
        predicted = {k for k, v in data.items() if contains_expression(v)}
        assert scanned == predicted == {"real", "escaped", "embedded"}


# ---------------------------------------------------------------------------
# Scan expressions
# ---------------------------------------------------------------------------


class TestScanExpressions:
    """Detection of ${...} in merged dicts."""

    def test_simple_reference(self) -> None:
        """A simple ${b} reference is detected."""
        data = {"a": "${b}", "b": "hello"}
        result = _scan_expressions(data)
        assert result == {"a": "${b}"}

    def test_nested_dict(self) -> None:
        """Expressions in nested dicts are detected with dotted paths."""
        data = {"db": {"url": "jdbc://${db.host}:${db.port}/mydb", "host": "localhost", "port": 5432}}
        result = _scan_expressions(data)
        assert result == {"db.url": "jdbc://${db.host}:${db.port}/mydb"}

    def test_non_string_ignored(self) -> None:
        """Non-string values are ignored in expression scanning."""
        data = {"count": 42, "rate": math.pi, "flag": True, "nothing": None}
        result = _scan_expressions(data)
        assert result == {}

    def test_no_expressions(self) -> None:
        """A dict with no expressions returns an empty scan result."""
        data = {"name": "hello", "nested": {"value": "world"}}
        result = _scan_expressions(data)
        assert result == {}

    def test_escaped_not_detected(self) -> None:
        """Escaped $${...} is detected for processing (to unescape) but not as a real reference."""
        data = {"a": "$${not_a_ref}"}
        result = _scan_expressions(data)
        # Escaped expressions ARE detected for processing (to unescape them)
        assert result == {"a": "$${not_a_ref}"}

    def test_list_values_scanned(self) -> None:
        """Expressions inside list elements are detected with integer-index paths."""
        data = {"items": ["${a}", "plain"]}
        result = _scan_expressions(data)
        assert result == {"items.0": "${a}"}

    def test_deeply_nested(self) -> None:
        """Deeply nested expressions are detected with their full dotted path."""
        data = {"a": {"b": {"c": {"d": "${x}"}}}}
        result = _scan_expressions(data)
        assert result == {"a.b.c.d": "${x}"}

    def test_multiple_expressions(self) -> None:
        """Multiple expression fields are all detected."""
        data = {"a": "${x}", "b": "${y}", "c": "plain"}
        result = _scan_expressions(data)
        assert result == {"a": "${x}", "b": "${y}"}


# ---------------------------------------------------------------------------
# Extract references
# ---------------------------------------------------------------------------


class TestExtractReferences:
    """Extracting dotted field paths from expression strings."""

    def test_simple_name(self) -> None:
        """A simple field name reference is extracted correctly."""
        refs = _extract_references("${name}")
        assert refs == {"name"}

    def test_dotted_path(self) -> None:
        """A dotted-path reference is extracted correctly."""
        refs = _extract_references("${db.host}")
        assert refs == {"db.host"}

    def test_multiple_refs(self) -> None:
        """Multiple references in one string are all extracted."""
        refs = _extract_references("jdbc://${db.host}:${db.port}/mydb")
        assert refs == {"db.host", "db.port"}

    def test_arithmetic_expr(self) -> None:
        """An arithmetic expression yields the variable references."""
        refs = _extract_references("${db.port + 1000}")
        assert refs == {"db.port"}

    def test_function_call(self) -> None:
        """Function call arguments are extracted as references."""
        refs = _extract_references("${max(a, b)}")
        assert refs == {"a", "b"}

    def test_no_refs_in_escaped(self) -> None:
        """An escaped expression yields no references."""
        refs = _extract_references("$${not_a_ref}")
        assert refs == set()

    def test_mixed_escaped_and_real(self) -> None:
        """Only the real reference is extracted when mixed with an escaped one."""
        refs = _extract_references("$${escape}${real}")
        assert refs == {"real"}

    def test_string_literal_not_a_ref(self) -> None:
        """A string literal inside an expression is not extracted as a reference."""
        refs = _extract_references('${db.host + ":"}')
        assert refs == {"db.host"}

    def test_list_index_ref(self) -> None:
        """A list index reference is normalized to a dotted path."""
        refs = _extract_references("${servers[0].host}")
        assert refs == {"servers.0.host"}


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    """Dependency ordering and circular detection."""

    def test_simple_chain(self) -> None:
        """A simple dependency chain is sorted topologically."""
        deps = {"c": {"b"}, "b": {"a"}, "a": set()}
        order = _topological_sort(deps)
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_independent(self) -> None:
        """Independent nodes all appear in the sorted result."""
        deps = {"a": set(), "b": set()}
        order = _topological_sort(deps)
        assert set(order) == {"a", "b"}

    def test_diamond(self) -> None:
        """A diamond dependency graph is sorted correctly."""
        deps = {"d": {"b", "c"}, "b": {"a"}, "c": {"a"}, "a": set()}
        order = _topological_sort(deps)
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_circular_raises(self) -> None:
        """A two-node cycle raises CircularReferenceError."""
        deps = {"a": {"b"}, "b": {"a"}}
        with pytest.raises(CircularReferenceError):
            _topological_sort(deps)

    def test_self_reference_raises(self) -> None:
        """A self-referencing node raises CircularReferenceError."""
        deps = {"a": {"a"}}
        with pytest.raises(CircularReferenceError):
            _topological_sort(deps)

    def test_circular_three(self) -> None:
        """A three-node cycle raises CircularReferenceError."""
        deps = {"a": {"c"}, "b": {"a"}, "c": {"b"}}
        with pytest.raises(CircularReferenceError):
            _topological_sort(deps)

    def test_empty(self) -> None:
        """An empty dependency dict returns an empty list."""
        assert _topological_sort({}) == []


# ---------------------------------------------------------------------------
# AST validation
# ---------------------------------------------------------------------------


class TestAstValidation:
    """Safety: allowed ops pass, disallowed constructs rejected."""

    def test_simple_name(self) -> None:
        """A simple variable name passes AST validation."""
        _validate_ast("x")

    def test_dotted_name(self) -> None:
        """A dotted attribute name passes AST validation."""
        _validate_ast("x.y")

    def test_arithmetic(self) -> None:
        """Arithmetic expressions pass AST validation."""
        _validate_ast("x + 1")
        _validate_ast("x * 2 - 3")
        _validate_ast("x / y")
        _validate_ast("x // y")
        _validate_ast("x % y")
        _validate_ast("x ** 2")

    def test_comparison(self) -> None:
        """Comparison expressions pass AST validation."""
        _validate_ast("x > 0")
        _validate_ast("x == y")

    def test_boolean(self) -> None:
        """Boolean expressions pass AST validation."""
        _validate_ast("x and y")
        _validate_ast("not x")

    def test_ternary(self) -> None:
        """Ternary expressions pass AST validation."""
        _validate_ast("x if x > 0 else y")

    def test_function_call(self) -> None:
        """Allowed function calls pass AST validation."""
        _validate_ast("max(x, y)")
        _validate_ast("abs(x)")
        _validate_ast("len(name)")

    def test_string_method(self) -> None:
        """String method calls pass AST validation."""
        _validate_ast("name.upper()")
        _validate_ast("name.replace('a', 'b')")

    def test_subscript(self) -> None:
        """Subscript expressions pass AST validation."""
        _validate_ast("x[0]")

    def test_constant(self) -> None:
        """Constant expressions pass AST validation."""
        _validate_ast("42")
        _validate_ast('"hello"')

    @pytest.mark.parametrize(
        "expr",
        [
            "import os",
            "__import__('os')",
            "lambda: 1",
            "[x for x in y]",
            "eval('1')",
            "exec('1')",
            "compile('1', '', 'eval')",
            "x.__class__",
            "x.__dict__",
            "x.__module__",
        ],
        ids=[
            "import",
            "__import__",
            "lambda",
            "comprehension",
            "eval",
            "exec",
            "compile",
            "__class__",
            "__dict__",
            "__module__",
        ],
    )
    def test_unsafe_rejected(self, expr: str) -> None:
        """Unsafe expression constructs raise UnsafeExpressionError."""
        with pytest.raises(UnsafeExpressionError):
            _validate_ast(expr)


# ---------------------------------------------------------------------------
# Evaluate expressions
# ---------------------------------------------------------------------------


class TestEvaluateExpressions:
    """All operators, math functions, string methods, type conversions, runtime errors."""

    @pytest.mark.parametrize(
        ("expr", "ctx", "expected"),
        [
            # reference
            ("${b}", {"b": "hello"}, "hello"),
            # arithmetic
            ("${b + 1}", {"b": 10}, 11),
            ("${b - 3}", {"b": 10}, 7),
            ("${b * 3}", {"b": 10}, 30),
            ("${b / 4}", {"b": 10}, 2.5),
            ("${b // 3}", {"b": 10}, 3),
            ("${b % 3}", {"b": 10}, 1),
            ("${b ** 2}", {"b": 5}, 25),
            # unary
            ("${-b}", {"b": 5}, -5),
            ("${+b}", {"b": 5}, 5),
            # comparison
            ("${b > 5}", {"b": 10}, True),
            # boolean
            ("${b and c}", {"b": True, "c": False}, False),
            ("${b or c}", {"b": False, "c": True}, True),
            # ternary
            ("${b if b > 0 else c}", {"b": 5, "c": 10}, 5),
            ("${b if b > 0 else c}", {"b": -1, "c": 10}, 10),
            # built-in functions
            ("${abs(b)}", {"b": -5}, 5),
            ("${min(b, c)}", {"b": 3, "c": 7}, 3),
            ("${max(b, c)}", {"b": 3, "c": 7}, 7),
            ("${round(b, 2)}", {"b": math.pi}, round(math.pi, 2)),
            ("${ceil(b)}", {"b": 3.2}, 4),
            ("${floor(b)}", {"b": 3.8}, 3),
            ("${str(b)}", {"b": 42}, "42"),
            ("${int(b)}", {"b": "42"}, 42),
            ("${float(b)}", {"b": "3.14"}, pytest.approx(3.14)),
            ("${bool(b)}", {"b": 0}, False),
            ("${len(b)}", {"b": "hello"}, 5),
            # string methods
            ("${b.upper()}", {"b": "hello"}, "HELLO"),
            ("${b.lower()}", {"b": "HELLO"}, "hello"),
            ("${b.strip()}", {"b": "  hello  "}, "hello"),
            ("${b.replace('world', 'there')}", {"b": "hello world"}, "hello there"),
            ("${b.startswith('he')}", {"b": "hello"}, True),
            ("${b.endswith('lo')}", {"b": "hello"}, True),
            ("${b.split(',')}", {"b": "a,b,c"}, ["a", "b", "c"]),
            ("${','.join(b.split(' '))}", {"b": "a b c"}, "a,b,c"),
        ],
        ids=[
            "ref",
            "add",
            "sub",
            "mul",
            "div",
            "floordiv",
            "mod",
            "pow",
            "neg",
            "pos",
            "gt",
            "and",
            "or",
            "ternary-true",
            "ternary-false",
            "abs",
            "min",
            "max",
            "round",
            "ceil",
            "floor",
            "str",
            "int",
            "float",
            "bool",
            "len",
            "upper",
            "lower",
            "strip",
            "replace",
            "startswith",
            "endswith",
            "split",
            "join",
        ],
    )
    def test_expression_eval(self, expr: str, ctx: dict, expected) -> None:
        """Expressions evaluate to their expected values."""
        data = {"a": expr, **ctx}
        resolved = resolve_expressions(data)
        assert resolved["a"] == expected

    def test_division_by_zero(self) -> None:
        """Division by zero raises ExpressionEvalError."""
        data = {"a": "${b / 0}", "b": 10}
        with pytest.raises(ExpressionEvalError, match="division"):
            resolve_expressions(data)


# ---------------------------------------------------------------------------
# Resolve expressions (full resolution on raw dicts)
# ---------------------------------------------------------------------------


class TestResolveExpressions:
    """Full resolution: field refs, interpolation, chaining, and escaping."""

    def test_field_ref_typed(self) -> None:
        """Pure ${expr} retains native type."""
        data = {"a": "${b}", "b": 42}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42
        assert isinstance(resolved["a"], int)

    def test_interpolation_string(self) -> None:
        """Interpolation result is always string."""
        data = {"url": "jdbc://${host}:${port}/db", "host": "localhost", "port": 5432}
        resolved = resolve_expressions(data)
        assert resolved["url"] == "jdbc://localhost:5432/db"
        assert isinstance(resolved["url"], str)

    def test_chaining(self) -> None:
        """Expressions can reference other expressions."""
        data = {"a": "${b}", "b": "${c}", "c": 42}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42
        assert resolved["b"] == 42

    def test_whole_dict_node_reference(self) -> None:
        """A reference may denote a whole subtree, not just a leaf."""
        data = {
            "db": {"host": "localhost", "port": 5432},
            "replica": "${db}",
        }
        resolved = resolve_expressions(data)
        assert resolved["replica"] == {"host": "localhost", "port": 5432}

    def test_whole_list_node_reference(self) -> None:
        """A reference to a list node substitutes the whole list."""
        data = {"primary": ["a", "b"], "backup": "${primary}"}
        resolved = resolve_expressions(data)
        assert resolved["backup"] == ["a", "b"]

    def test_node_reference_aliases_the_source_node(self) -> None:
        """The substituted node is the live sub-dict, not a copy.

        Documented as a limitation: a caller that mutates a resolved dict in
        place reaches every path that referenced the mutated node.  Pinned so
        the aliasing cannot change silently.
        """
        data = {
            "db": {"host": "localhost", "port": 5432},
            "replica": "${db}",
        }
        resolved = resolve_expressions(data)
        assert resolved["replica"] is resolved["db"]

    def test_escape(self) -> None:
        """$${...} produces literal ${...}."""
        data = {"a": "$${not_a_ref}"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "${not_a_ref}"

    def test_nested_dict_refs(self) -> None:
        """An expression can reference nested dict fields."""
        data = {
            "db": {"host": "localhost", "port": 5432},
            "url": "jdbc://${db.host}:${db.port}/mydb",
        }
        resolved = resolve_expressions(data)
        assert resolved["url"] == "jdbc://localhost:5432/mydb"

    def test_cross_nested_ref(self) -> None:
        """An expression inside a nested dict can reference sibling fields."""
        data = {
            "db": {"host": "localhost", "port": 5432, "url": "jdbc://${db.host}:${db.port}/mydb"},
        }
        resolved = resolve_expressions(data)
        assert resolved["db"]["url"] == "jdbc://localhost:5432/mydb"

    def test_non_expression_strings_unchanged(self) -> None:
        """Plain strings without expressions are left unchanged."""
        data = {"a": "hello", "b": "world"}
        resolved = resolve_expressions(data)
        assert resolved == {"a": "hello", "b": "world"}

    def test_mixed_expressions_and_plain(self) -> None:
        """A mix of expression and plain fields resolves correctly."""
        data = {"a": "${b}", "b": 42, "c": "plain"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42
        assert resolved["c"] == "plain"

    def test_list_index_reference(self) -> None:
        """A list index reference resolves correctly."""
        data = {
            "servers": [{"host": "s1"}, {"host": "s2"}],
            "primary": "${servers[0].host}",
        }
        resolved = resolve_expressions(data)
        assert resolved["primary"] == "s1"

    def test_negative_list_index_reference(self) -> None:
        """A negative list index reference resolves correctly."""
        data = {
            "servers": [{"host": "s1"}, {"host": "s2"}],
            "last": "${servers[-1].host}",
        }
        resolved = resolve_expressions(data)
        assert resolved["last"] == "s2"

    def test_deeply_nested_path(self) -> None:
        """A deeply nested path reference resolves correctly."""
        data = {
            "a": {"b": {"c": {"d": 42}}},
            "result": "${a.b.c.d}",
        }
        resolved = resolve_expressions(data)
        assert resolved["result"] == 42


# ---------------------------------------------------------------------------
# Load with expressions (end-to-end)
# ---------------------------------------------------------------------------


@dataclass
class ExprDb:
    """Database config with an expression-based URL field."""

    host: str
    port: int
    url: str = ""


@dataclass
class ExprAppConfig:
    """Application config wrapping an ExprDb for expression tests."""

    db: ExprDb
    debug: bool = False


class TestLoadWithExpressions:
    """End-to-end via load() from TOML, YAML, env, CLI."""

    def test_toml_expression(self, tmp_toml) -> None:
        """Test that ${...} expressions in a TOML file are resolved end-to-end."""
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, argv=[], env={}, files=[path])
        assert result.db.url == "jdbc://localhost:5432/mydb"

    def test_yaml_expression(self, tmp_yaml) -> None:
        """Test that ${...} expressions in a YAML file are resolved end-to-end."""
        path = tmp_yaml("""\
            db:
              host: localhost
              port: 5432
              url: "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, argv=[], env={}, files=[path])
        assert result.db.url == "jdbc://localhost:5432/mydb"

    def test_env_expression(self) -> None:
        """Env var value with expression referencing another env-provided field."""

        @dataclass
        class Cfg:
            greeting: str = ""
            name: str = ""

        result = confarg.load(
            Cfg,
            argv=[],
            env={"MYAPP_GREETING": "hello", "MYAPP_NAME": "${greeting}"},
            env_prefix="MYAPP_",
        )
        assert result.name == "hello"

    def test_cli_expression(self) -> None:
        """CLI arg value with expression referencing another CLI-provided field."""

        @dataclass
        class Cfg:
            greeting: str = ""
            name: str = ""

        result = confarg.load(
            Cfg,
            argv=["--name", "${greeting}", "--greeting", "hello"],
            env={},
        )
        assert result.name == "hello"

    def test_cross_source_toml_cli(self, tmp_toml) -> None:
        """CLI value referenced by TOML expression."""
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        # Override host via CLI
        result = confarg.load(
            ExprAppConfig,
            argv=["--db.host", "prod-server"],
            env={},
            files=[path],
        )
        # CLI has higher priority, so db.host = "prod-server"
        # Expression references db.host which is now "prod-server"
        assert result.db.url == "jdbc://prod-server:5432/mydb"

    def test_merge_output_preserves_raw_expressions(self, tmp_toml) -> None:
        """Merge() preserves raw ${...} expressions without evaluating them."""
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "${db.host}"
        """)
        raw = confarg.merge(ExprAppConfig, argv=[], env={}, files=[path])
        assert raw["db"]["url"] == "${db.host}"

    def test_pure_expression_retains_type(self, tmp_toml) -> None:
        """A pure ${expr} preserving int type through load."""

        @dataclass
        class Cfg:
            a: int
            b: int = 0

        path = tmp_toml("""\
            a = 42
            b = "${a}"
        """)
        result = confarg.load(Cfg, argv=[], env={}, files=[path])
        assert result.b == 42
        assert isinstance(result.b, int)


# ---------------------------------------------------------------------------
# Cross-source interpolation
# ---------------------------------------------------------------------------


@dataclass
class CrossCfg:
    """Configuration for cross-source interpolation tests."""

    host: str = "localhost"
    port: int = 5432
    url: str = ""


class TestCrossSourceInterpolation:
    """${...} expressions in one source can reference values from a higher-priority source."""

    # --- right config → left config ---

    def test_right_config_value_interpolated_in_left_config(self, tmp_toml) -> None:
        """Expression in left file resolves a value defined only in right file."""
        left = tmp_toml('url = "jdbc://${host}"\n', "left.toml")
        right = tmp_toml('host = "prod"\nport = 5432\n', "right.toml")
        result = confarg.load(CrossCfg, argv=[], env={}, files=[left, right])
        assert result.url == "jdbc://prod"

    def test_right_config_overrides_then_referenced(self, tmp_toml) -> None:
        """Expression uses the right-config value when both files define the field."""
        left = tmp_toml('host = "dev"\nurl = "jdbc://${host}"\nport = 5432\n', "left.toml")
        right = tmp_toml('host = "prod"\n', "right.toml")
        result = confarg.load(CrossCfg, argv=[], env={}, files=[left, right])
        assert result.url == "jdbc://prod"  # right file's host wins

    # --- env var → config ---

    def test_env_value_interpolated_in_config(self, tmp_toml) -> None:
        """Config expression resolves a value supplied by an env var."""
        path = tmp_toml('url = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, argv=[], env={"MYAPP_HOST": "env-host"}, env_prefix="MYAPP_", files=[path])
        assert result.url == "jdbc://env-host"

    def test_env_overrides_config_value_used_in_expression(self, tmp_toml) -> None:
        """Env var overrides a config-file value; expression uses the env var version."""
        path = tmp_toml('host = "file-host"\nurl = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, argv=[], env={"MYAPP_HOST": "env-host"}, env_prefix="MYAPP_", files=[path])
        assert result.url == "jdbc://env-host"

    # --- CLI → config ---

    def test_cli_value_interpolated_in_config(self, tmp_toml) -> None:
        """Config expression resolves a value supplied via CLI."""
        path = tmp_toml('url = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, argv=["--host", "cli-host"], env={}, files=[path])
        assert result.url == "jdbc://cli-host"

    def test_cli_overrides_config_value_used_in_expression(self, tmp_toml) -> None:
        """CLI overrides a config-file value; expression uses the CLI version."""
        path = tmp_toml('host = "file-host"\nurl = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, argv=["--host", "cli-host"], env={}, files=[path])
        assert result.url == "jdbc://cli-host"

    # --- CLI → env var ---

    def test_cli_value_interpolated_in_env_expression(self) -> None:
        """Env var containing an expression resolves a value supplied via CLI."""
        result = confarg.load(
            CrossCfg,
            argv=["--host", "cli-host"],
            env={"MYAPP_URL": "jdbc://${host}", "MYAPP_PORT": "5432"},
            env_prefix="MYAPP_",
        )
        assert result.url == "jdbc://cli-host"

    # --- multi-source: CLI + env + config all contribute to one expression ---

    def test_expression_spans_three_sources(self, tmp_toml) -> None:
        """A config expression references values from env and CLI simultaneously."""
        path = tmp_toml('url = "jdbc://${host}:${port}/db"\n')
        result = confarg.load(
            CrossCfg,
            argv=["--host", "cli-host"],
            env={"MYAPP_PORT": "9999"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.url == "jdbc://cli-host:9999/db"


# ---------------------------------------------------------------------------
# Dump with expressions
# ---------------------------------------------------------------------------


class TestDump:
    """dump() always outputs resolved values."""

    def test_dump_resolved_values(self, tmp_toml) -> None:
        """Dump() outputs the resolved value, not the raw expression string."""
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, argv=[], env={}, files=[path])
        dumped = confarg.dump(result)
        assert dumped["db"]["url"] == "jdbc://localhost:5432/mydb"

    def test_dump_no_expressions_unchanged(self) -> None:
        """Dump() leaves values without expressions unchanged."""
        obj = WithDefaults(name="alice", count=1, rate=2.0, verbose=True)
        dumped = confarg.dump(obj)
        assert dumped == {"name": "alice", "count": 1, "rate": 2.0, "verbose": True}

    def test_dump_file_toml_resolved(self, tmp_toml, tmp_path) -> None:
        """Dump_file() writes resolved values without ${...} expressions."""
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, argv=[], env={}, files=[path])
        out_path = tmp_path / "out.toml"
        confarg.dump_file(result, out_path)
        content = out_path.read_text()
        assert "${db.host}" not in content
        assert "localhost" in content


# ---------------------------------------------------------------------------
# Expression errors
# ---------------------------------------------------------------------------


class TestExpressionErrors:
    """Circular, missing, unsafe, eval errors."""

    def test_circular_reference(self) -> None:
        """A two-field circular reference raises CircularReferenceError."""
        data = {"a": "${b}", "b": "${a}"}
        with pytest.raises(CircularReferenceError):
            resolve_expressions(data)

    def test_circular_three_way(self) -> None:
        """A three-field circular reference raises CircularReferenceError."""
        data = {"a": "${b}", "b": "${c}", "c": "${a}"}
        with pytest.raises(CircularReferenceError):
            resolve_expressions(data)

    def test_self_reference(self) -> None:
        """A self-referencing field raises CircularReferenceError."""
        data = {"a": "${a}"}
        with pytest.raises(CircularReferenceError):
            resolve_expressions(data)

    def test_missing_reference(self) -> None:
        """A reference to an undefined field raises MissingReferenceError."""
        data = {"a": "${nonexistent}"}
        with pytest.raises(MissingReferenceError):
            resolve_expressions(data)

    def test_missing_nested_reference(self) -> None:
        """A reference to a missing nested path raises MissingReferenceError."""
        data = {"a": "${x.y.z}"}
        with pytest.raises(MissingReferenceError):
            resolve_expressions(data)

    @pytest.mark.parametrize(
        "expr",
        [
            "${__import__('os').system('ls')}",
            "${eval('1+1')}",
            "${exec('x=1')}",
            "${(lambda: 1)()}",
            "${[x for x in [1,2,3]]}",
        ],
        ids=["import", "eval", "exec", "lambda", "comprehension"],
    )
    def test_unsafe_expression(self, expr: str) -> None:
        """Unsafe expression constructs raise UnsafeExpressionError during resolution."""
        data = {"a": expr}
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions(data)

    def test_dunder_access(self) -> None:
        """Accessing dunder attributes raises UnsafeExpressionError."""
        data = {"a": "${b.__class__}", "b": "hello"}
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions(data)

    def test_division_by_zero_error(self) -> None:
        """Division by zero raises ExpressionEvalError."""
        data = {"a": "${b / 0}", "b": 10}
        with pytest.raises(ExpressionEvalError):
            resolve_expressions(data)

    def test_type_error_in_expression(self) -> None:
        """A type error in an expression raises ExpressionEvalError."""
        data = {"a": "${b + c}", "b": "hello", "c": 42}
        with pytest.raises(ExpressionEvalError):
            resolve_expressions(data)

    def test_unknown_function(self) -> None:
        """Calling a non-whitelisted function raises UnsafeExpressionError."""
        data = {"a": "${open('foo')}"}
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions(data)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestExpressionEdgeCases:
    """Empty strings, $foo without braces, multiple ${...}, None, lists, deeply nested."""

    def test_empty_string(self) -> None:
        """An empty string is left unchanged."""
        data = {"a": ""}
        resolved = resolve_expressions(data)
        assert resolved["a"] == ""

    def test_dollar_without_braces(self) -> None:
        """$foo is NOT treated as an expression."""
        data = {"a": "$foo"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "$foo"

    def test_multiple_expressions_in_one_string(self) -> None:
        """Multiple expressions in one string are all resolved."""
        data = {"a": "${x}-${y}", "x": "hello", "y": "world"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "hello-world"

    def test_none_value_unchanged(self) -> None:
        """A None value is left unchanged while expressions are resolved."""
        data = {"a": None, "b": "${c}", "c": 42}
        resolved = resolve_expressions(data)
        assert resolved["a"] is None
        assert resolved["b"] == 42

    def test_no_expressions_returns_same_object(self) -> None:
        """Invariant: resolve_expressions returns the *same* dict object (not a copy).

        When there are no ${...} expressions present, the early-exit path returns
        data unchanged — callers must not rely on always receiving a fresh copy.
        """
        data = {"host": "localhost", "port": 5432, "enabled": True}
        result = resolve_expressions(data)
        assert result is data

    def test_no_expressions_empty_dict_returns_same_object(self) -> None:
        """Empty dict with no expressions: same object identity guaranteed."""
        data: dict = {}
        result = resolve_expressions(data)
        assert result is data

    def test_with_expressions_returns_new_object(self) -> None:
        """When expressions are present, resolve_expressions returns a deep copy.

        The returned dict is a different object, not the original dict.
        """
        data = {"a": "${b}", "b": "hello"}
        result = resolve_expressions(data)
        assert result is not data

    def test_input_dict_not_mutated(self) -> None:
        """resolve_expressions must not modify the caller's dict."""
        data = {"host": "localhost", "url": "${host}:8080"}
        original = {"host": "localhost", "url": "${host}:8080"}
        resolve_expressions(data)
        assert data == original

    def test_input_dict_not_mutated_nested(self) -> None:
        """Nested dicts are also not mutated."""
        data = {"db": {"host": "localhost", "url": "${db.host}:5432"}}
        original_inner = dict(data["db"])
        resolve_expressions(data)
        assert data["db"] == original_inner

    def test_bool_value_unchanged(self) -> None:
        """Boolean values are left unchanged during expression resolution."""
        data = {"a": True, "b": False}
        resolved = resolve_expressions(data)
        assert resolved["a"] is True
        assert resolved["b"] is False

    def test_integer_value_unchanged(self) -> None:
        """Integer values are left unchanged during expression resolution."""
        data = {"a": 42}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42

    def test_expression_referencing_list(self) -> None:
        """Can reference a list value."""
        data = {"items": [1, 2, 3], "count": "${len(items)}"}
        resolved = resolve_expressions(data)
        assert resolved["count"] == 3

    def test_deeply_nested_expression_path(self) -> None:
        """An expression referencing a deeply nested path resolves correctly."""
        data = {
            "level1": {"level2": {"level3": {"value": 42}}},
            "result": "${level1.level2.level3.value}",
        }
        resolved = resolve_expressions(data)
        assert resolved["result"] == 42

    def test_string_concat_via_interpolation(self) -> None:
        """String concatenation via interpolation works correctly."""
        data = {"first": "John", "last": "Doe", "full": "${first} ${last}"}
        resolved = resolve_expressions(data)
        assert resolved["full"] == "John Doe"

    def test_escaped_in_middle(self) -> None:
        """An escaped expression in the middle of a string is unescaped."""
        data = {"a": "before$${escaped}after"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "before${escaped}after"

    def test_mixed_escaped_and_real_in_string(self) -> None:
        """A mix of escaped and real expressions in one string works correctly."""
        data = {"a": "$${esc}${b}", "b": "real"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "${esc}real"

    def test_expression_with_string_literal(self) -> None:
        """Expressions with string literals concatenate correctly."""
        data = {"a": '${b + " world"}', "b": "hello"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "hello world"

    def test_constant_expression(self) -> None:
        """Pure constant expression (no refs)."""
        data = {"a": "${42}"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42


# ---------------------------------------------------------------------------
# Bug-fix regression tests
# ---------------------------------------------------------------------------


class TestExpressionBugFixes:
    """Regression tests for bugs fixed in the expression engine."""

    # Bug: _scan_expressions skipped list values entirely
    def test_expression_inside_list_is_resolved(self) -> None:
        """Expressions inside list elements are resolved end-to-end."""
        data = {"host": "localhost", "endpoints": ["${host}:8080", "static"]}
        resolved = resolve_expressions(data)
        assert resolved["endpoints"][0] == "localhost:8080"
        assert resolved["endpoints"][1] == "static"

    def test_expression_inside_nested_list_is_resolved(self) -> None:
        """Expressions inside a list of dicts are resolved."""
        data = {
            "base": "prod",
            "servers": [{"env": "${base}"}, {"env": "dev"}],
        }
        resolved = resolve_expressions(data)
        assert resolved["servers"][0]["env"] == "prod"
        assert resolved["servers"][1]["env"] == "dev"

    def test_end_to_end_expression_in_list(self) -> None:
        """load() resolves ${...} expressions that appear inside a list field."""

        @dataclass
        class Cfg:
            host: str = "localhost"
            endpoints: list[str] = field(default_factory=list)

        result = confarg.load(
            Cfg,
            argv=["--host", "prod", "--endpoints", "${host}:8080", "other"],
            env={},
        )
        assert result.endpoints[0] == "prod:8080"
        assert result.endpoints[1] == "other"


class TestReservedNamesInExpressions:
    """Names the expression engine must resolve from the config, not from Python."""

    def test_locals_is_not_a_safe_function(self) -> None:
        """``locals`` is a Python builtin but not whitelisted, so it stays a config path."""
        assert "locals" not in _SAFE_FUNCTIONS

    def test_locals_path_resolves_from_the_namespace(self) -> None:
        """${locals.k} reads the reserved namespace rather than Python's locals()."""
        result = resolve_expressions({"locals": {"k": 3}, "n": "${locals.k * 2}"})
        assert result["n"] == 6


# ---------------------------------------------------------------------------
# Anchor marker lexing
# ---------------------------------------------------------------------------


class TestAnchorMarkerLexing:
    """``(offset, length, levels)`` for each marker that begins an operand.

    The scan is lexical rather than a regex because a dot belongs to whatever token
    the tokenizer put it in.  Two details bite: Python tokenizes ``...`` as one
    ellipsis token while ``..`` arrives as two dots, and a ``::`` is a slice step
    inside a subscript but a root marker anywhere else.
    """

    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            pytest.param(".host", [(0, 1, 1)], id="one-dot"),
            pytest.param("..host", [(0, 2, 2)], id="two-dots"),
            pytest.param("...host", [(0, 3, 3)], id="three-dots-is-one-ellipsis-token"),
            pytest.param("....host", [(0, 4, 4)], id="four-dots-spans-both"),
            pytest.param("::name", [(0, 2, 0)], id="root"),
            pytest.param("a.b", [], id="ordinary-attribute"),
            pytest.param("1.5 + n", [], id="inside-float"),
            pytest.param("'a.b'.upper()", [], id="after-string-literal"),
            pytest.param("str(n)[0].upper()", [], id="after-closing-bracket"),
            pytest.param("n if .name else 0", [(5, 1, 1)], id="after-keyword"),
            pytest.param("min(.a, ::b)", [(4, 1, 1), (8, 2, 0)], id="both-inside-a-call"),
        ],
    )
    def test_markers(self, expr: str, expected: list[tuple[int, int, int]]) -> None:
        """Each case pins one way a marker is or is not spelled."""
        assert _anchor_markers(expr) == expected

    def test_double_colon_in_a_subscript_is_a_slice(self) -> None:
        """``items[::2]`` keeps its slice reading, so widening the grammar stays possible."""
        assert _anchor_markers("items[::2]") == []

    def test_parentheses_reopen_the_root_marker_inside_a_subscript(self) -> None:
        """The documented escape hatch: parenthesise to reach the root within brackets."""
        assert _anchor_markers("items[(::step)]") == [(7, 2, 0)]

    def test_a_slice_is_still_refused(self) -> None:
        """Nothing here makes slices legal; they remain outside the whitelist."""
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions({"items": [1, 2, 3], "n": "${items[::2]}"})


class TestAnchorNameRoundTrip:
    """Markers become stand-in names to parse, and must come back out unchanged.

    ``prefix_references`` unparses a rewritten tree, so a dumped configuration that
    still carries ``${.host}`` only survives being re-included if this round-trips.
    """

    @pytest.mark.parametrize(
        "expr",
        [".host", "..host", "...host", "::name", "min(.a, ::b) + n", "x.upper()"],
    )
    def test_round_trip(self, expr: str) -> None:
        """Naming the markers and unnaming them is the identity."""
        assert _unname_anchor(_name_anchor(expr)) == expr

    def test_mounting_leaves_anchored_references_alone(self) -> None:
        """Only a bare name is file-anchored, so only a bare name takes the prefix."""
        assert _prefix_content("host", "db") == "db.host"
        assert _prefix_content(".host", "db") == ".host"
        assert _prefix_content("..host", "db") == "..host"
        assert _prefix_content("::name", "db") == "::name"


class TestAnchorDepthArithmetic:
    """One dot drops the value's own key; each further dot drops one more segment."""

    @pytest.mark.parametrize(
        ("node_path", "levels", "expected"),
        [
            pytest.param("dbs.0.url", 1, "dbs.0.", id="sibling-in-a-list-element"),
            pytest.param("dbs.0.url", 2, "dbs.", id="the-list-itself"),
            pytest.param("dbs.0.url", 3, "", id="document-root"),
            pytest.param("a", 1, "", id="already-at-the-root"),
        ],
    )
    def test_prefix(self, node_path: str, levels: int, expected: str) -> None:
        """A list index is an ordinary segment, as it is everywhere else."""
        assert _anchor_prefix(node_path, levels) == expected

    def test_climbing_past_the_root_is_an_error(self) -> None:
        """The message names the run, the depth it had, and the way out."""
        with pytest.raises(MissingReferenceError, match=r"above the document root"):
            _anchor_prefix("a", 2)

    def test_a_non_identifier_key_is_still_addressable(self) -> None:
        """The absolute path is built as a tree, so ``web-1`` never has to parse."""
        data = {"svc": {"web-1": {"host": "h", "url": "x://${.host}"}}}
        assert resolve_expressions(data)["svc"]["web-1"]["url"] == "x://h"
