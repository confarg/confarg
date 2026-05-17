# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Curated registry mapping example scripts to replayable load specifications.

Each ``uv run <script>.py`` command found in an example README is replayed
in-process through every CLI integration (see test_readme_commands.py).  The
registry tells the replay harness, per script, which module attribute is the
load target, which keyword arguments the script passes to ``confarg.load``,
and how the script renders the result for output comparison.

An unregistered vanilla script appearing in a README fails the suite loudly —
add it here (or to SKIP_DIRS with a reason) so the registry stays honest.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


def _render_greeting(config: Any) -> str:
    """Mimic 130_callable / 140_binding main(): call the configured fn and capture stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        config.greetings_fn("world")
    return buf.getvalue().rstrip("\n")


def _render_optimizer(config: Any) -> str:
    """Mimic 150_factories main(): print the factory and the constructed optimizer."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(config.optimizer)
        print(config.optimizer([1, 2]))
    return buf.getvalue().rstrip("\n")


def _setup_custom_leaf_type() -> None:
    """Mimic 4_leaf_types/custom_leaf_type.py main(): register the Int leaf type."""
    import confarg  # noqa: PLC0415  # deferred so registration happens at replay time, like in the script

    from .test_readme_commands import load_script_module  # noqa: PLC0415  # circular at module level

    mod = load_script_module("4_leaf_types", "custom_leaf_type.py")
    confarg.register_leaf_type(mod.Int, mod.coerce_int)


@dataclass(frozen=True)
class ScriptSpec:
    """How to replay one example script's confarg.load call in-process."""

    target: str = "Config"
    printer: Literal["print", "pprint"] = "print"
    load_kwargs: Mapping[str, Any] = field(default_factory=dict)
    render: Callable[[Any], str] | None = None
    setup: Callable[[], None] | None = None


# (example_dir, script_name) -> spec.  Only vanilla scripts are registered;
# *_argparse.py twins replay the same commands through ArgparseLoader anyway.
REGISTRY: dict[tuple[str, str], ScriptSpec] = {
    ("1_three_input_sources", "myapp.py"): ScriptSpec(target="DBConfig", load_kwargs={"env_prefix": "MYAPP_"}),
    ("2_input_precedence", "myapp.py"): ScriptSpec(target="DBConfig", load_kwargs={"env_prefix": "MYAPP_"}),
    ("3_scalar_types", "str_value.py"): ScriptSpec(),
    ("3_scalar_types", "int_value.py"): ScriptSpec(),
    ("3_scalar_types", "float_value.py"): ScriptSpec(),
    ("3_scalar_types", "bool_value.py"): ScriptSpec(),
    ("3_scalar_types", "none_value.py"): ScriptSpec(),
    ("4_leaf_types", "enum_value.py"): ScriptSpec(),
    ("4_leaf_types", "path_value.py"): ScriptSpec(),
    ("4_leaf_types", "custom_leaf_type.py"): ScriptSpec(setup=_setup_custom_leaf_type),
    ("5_generics", "literal.py"): ScriptSpec(),
    ("5_generics", "annotated.py"): ScriptSpec(),
    ("5_generics", "final.py"): ScriptSpec(),
    ("6_unions", "myapp.py"): ScriptSpec(),
    ("7_stealing_rule", "str_or_none.py"): ScriptSpec(),
    ("7_stealing_rule", "str_or_float.py"): ScriptSpec(),
    ("7_stealing_rule", "str_or_bool.py"): ScriptSpec(),
    ("7_stealing_rule", "enum_or_str.py"): ScriptSpec(),
    ("7_stealing_rule", "enum_or_int.py"): ScriptSpec(),
    ("8_disambiguation", "dbhosts.py"): ScriptSpec(),
    ("8_disambiguation", "dbhosts_type.py"): ScriptSpec(),
    ("8_disambiguation", "myapp.py"): ScriptSpec(),
    ("9_child_configurations", "myapp.py"): ScriptSpec(target="DBConfig"),
    ("9_child_configurations", "db_or_api.py"): ScriptSpec(),
    ("10_nested_configurations", "myapp.py"): ScriptSpec(printer="pprint"),
    ("13_collection_items", "list_of_list_of_ints.py"): ScriptSpec(printer="pprint"),
    ("13_collection_items", "pair_of_ints.py"): ScriptSpec(printer="pprint"),
    ("13_collection_items", "triplet_of_ints.py"): ScriptSpec(printer="pprint"),
    ("50_list", "myapp.py"): ScriptSpec(printer="pprint"),
    ("60_type", "myapp.py"): ScriptSpec(),
    ("70_subconfig", "myapp.py"): ScriptSpec(printer="pprint"),
    ("80_variable_interpolation", "myapp.py"): ScriptSpec(printer="pprint"),
    ("110_include", "myapp.py"): ScriptSpec(printer="pprint"),
    ("120_unstructured", "myapp.py"): ScriptSpec(printer="pprint"),
    ("130_callable", "myapp.py"): ScriptSpec(render=_render_greeting),
    ("140_binding", "myapp.py"): ScriptSpec(render=_render_greeting),
    ("150_factories", "myapp.py"): ScriptSpec(render=_render_optimizer),
    ("160_json", "myapp.py"): ScriptSpec(printer="pprint"),
    ("170_append", "myapp.py"): ScriptSpec(printer="pprint"),
    ("170_append", "simple.py"): ScriptSpec(printer="pprint"),
    ("180_deletion", "myapp.py"): ScriptSpec(printer="pprint"),
    ("180_deletion", "users.py"): ScriptSpec(printer="pprint"),
    ("180_deletion", "names.py"): ScriptSpec(printer="pprint"),
    ("180_deletion", "transforms.py"): ScriptSpec(printer="pprint"),
    ("180_deletion", "transforms_v2.py"): ScriptSpec(printer="pprint"),
}

