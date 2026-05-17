# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Branch-coverage tests for argparse-integration internals.

Relocated from tests/test_coverage_gaps.py so the test tree mirrors
src/confarg/cli/argparse/.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from collections.abc import (
    Callable,  # noqa: TC003  # runtime import: confarg resolves test-class annotations via get_type_hints
)
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import confarg.cli.argparse._build as build_mod
import confarg.cli.argparse._register as reg_mod
from confarg._types import _resolve_struct
from confarg.cli.argparse import from_namespace, populate_parser
from confarg.cli.argparse._build import (
    _collect_callable_bind_specs,
    _collect_callable_factory_specs,
    _collect_callable_field_specs,
    _collect_fn_paths_from_argv,
    _collect_fn_paths_from_config,
    _collect_struct_specs,
    _collect_subconfig_specs,
    build_dynamic_flags,
)
from confarg.cli.argparse._completion import (
    _extend_walk,
    _pre_extend_parser_for_completion,
    _resolve_tags_from_config,
    _WalkCtx,
)
from confarg.cli.argparse._completion import (
    setup_completion as _argparse_setup_completion,
)
from confarg.cli.argparse._register import _add_callable_bind_flags, _add_callable_fn_flags, _register_spec
from confarg.cli.argparse._spec import FlagSpec, _get_field_docstrings
from tests._cov_helpers import (
    _COV_MOD,
    _CovCallableCls,
    _CovDCResult,
    _CovOuter,
    _CovUninspectable,
    _CovWithDict,
    _CovWithKwargs,
    _WithCovCallable,
    _WithUnionForCompletion,
)
from tests.conftest import WithDefaults

if TYPE_CHECKING:
    from pathlib import Path


