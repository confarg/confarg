# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for field references and expressions (${...} syntax)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest

import confarg
from confarg._errors import (
    CircularReferenceError,
    ExpressionEvalError,
    MissingReferenceError,
    UnsafeExpressionError,
)
from confarg.dictexpr._expressions import (
    _extract_references,
    _scan_expressions,
    _topological_sort,
    _validate_ast,
    resolve_expressions,
)
from tests.conftest import (
    WithDefaults,
)

# ---------------------------------------------------------------------------
# Scan expressions
# ---------------------------------------------------------------------------


class TestScanExpressions:
    """Detection of ${...} in merged dicts."""

    def test_simple_reference(self) -> None:
        data = {"a": "${b}", "b": "hello"}
        result = _scan_expressions(data)
        assert result == {"a": "${b}"}

    def test_nested_dict(self) -> None:
        data = {"db": {"url": "jdbc://${db.host}:${db.port}/mydb", "host": "localhost", "port": 5432}}
        result = _scan_expressions(data)
        assert result == {"db.url": "jdbc://${db.host}:${db.port}/mydb"}

    def test_non_string_ignored(self) -> None:
        data = {"count": 42, "rate": math.pi, "flag": True, "nothing": None}
        result = _scan_expressions(data)
        assert result == {}

    def test_no_expressions(self) -> None:
        data = {"name": "hello", "nested": {"value": "world"}}
        result = _scan_expressions(data)
        assert result == {}

    def test_escaped_not_detected(self) -> None:
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
        data = {"a": {"b": {"c": {"d": "${x}"}}}}
        result = _scan_expressions(data)
        assert result == {"a.b.c.d": "${x}"}

    def test_multiple_expressions(self) -> None:
        data = {"a": "${x}", "b": "${y}", "c": "plain"}
        result = _scan_expressions(data)
        assert result == {"a": "${x}", "b": "${y}"}


# ---------------------------------------------------------------------------
# Extract references
# ---------------------------------------------------------------------------


class TestExtractReferences:
    """Extracting dotted field paths from expression strings."""

    def test_simple_name(self) -> None:
        refs = _extract_references("${name}")
        assert refs == {"name"}

    def test_dotted_path(self) -> None:
        refs = _extract_references("${db.host}")
        assert refs == {"db.host"}

    def test_multiple_refs(self) -> None:
        refs = _extract_references("jdbc://${db.host}:${db.port}/mydb")
        assert refs == {"db.host", "db.port"}

    def test_arithmetic_expr(self) -> None:
        refs = _extract_references("${db.port + 1000}")
        assert refs == {"db.port"}

    def test_function_call(self) -> None:
        refs = _extract_references("${max(a, b)}")
        assert refs == {"a", "b"}

    def test_no_refs_in_escaped(self) -> None:
        refs = _extract_references("$${not_a_ref}")
        assert refs == set()

    def test_mixed_escaped_and_real(self) -> None:
        refs = _extract_references("$${escape}${real}")
        assert refs == {"real"}

    def test_string_literal_not_a_ref(self) -> None:
        refs = _extract_references('${db.host + ":"}')
        assert refs == {"db.host"}

    def test_list_index_ref(self) -> None:
        refs = _extract_references("${servers[0].host}")
        assert refs == {"servers.0.host"}


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    """Dependency ordering and circular detection."""

    def test_simple_chain(self) -> None:
        deps = {"c": {"b"}, "b": {"a"}, "a": set()}
        order = _topological_sort(deps)
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_independent(self) -> None:
        deps = {"a": set(), "b": set()}
        order = _topological_sort(deps)
        assert set(order) == {"a", "b"}

    def test_diamond(self) -> None:
        deps = {"d": {"b", "c"}, "b": {"a"}, "c": {"a"}, "a": set()}
        order = _topological_sort(deps)
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_circular_raises(self) -> None:
        deps = {"a": {"b"}, "b": {"a"}}
        with pytest.raises(CircularReferenceError):
            _topological_sort(deps)

    def test_self_reference_raises(self) -> None:
        deps = {"a": {"a"}}
        with pytest.raises(CircularReferenceError):
            _topological_sort(deps)

    def test_circular_three(self) -> None:
        deps = {"a": {"c"}, "b": {"a"}, "c": {"b"}}
        with pytest.raises(CircularReferenceError):
            _topological_sort(deps)

    def test_empty(self) -> None:
        assert _topological_sort({}) == []