# Example dirs whose README commands cannot be replayed through the loader
# harness; the subprocess plugin still covers them verbatim.
SKIP_DIRS: dict[str, str] = {
    "90_integration": "framework-wiring example with positional CLI params not expressible via the loaders",
}

# (example_dir, substring of the command) -> skip reason, for individual
# commands that cannot be replayed in-process.
SKIP_COMMANDS: dict[tuple[str, str], str] = {}

# (example_dir, substring of the command) -> reason, for commands that only
# work through confarg.load().  Empty: the list-patch, dict-subkey, call-bind,
# and expression-over-CLI-token gaps are now closed — every backend registers
# the argv-derived patch flags (build_dynamic_flags) and applies them through
# the shared argv-ordered patch scan (_parse_cli patch_only mode), with eager
# leaf coercion making merged dicts identical to confarg.load().
VANILLA_ONLY_COMMANDS: dict[tuple[str, str], str] = {}

# (example_dir, substring of the command) -> (reason, loader ids to skip), for
# host-framework syntax limitations (e.g. argparse rejecting option values that
# look like flags, such as negative numbers in scientific notation).
LOADER_SKIP_COMMANDS: dict[tuple[str, str], tuple[str, frozenset[str]]] = {
    ("3_scalar_types", "--value -1.5e-2"): (
        "argparse rejects option values starting with '-' unless they parse as plain negative numbers",
        frozenset({"argparse"}),
    ),
    ("3_scalar_types", "--value -inf"): (
        "argparse rejects option values starting with '-' unless they parse as plain negative numbers",
        frozenset({"argparse"}),
    ),
    ("3_scalar_types", "--value -42"): (
        "argparse/cyclopts reject or mis-tokenize negative-number option values",
        frozenset({"argparse", "cyclopts"}),
    ),
    ("3_scalar_types", "--value -0o20"): (
        "argparse/cyclopts reject or mis-tokenize negative-number option values",
        frozenset({"argparse", "cyclopts"}),
    ),
}