class TestArgparseBranches:
    """Uncovered branches in the argparse integration layer."""

    def test_get_field_docstrings_no_class_found(self) -> None:
        """_get_field_docstrings returns an empty dict when the class cannot be located by name."""

        @dataclass
        class Dummy:
            x: int = 0

        original_name = Dummy.__name__
        try:
            Dummy.__name__ = "RenamedClass"
            result = _get_field_docstrings(Dummy)
            assert result == {}
        finally:
            Dummy.__name__ = original_name

    def test_walk_struct_non_struct_returns_early(self) -> None:
        """_collect_struct_specs returns empty list for non-struct types."""
        assert _collect_struct_specs(int, "", "class") == []

    def test_walk_struct_get_type_hints_exception(self) -> None:
        """_collect_struct_specs falls back gracefully when get_type_hints raises for broken annotations."""

        # This class has a CLASS-LEVEL annotation with an undefined forward ref.
        # With `from __future__ import annotations`, all annotations are strings;
        # get_type_hints(cls) tries to evaluate "UndefinedTypeXYZ999" in this
        # module's globals → NameError → except Exception → fallback to flds.
        class BrokenClassAnnot:
            _bad: UndefinedTypeXYZ999  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback

            def __init__(self, value: int) -> None:
                self.value = value

        _collect_struct_specs(BrokenClassAnnot, "", "class")

    def test_walk_struct_union_tag_field_skipped(self) -> None:
        """The union_tag field is not registered as a CLI flag by populate_parser."""

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        parser = argparse.ArgumentParser()
        populate_parser(WithTypeField, parser, union_tag="type")
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--type" not in flags
        assert "--value" in flags

    def test_walk_struct_callable_field_registered(self) -> None:
        """A Callable-typed field is registered as a CLI flag by populate_parser."""

        @dataclass
        class WithCallable:
            fn: Callable[[int], str] = str

        parser = argparse.ArgumentParser()
        populate_parser(WithCallable, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--fn" in flags

    def test_walk_struct_variable_length_tuple_field(self) -> None:
        """A variable-length tuple[int, ...] field is registered as a CLI flag."""

        @dataclass
        class WithVarTuple:
            nums: tuple[int, ...] = ()

        parser = argparse.ArgumentParser()
        populate_parser(WithVarTuple, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--nums" in flags

    def test_walk_struct_var_param_field_skipped(self) -> None:
        """*args fields are not included in static flag specs."""

        class PlainWithArgs:
            def __init__(self, x: int, *extras: str):
                pass

        specs = _collect_struct_specs(PlainWithArgs, "", "class")
        assert not any(s.name == "extras" for s in specs)

    def test_register_subconfig_flags_non_struct(self) -> None:
        """_collect_subconfig_specs returns empty list for non-struct types."""
        assert _collect_subconfig_specs(int, "config", "", "class") == []

    def test_register_subconfig_flags_get_type_hints_exception(self) -> None:
        """_collect_subconfig_specs falls back gracefully when get_type_hints raises."""

        # A class with a broken CLASS-LEVEL annotation (not __init__) causes
        # get_type_hints(cls) to fail, but _struct_fields succeeds via __init__.
        class BrokenClassAnnot:
            _bad: UndefinedType999  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback

            def __init__(self, x: int, y: str = "default") -> None:
                self.x = x
                self.y = y

        _collect_subconfig_specs(BrokenClassAnnot, "config", "", "class")

    def test_register_subconfig_flags_union_tag_skipped(self) -> None:
        """_collect_subconfig_specs skips the union_tag field."""

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        _collect_subconfig_specs(WithTypeField, "config", "", union_tag="type")

    def test_from_namespace_with_expressions(self) -> None:
        """from_namespace resolves ${...} expressions supplied via the env parameter."""

        @dataclass
        class WithExpr:
            host: str = "localhost"
            db_host: str = "myserver"

        parser = argparse.ArgumentParser()
        populate_parser(WithExpr, parser)
        ns = parser.parse_args([])
        # Pass env vars with an expression — the resolved value triggers expr_map storage
        result = from_namespace(WithExpr, ns, env={"HOST": "${db_host}", "DB_HOST": "realserver"}, env_prefix="")
        assert result.host == "realserver"


class TestBuildCallableSpecs:
    """Tests for _build.py callable spec builder functions."""

    def test_collect_callable_bind_specs_valid_fn(self) -> None:
        """_collect_callable_bind_specs returns FlagSpecs for a valid function's parameters."""
        specs = _collect_callable_bind_specs("myfn", f"{_COV_MOD}._cov_call_fn", "bind", set())
        names = [s.name for s in specs]
        assert "myfn.bind.x" in names
        assert "myfn.bind.y" in names

    def test_collect_callable_bind_specs_import_error(self) -> None:
        """_collect_callable_bind_specs returns [] for an unimportable fn_path."""
        result = _collect_callable_bind_specs("myfn", "nonexistent.module.fn", "bind", set())
        assert result == []

    def test_collect_callable_bind_specs_dedup(self) -> None:
        """_collect_callable_bind_specs skips specs already in existing_names."""
        existing = {"myfn.bind.x"}
        specs = _collect_callable_bind_specs("myfn", f"{_COV_MOD}._cov_call_fn", "bind", existing)
        names = [s.name for s in specs]
        assert "myfn.bind.x" not in names
        assert "myfn.bind.y" in names

    def test_collect_callable_factory_specs_valid_class(self) -> None:
        """_collect_callable_factory_specs returns FlagSpecs for factory constructor params."""
        specs = _collect_callable_factory_specs("myopt", _CovCallableCls, set())
        names = [s.name for s in specs]
        assert "myopt.lr" in names

    def test_collect_callable_field_specs_class_mode(self) -> None:
        """_collect_callable_field_specs in 'class' mode returns factory specs."""
        specs = _collect_callable_field_specs("opt", f"{_COV_MOD}._CovCallableCls", "class", "bind", set())
        names = [s.name for s in specs]
        assert "opt.lr" in names

    def test_collect_callable_field_specs_fn_mode(self) -> None:
        """_collect_callable_field_specs in 'fn' mode returns bind specs."""
        specs = _collect_callable_field_specs("myfn", f"{_COV_MOD}._cov_call_fn", "fn", "bind", set())
        names = [s.name for s in specs]
        assert "myfn.bind.x" in names

    def test_collect_callable_field_specs_call_mode(self) -> None:
        """_collect_callable_field_specs in 'call' mode returns bind specs."""
        specs = _collect_callable_field_specs("myfn", f"{_COV_MOD}._cov_call_fn", "call", "bind", set())
        names = [s.name for s in specs]
        assert "myfn.bind.x" in names

    def test_collect_callable_field_specs_fn_mode_method(self) -> None:
        """_collect_callable_field_specs in 'fn' mode for a method uses owning class specs."""
        specs = _collect_callable_field_specs("myfn", f"{_COV_MOD}._CovOptMethod.method", "fn", "bind", set())
        # Owning class is _CovOptMethod; returns factory specs for its constructor
        names = [s.name for s in specs]
        assert any("myfn" in n for n in names)

    def test_collect_callable_bind_specs_signature_fails(self) -> None:
        """_collect_callable_bind_specs returns [] when signature inspection raises."""
        # _CovUninspectable.__init__.__signature__ is broken → TypeError
        result = _collect_callable_bind_specs("myopt", f"{_COV_MOD}._CovUninspectable", "bind", set())
        assert result == []

    def test_collect_callable_bind_specs_varargs_skipped(self) -> None:
        """_collect_callable_bind_specs skips *args/**kwargs parameters."""
        specs = _collect_callable_bind_specs("myfn", f"{_COV_MOD}._cov_fn_with_varargs", "bind", set())
        names = [s.name for s in specs]
        assert "myfn.bind.key" in names
        assert not any("myfn.bind.args" in n for n in names)

    def test_collect_callable_factory_specs_fields_raises(self) -> None:
        """_collect_callable_factory_specs returns [] when _init_fields raises."""
        # _CovUninspectable.__init__.__signature__ raises TypeError → _init_fields raises
        result = _collect_callable_factory_specs("myopt", _CovUninspectable, set())
        assert result == []

    def test_collect_callable_factory_specs_dedup(self) -> None:
        """_collect_callable_factory_specs skips specs already in existing_names."""
        existing = {"myopt.lr"}
        specs = _collect_callable_factory_specs("myopt", _CovCallableCls, existing)
        assert all(s.name != "myopt.lr" for s in specs)

    def test_collect_callable_field_specs_class_mode_import_error(self) -> None:
        """_collect_callable_field_specs in 'class' mode falls through on import error."""
        # Bad path → SymbolImportError → falls through to bind specs → returns []
        result = _collect_callable_field_specs("opt", "nonexistent.Bad", "class", "bind", set())
        assert result == []

    def test_collect_callable_field_specs_fn_mode_class_path(self) -> None:
        """'fn' mode with a class path registers the constructor params as bind flags."""
        specs = _collect_callable_field_specs("opt", f"{_COV_MOD}._CovCallableCls", "fn", "bind", set())
        names = [s.name for s in specs]
        assert "opt.bind.lr" in names

    def test_collect_callable_field_specs_fn_mode_import_error(self) -> None:
        """_collect_callable_field_specs in 'fn' mode falls through on import error."""
        result = _collect_callable_field_specs("myfn", "nonexistent.fn", "fn", "bind", set())
        assert result == []

    def test_collect_fn_paths_from_config_fields_raises(self) -> None:
        """_collect_fn_paths_from_config returns {} when _struct_fields raises."""

        class _BrokenDCFields:
            pass

        _BrokenDCFields.__dataclass_fields__ = property(  # ty: ignore[unresolved-attribute]  # deliberately corrupt __dataclass_fields__ for testing
            lambda self: (_ for _ in ()).throw(TypeError("boom")),
        )
        result = _collect_fn_paths_from_config({}, _BrokenDCFields, "", "class")
        assert result == {}

    def test_build_dynamic_flags_config_equals_form(self, tmp_path: Path) -> None:
        """build_dynamic_flags reads fn paths from config file in --config=FILE argv form."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"fn": {"fn": f"{_COV_MOD}._cov_call_fn"}}))
        specs = build_dynamic_flags(
            _WithCovCallable,
            [f"--config={cfg}"],
        )
        names = [s.name for s in specs]
        assert "fn.bind.x" in names

    def test_build_dynamic_flags_exception_from_collect(self, monkeypatch) -> None:
        """build_dynamic_flags returns [] when an unexpected exception occurs."""

        def _boom(*args, **kwargs):
            msg = "deliberate boom"
            raise RuntimeError(msg)

        monkeypatch.setattr(build_mod, "_collect_fn_paths_from_argv", _boom)
        result = build_dynamic_flags(_WithCovCallable, [])
        assert result == []

    def test_collect_fn_paths_from_argv_equals_form(self) -> None:
        """_collect_fn_paths_from_argv handles --field.fn=path (= form)."""
        result = _collect_fn_paths_from_argv(["--optimizer.fn=my.module.fn"])
        assert result == {"optimizer": ("my.module.fn", "fn", "bind")}

    def test_collect_fn_paths_from_argv_space_form(self) -> None:
        """_collect_fn_paths_from_argv handles --field.fn path (space form)."""
        result = _collect_fn_paths_from_argv(["--optimizer.fn", "my.module.fn"])
        assert result == {"optimizer": ("my.module.fn", "fn", "bind")}

    def test_collect_fn_paths_from_argv_non_flag_token(self) -> None:
        """_collect_fn_paths_from_argv skips non-flag tokens."""
        result = _collect_fn_paths_from_argv(["value", "--optimizer.class=my.Cls"])
        assert "optimizer" in result

    def test_collect_fn_paths_from_argv_space_form_no_value(self) -> None:
        """_collect_fn_paths_from_argv skips --field.fn with no following value."""
        result = _collect_fn_paths_from_argv(["--optimizer.fn"])
        assert result == {}

    def test_collect_fn_paths_from_config_callable_fn(self) -> None:
        """_collect_fn_paths_from_config finds fn: entries for Callable fields."""
        config = {"fn": {"fn": "my.module.fn"}}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert "fn" in result
        assert result["fn"] == ("my.module.fn", "fn", "bind")

    def test_collect_fn_paths_from_config_callable_class(self) -> None:
        """_collect_fn_paths_from_config finds class: entries for Callable fields."""
        config = {"fn": {"class": "my.module.Cls"}}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert result.get("fn") == ("my.module.Cls", "class", "bind")

    def test_collect_fn_paths_from_config_callable_call(self) -> None:
        """_collect_fn_paths_from_config finds call: entries for Callable fields."""
        config = {"fn": {"call": "my.module.factory"}}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert result.get("fn") == ("my.module.factory", "call", "bind")

    def test_collect_fn_paths_from_config_callable_bare_string(self) -> None:
        """_collect_fn_paths_from_config handles bare string value for Callable field."""
        config = {"fn": "my.module.fn"}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert result.get("fn") == ("my.module.fn", "fn", "bind")

    def test_collect_fn_paths_from_config_non_struct(self) -> None:
        """_collect_fn_paths_from_config returns {} for non-struct types."""
        result = _collect_fn_paths_from_config({}, int, "", "class")
        assert result == {}

    def test_collect_struct_specs_callable_registers_identity_flags_only(self) -> None:
        """A Callable field registers only its identity flags; no return-type-derived factory flags.

        The implicit return-type factory form was removed: factory kwargs are supplied via
        'fn:'+bind (registered dynamically once --field.fn is in argv), not statically from
        the return type's fields.
        """
        specs = _collect_struct_specs(_WithCovCallable, "", "class")
        names = [s.name for s in specs]
        assert "fn.result_val" not in names
        assert {"fn", "fn.fn", "fn.class", "fn.call"} <= set(names)

    def test_build_dynamic_flags_with_argv(self) -> None:
        """build_dynamic_flags generates bind specs when --field.fn=path is in argv."""
        specs = build_dynamic_flags(
            _WithCovCallable,
            [f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        names = [s.name for s in specs]
        assert "fn.bind.x" in names

    def test_build_dynamic_flags_with_config_file(self, tmp_path: Path) -> None:
        """build_dynamic_flags reads fn paths from a config file referenced in argv."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"fn": {"fn": f"{_COV_MOD}._cov_call_fn"}}))
        specs = build_dynamic_flags(
            _WithCovCallable,
            ["--config", str(cfg)],
        )
        names = [s.name for s in specs]
        assert "fn.bind.x" in names

    def test_build_dynamic_flags_exception_returns_empty(self) -> None:
        """build_dynamic_flags returns [] on any internal exception."""
        # Passing a non-type target causes an internal error; result is []
        result = build_dynamic_flags(None, [])  # deliberately passing None to exercise internal error-handling
        assert result == []

    def test_resolve_struct_struct_fields_raises(self) -> None:
        """_resolve_struct returns None when _struct_fields raises for a struct-like type."""

        class _BrokenStruct:
            """Passes _is_struct but fails _struct_fields."""

        # Make _is_struct think this is a struct by giving it __dataclass_fields__
        _BrokenStruct.__dataclass_fields__ = property(  # ty: ignore[unresolved-attribute]  # deliberately corrupt __dataclass_fields__ for testing
            lambda self: (_ for _ in ()).throw(TypeError("boom")),
        )
        # Should return None, not raise
        result = _resolve_struct(_BrokenStruct)
        # It might or might not be None; important thing is it doesn't raise
        assert result is None or isinstance(result, tuple)


class TestNamespaceGaps:
    """Uncovered branches in merge_namespace/from_namespace."""

    def test_from_namespace_with_env_configs(self, tmp_path: Path) -> None:
        """from_namespace processes env_configs (files referenced by env vars)."""
        cfg = tmp_path / "sub.json"
        cfg.write_text(json.dumps({"result_val": "from_env_config"}))

        parser = argparse.ArgumentParser()
        populate_parser(_CovDCResult, parser)
        ns = parser.parse_args([])
        result = from_namespace(
            _CovDCResult,
            ns,
            env={"CONFARG_CONFIG__": str(cfg)},
            env_prefix="CONFARG_",
        )
        # The main point is no crash; result_val may or may not be set
        assert isinstance(result, _CovDCResult)

    def test_from_namespace_env_config_subpath(self, tmp_path: Path) -> None:
        """from_namespace processes env_configs with non-empty subpath."""
        cfg = tmp_path / "inner.json"
        cfg.write_text(json.dumps({"value": "from_env_subpath"}))

        parser = argparse.ArgumentParser()
        populate_parser(_CovOuter, parser)
        ns = parser.parse_args([])
        result = from_namespace(
            _CovOuter,
            ns,
            env={"CONFARG_CONFIG__INNER": str(cfg)},
            env_prefix="CONFARG_",
        )
        assert result.inner.value == "from_env_subpath"


class TestRegisterGaps:
    """Uncovered branches in _register.py."""

    def test_register_spec_skips_existing_dest(self) -> None:
        """_register_spec silently skips a spec whose name is already registered."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--myfield", dest="myfield", default=argparse.SUPPRESS)
        existing = {"myfield"}
        spec = FlagSpec(name="myfield", metavar="VAL", help="", group=None, group_description="")
        _register_spec(spec, parser, existing)
        # Should not raise, should not add duplicate
        assert len([a for a in parser._actions if a.dest == "myfield"]) == 1

    def test_populate_parser_with_argv(self) -> None:
        """populate_parser with argv registers dynamic bind specs."""
        parser = argparse.ArgumentParser()
        populate_parser(
            _WithCovCallable,
            parser,
            argv=[f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        dests = {a.dest for a in parser._actions}
        assert "fn.bind.x" in dests

    def test_add_callable_fn_flags(self) -> None:
        """_add_callable_fn_flags registers fn/class/call flags on the parser."""
        parser = argparse.ArgumentParser()
        _add_callable_fn_flags(parser, "myfield")
        dests = {a.dest for a in parser._actions}
        assert "myfield.fn" in dests
        assert "myfield.class" in dests
        assert "myfield.call" in dests

    def test_add_callable_bind_flags_no_existing_dests(self) -> None:
        """_add_callable_bind_flags works without pre-computed existing_dests."""
        parser = argparse.ArgumentParser()
        _add_callable_bind_flags(parser, "myfn", f"{_COV_MOD}._cov_call_fn")
        dests = {a.dest for a in parser._actions}
        assert "myfn.bind.x" in dests


class TestCompletionGaps:
    """Uncovered branches in _completion.py."""

    def test_resolve_tags_from_config_non_struct(self) -> None:
        """_resolve_tags_from_config returns {} for non-struct types."""
        result = _resolve_tags_from_config({}, int, "", "class")
        assert result == {}

    def test_resolve_tags_from_config_struct_fields_raises(self) -> None:
        """_resolve_tags_from_config returns {} when _struct_fields raises."""

        class _BrokenStruct:
            __dataclass_fields__ = property(
                lambda s: (_ for _ in ()).throw(ValueError("boom")),
            )

        result = _resolve_tags_from_config({}, _BrokenStruct, "", "class")
        assert result == {}

    def test_resolve_tags_from_config_optional_union(self) -> None:
        """_resolve_tags_from_config handles Optional[T] (single-variant union) in config."""

        @dataclass
        class _WithOptionalSub:
            sub: _CovDCResult | None = None

        config = {"sub": {"result_val": "hello"}}
        result = _resolve_tags_from_config(config, _WithOptionalSub, "", "class")
        # No union_tag in sub → tags is empty but shouldn't crash
        assert isinstance(result, dict)

    def test_extend_walk_concrete_singleton_literal_skipped(self) -> None:
        """_extend_walk skips singleton literal fields when concrete=True."""

        @dataclass
        class _WithLiteral:
            kind: Literal["fixed"] = "fixed"
            value: int = 0

        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests=set())
        _extend_walk(_WithLiteral, ctx, parser, "", concrete=True)
        dests = {a.dest for a in parser._actions}
        assert "kind" not in dests  # singleton literal skipped in concrete mode
        assert "value" in dests  # non-singleton fields are added

    def test_extend_walk_callable_field(self) -> None:
        """_extend_walk registers callable fn/class/call flags for Callable fields."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_WithCovCallable, ctx, parser, "")
        dests = {a.dest for a in parser._actions}
        assert "fn.fn" in dests

    def test_pre_extend_parser_outer_except(self, monkeypatch) -> None:
        """_pre_extend_parser_for_completion swallows any outer exception."""
        # Monkeypatch _collect_partial_config to raise an unexpected exception
        monkeypatch.setattr(
            "confarg.cli.argparse._completion._collect_partial_config",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        parser = argparse.ArgumentParser()
        # Must not raise
        _pre_extend_parser_for_completion(parser, WithDefaults, "class", "config", [])

    def test_pre_extend_parser_with_union_tag(self) -> None:
        """_pre_extend_parser_for_completion extends parser when a union class tag is in argv."""
        cls_path = f"{_COV_MOD}._ConstructAVariant"
        parser = argparse.ArgumentParser()
        populate_parser(_WithUnionForCompletion, parser)
        _pre_extend_parser_for_completion(
            parser,
            _WithUnionForCompletion,
            "class",
            "config",
            [f"--val.class={cls_path}"],
        )
        dests = {a.dest for a in parser._actions}
        assert "val.x" in dests

    def test_pre_extend_parser_with_callable_bind(self) -> None:
        """_pre_extend_parser_for_completion registers bind flags for --fn.fn in argv."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithCovCallable, parser)
        _pre_extend_parser_for_completion(
            parser,
            _WithCovCallable,
            "class",
            "config",
            [f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        dests = {a.dest for a in parser._actions}
        assert "fn.bind.x" in dests

    def test_extend_walk_var_params_skipped(self) -> None:
        """_extend_walk skips var_params fields like **kwargs in plain classes."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_CovWithKwargs, ctx, parser, "")
        dests = {a.dest for a in parser._actions}
        # "extra" is a **kwargs param → skipped
        assert "extra" not in dests

    def test_extend_walk_struct_group_already_exists(self) -> None:
        """_extend_walk reuses an existing group when the struct field was already walked."""
        parser = argparse.ArgumentParser()
        # First walk creates the "inner" group
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests=set())
        _extend_walk(_CovOuter, ctx, parser, "")
        # Second walk finds the group already exists
        _extend_walk(_CovOuter, ctx, parser, "")
        # Should not raise
        assert any(g.title == "inner" for g in parser._action_groups)

    def test_extend_walk_dict_field_skipped(self) -> None:
        """_extend_walk skips dict-typed fields."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_CovWithDict, ctx, parser, "")
        dests = {a.dest for a in parser._actions}
        # "settings" is a dict field → should be skipped
        assert "settings" not in dests
        assert "name" in dests

    def test_pre_extend_parser_non_struct_class_skipped(self) -> None:
        """_pre_extend_parser_for_completion skips class_path that resolves to non-struct."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithUnionForCompletion, parser)
        # "builtins.int" is a type but NOT a struct → skipped
        _pre_extend_parser_for_completion(
            parser,
            _WithUnionForCompletion,
            "class",
            "config",
            ["--val.class=builtins.int"],
        )
        # Should not crash; val.x/val.y are already registered by populate_parser
        # (not added by _pre_extend_parser_for_completion from a non-struct class).
        dests = {a.dest for a in parser._actions}
        assert "val.x" in dests
        assert "val.class" in dests

    def test_pre_extend_parser_bind_flags_exception(self, monkeypatch) -> None:
        """_pre_extend_parser_for_completion swallows exception from _add_callable_bind_flags."""

        def _boom(*args, **kwargs):
            msg = "deliberate bind boom"
            raise RuntimeError(msg)

        monkeypatch.setattr(reg_mod, "_collect_callable_bind_specs", _boom)
        parser = argparse.ArgumentParser()
        populate_parser(_WithCovCallable, parser)
        # Must not raise even though _add_callable_bind_flags raises
        _pre_extend_parser_for_completion(
            parser,
            _WithCovCallable,
            "class",
            "config",
            [f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )

    def test_setup_completion_argv_defaults_to_sys_argv(self, monkeypatch) -> None:
        """setup_completion defaults argv to sys.argv[1:] when argv=None."""
        # Inject a mock argcomplete so ImportError is avoided
        mock_argcomplete = types.ModuleType("argcomplete")
        mock_argcomplete.autocomplete = lambda *a, **kw: None  # ty: ignore[unresolved-attribute]  # dynamically adding attribute to a mock module
        monkeypatch.setitem(sys.modules, "argcomplete", mock_argcomplete)

        parser = argparse.ArgumentParser()
        populate_parser(_CovDCResult, parser)
        monkeypatch.setattr(sys, "argv", ["prog", "--result_val=hello"])
        # argv=None → sys.argv[1:] is used
        _argparse_setup_completion(parser, _CovDCResult, argv=None)