# ---------------------------------------------------------------------------
# AST validation
# ---------------------------------------------------------------------------


class TestAstValidation:
    """Safety: allowed ops pass, disallowed constructs rejected."""

    def test_simple_name(self) -> None:
        _validate_ast("x")

    def test_dotted_name(self) -> None:
        _validate_ast("x.y")

    def test_arithmetic(self) -> None:
        _validate_ast("x + 1")
        _validate_ast("x * 2 - 3")
        _validate_ast("x / y")
        _validate_ast("x // y")
        _validate_ast("x % y")
        _validate_ast("x ** 2")

    def test_comparison(self) -> None:
        _validate_ast("x > 0")
        _validate_ast("x == y")

    def test_boolean(self) -> None:
        _validate_ast("x and y")
        _validate_ast("not x")

    def test_ternary(self) -> None:
        _validate_ast("x if x > 0 else y")

    def test_function_call(self) -> None:
        _validate_ast("max(x, y)")
        _validate_ast("abs(x)")
        _validate_ast("len(name)")

    def test_string_method(self) -> None:
        _validate_ast("name.upper()")
        _validate_ast("name.replace('a', 'b')")

    def test_subscript(self) -> None:
        _validate_ast("x[0]")

    def test_constant(self) -> None:
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
        data = {"a": expr, **ctx}
        resolved = resolve_expressions(data)
        assert resolved["a"] == expected

    def test_division_by_zero(self) -> None:
        data = {"a": "${b / 0}", "b": 10}
        with pytest.raises(ExpressionEvalError, match="division"):
            resolve_expressions(data)


# ---------------------------------------------------------------------------
# Resolve expressions (full resolution on raw dicts)
# ---------------------------------------------------------------------------


class TestResolveExpressions:
    """Full resolution: field refs, interpolation, chaining, escaping, resolve=False."""

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

    def test_escape(self) -> None:
        """$${...} produces literal ${...}."""
        data = {"a": "$${not_a_ref}"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "${not_a_ref}"

    def test_nested_dict_refs(self) -> None:
        data = {
            "db": {"host": "localhost", "port": 5432},
            "url": "jdbc://${db.host}:${db.port}/mydb",
        }
        resolved = resolve_expressions(data)
        assert resolved["url"] == "jdbc://localhost:5432/mydb"

    def test_cross_nested_ref(self) -> None:
        data = {
            "db": {"host": "localhost", "port": 5432, "url": "jdbc://${db.host}:${db.port}/mydb"},
        }
        resolved = resolve_expressions(data)
        assert resolved["db"]["url"] == "jdbc://localhost:5432/mydb"

    def test_non_expression_strings_unchanged(self) -> None:
        data = {"a": "hello", "b": "world"}
        resolved = resolve_expressions(data)
        assert resolved == {"a": "hello", "b": "world"}

    def test_mixed_expressions_and_plain(self) -> None:
        data = {"a": "${b}", "b": 42, "c": "plain"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42
        assert resolved["c"] == "plain"

    def test_list_index_reference(self) -> None:
        data = {
            "servers": [{"host": "s1"}, {"host": "s2"}],
            "primary": "${servers[0].host}",
        }
        resolved = resolve_expressions(data)
        assert resolved["primary"] == "s1"

    def test_deeply_nested_path(self) -> None:
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
    host: str
    port: int
    url: str = ""


@dataclass
class ExprAppConfig:
    db: ExprDb
    debug: bool = False


class TestLoadWithExpressions:
    """End-to-end via load() from TOML, YAML, env, CLI."""

    def test_toml_expression(self, tmp_toml) -> None:
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, args=[], env={}, files=[path])
        assert result.db.url == "jdbc://localhost:5432/mydb"

    def test_yaml_expression(self, tmp_yaml) -> None:
        path = tmp_yaml("""\
            db:
              host: localhost
              port: 5432
              url: "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, args=[], env={}, files=[path])
        assert result.db.url == "jdbc://localhost:5432/mydb"

    def test_env_expression(self) -> None:
        """Env var value with expression referencing another env-provided field."""

        @dataclass
        class Cfg:
            greeting: str = ""
            name: str = ""

        result = confarg.load(
            Cfg,
            args=[],
            env={"GREETING": "hello", "NAME": "${greeting}"},
            env_prefix="",
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
            args=["--name", "${greeting}", "--greeting", "hello"],
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
            args=["--db.host", "prod-server"],
            env={},
            files=[path],
        )
        # CLI has higher priority, so db.host = "prod-server"
        # Expression references db.host which is now "prod-server"
        assert result.db.url == "jdbc://prod-server:5432/mydb"

    def test_merge_output_preserves_raw_expressions(self, tmp_toml) -> None:
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "${db.host}"
        """)
        raw = confarg.merge(ExprAppConfig, args=[], env={}, files=[path])
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
        result = confarg.load(Cfg, args=[], env={}, files=[path])
        assert result.b == 42
        assert isinstance(result.b, int)


# ---------------------------------------------------------------------------
# Cross-source interpolation
# ---------------------------------------------------------------------------


@dataclass
class CrossCfg:
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
        result = confarg.load(CrossCfg, args=[], env={}, files=[left, right])
        assert result.url == "jdbc://prod"

    def test_right_config_overrides_then_referenced(self, tmp_toml) -> None:
        """Expression uses the right-config value when both files define the field."""
        left = tmp_toml('host = "dev"\nurl = "jdbc://${host}"\nport = 5432\n', "left.toml")
        right = tmp_toml('host = "prod"\n', "right.toml")
        result = confarg.load(CrossCfg, args=[], env={}, files=[left, right])
        assert result.url == "jdbc://prod"  # right file's host wins

    # --- env var → config ---

    def test_env_value_interpolated_in_config(self, tmp_toml) -> None:
        """Config expression resolves a value supplied by an env var."""
        path = tmp_toml('url = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, args=[], env={"HOST": "env-host"}, env_prefix="", files=[path])
        assert result.url == "jdbc://env-host"

    def test_env_overrides_config_value_used_in_expression(self, tmp_toml) -> None:
        """Env var overrides a config-file value; expression uses the env var version."""
        path = tmp_toml('host = "file-host"\nurl = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, args=[], env={"HOST": "env-host"}, env_prefix="", files=[path])
        assert result.url == "jdbc://env-host"

    # --- CLI → config ---

    def test_cli_value_interpolated_in_config(self, tmp_toml) -> None:
        """Config expression resolves a value supplied via CLI."""
        path = tmp_toml('url = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, args=["--host", "cli-host"], env={}, files=[path])
        assert result.url == "jdbc://cli-host"

    def test_cli_overrides_config_value_used_in_expression(self, tmp_toml) -> None:
        """CLI overrides a config-file value; expression uses the CLI version."""
        path = tmp_toml('host = "file-host"\nurl = "jdbc://${host}"\nport = 5432\n')
        result = confarg.load(CrossCfg, args=["--host", "cli-host"], env={}, files=[path])
        assert result.url == "jdbc://cli-host"

    # --- CLI → env var ---

    def test_cli_value_interpolated_in_env_expression(self) -> None:
        """Env var containing an expression resolves a value supplied via CLI."""
        result = confarg.load(
            CrossCfg,
            args=["--host", "cli-host"],
            env={"URL": "jdbc://${host}", "PORT": "5432"},
            env_prefix="",
        )
        assert result.url == "jdbc://cli-host"

    # --- multi-source: CLI + env + config all contribute to one expression ---

    def test_expression_spans_three_sources(self, tmp_toml) -> None:
        """A config expression references values from env and CLI simultaneously."""
        path = tmp_toml('url = "jdbc://${host}:${port}/db"\n')
        result = confarg.load(
            CrossCfg,
            args=["--host", "cli-host"],
            env={"PORT": "9999"},
            env_prefix="",
            files=[path],
        )
        assert result.url == "jdbc://cli-host:9999/db"


# ---------------------------------------------------------------------------
# Dump with expressions
# ---------------------------------------------------------------------------


class TestDump:
    """dump() always outputs resolved values."""

    def test_dump_resolved_values(self, tmp_toml) -> None:
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, args=[], env={}, files=[path])
        dumped = confarg.dump(result)
        assert dumped["db"]["url"] == "jdbc://localhost:5432/mydb"

    def test_dump_no_expressions_unchanged(self) -> None:
        obj = WithDefaults(name="alice", count=1, rate=2.0, verbose=True)
        dumped = confarg.dump(obj)
        assert dumped == {"name": "alice", "count": 1, "rate": 2.0, "verbose": True}

    def test_dump_file_toml_resolved(self, tmp_toml, tmp_path) -> None:
        path = tmp_toml("""\
            [db]
            host = "localhost"
            port = 5432
            url = "jdbc://${db.host}:${db.port}/mydb"
        """)
        result = confarg.load(ExprAppConfig, args=[], env={}, files=[path])
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
        data = {"a": "${b}", "b": "${a}"}
        with pytest.raises(CircularReferenceError):
            resolve_expressions(data)

    def test_circular_three_way(self) -> None:
        data = {"a": "${b}", "b": "${c}", "c": "${a}"}
        with pytest.raises(CircularReferenceError):
            resolve_expressions(data)

    def test_self_reference(self) -> None:
        data = {"a": "${a}"}
        with pytest.raises(CircularReferenceError):
            resolve_expressions(data)

    def test_missing_reference(self) -> None:
        data = {"a": "${nonexistent}"}
        with pytest.raises(MissingReferenceError):
            resolve_expressions(data)

    def test_missing_nested_reference(self) -> None:
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
        data = {"a": expr}
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions(data)

    def test_dunder_access(self) -> None:
        data = {"a": "${b.__class__}", "b": "hello"}
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions(data)

    def test_division_by_zero_error(self) -> None:
        data = {"a": "${b / 0}", "b": 10}
        with pytest.raises(ExpressionEvalError):
            resolve_expressions(data)

    def test_type_error_in_expression(self) -> None:
        data = {"a": "${b + c}", "b": "hello", "c": 42}
        with pytest.raises(ExpressionEvalError):
            resolve_expressions(data)

    def test_unknown_function(self) -> None:
        data = {"a": "${open('foo')}"}
        with pytest.raises(UnsafeExpressionError):
            resolve_expressions(data)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestExpressionEdgeCases:
    """Empty strings, $foo without braces, multiple ${...}, None, lists, deeply nested."""

    def test_empty_string(self) -> None:
        data = {"a": ""}
        resolved = resolve_expressions(data)
        assert resolved["a"] == ""

    def test_dollar_without_braces(self) -> None:
        """$foo is NOT treated as an expression."""
        data = {"a": "$foo"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "$foo"

    def test_multiple_expressions_in_one_string(self) -> None:
        data = {"a": "${x}-${y}", "x": "hello", "y": "world"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "hello-world"

    def test_none_value_unchanged(self) -> None:
        data = {"a": None, "b": "${c}", "c": 42}
        resolved = resolve_expressions(data)
        assert resolved["a"] is None
        assert resolved["b"] == 42

    def test_no_expressions_returns_same_object(self) -> None:
        """Invariant: resolve_expressions returns the *same* dict object (not a copy)
        when there are no ${...} expressions present.

        The early-exit path at line 139 (``if not expr_fields: return data``) returns
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
        """When expressions are present, resolve_expressions returns a deep copy
        (a different object), not the original dict."""
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
        data = {"a": True, "b": False}
        resolved = resolve_expressions(data)
        assert resolved["a"] is True
        assert resolved["b"] is False

    def test_integer_value_unchanged(self) -> None:
        data = {"a": 42}
        resolved = resolve_expressions(data)
        assert resolved["a"] == 42

    def test_expression_referencing_list(self) -> None:
        """Can reference a list value."""
        data = {"items": [1, 2, 3], "count": "${len(items)}"}
        resolved = resolve_expressions(data)
        assert resolved["count"] == 3

    def test_deeply_nested_expression_path(self) -> None:
        data = {
            "level1": {"level2": {"level3": {"value": 42}}},
            "result": "${level1.level2.level3.value}",
        }
        resolved = resolve_expressions(data)
        assert resolved["result"] == 42

    def test_string_concat_via_interpolation(self) -> None:
        data = {"first": "John", "last": "Doe", "full": "${first} ${last}"}
        resolved = resolve_expressions(data)
        assert resolved["full"] == "John Doe"

    def test_escaped_in_middle(self) -> None:
        data = {"a": "before$${escaped}after"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "before${escaped}after"

    def test_mixed_escaped_and_real_in_string(self) -> None:
        data = {"a": "$${esc}${b}", "b": "real"}
        resolved = resolve_expressions(data)
        assert resolved["a"] == "${esc}real"

    def test_expression_with_string_literal(self) -> None:
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
            args=["--host", "prod", "--endpoints", "${host}:8080", "other"],
            env={},
        )
        assert result.endpoints[0] == "prod:8080"
        assert result.endpoints[1] == "other"
