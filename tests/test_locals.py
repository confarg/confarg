# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the reserved ``locals:`` namespace holding local variables.

Cross-front-end behavior is pinned once in
``tests/cli/test_backend_contract.py::TestLocalsContract``; what lives here is
the config-file machinery the namespace rides on — includes, data-format
rejection, round-tripping, and the reserved-name policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import confarg
from confarg._files import INCLUDE_KEY
from confarg.exceptions import ConfargError, InvalidConfigFileError, LocalsError, TypeCoercionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write(tmp_path: Path, name: str, content: str) -> Path:
    """Write content to a named file inside tmp_path and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


@dataclass
class Cfg:
    """Config whose fields are derived from local variables."""

    root: str = ""
    n: int = 0


@dataclass
class Shadow:
    """Config that claims `locals`, pushing the namespace to `_locals`."""

    locals: str = ""
    root: str = ""


@dataclass
class ShadowBoth:
    """Config that claims both names, leaving no namespace at all."""

    locals: str = ""
    _locals: str = ""


# ---------------------------------------------------------------------------
# Includes
# ---------------------------------------------------------------------------


class TestLocalsFromIncludes:
    """A shared variable library merges into the parent's namespace via __include__."""

    def test_included_locals_are_visible(self, tmp_path: Path) -> None:
        """Locals declared in an included file feed the parent's expressions."""
        write(tmp_path, "vars.yaml", "base: /srv\n")
        cfg = write(
            tmp_path,
            "config.yaml",
            f"locals:\n  {INCLUDE_KEY}: ./vars.yaml\nroot: ${{locals.base}}\n",
        )
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).root == "/srv"

    def test_parent_locals_override_included_ones(self, tmp_path: Path) -> None:
        """Sibling keys win over the included file, as they do for ordinary fields."""
        write(tmp_path, "vars.yaml", "base: /srv\n")
        cfg = write(
            tmp_path,
            "config.yaml",
            f"locals:\n  {INCLUDE_KEY}: ./vars.yaml\n  base: /opt\nroot: ${{locals.base}}\n",
        )
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).root == "/opt"


# ---------------------------------------------------------------------------
# Self-describing formats only
# ---------------------------------------------------------------------------


class TestLocalsRequireTypedFormats:
    """Data files carry no types, so they may not *declare* local variables.

    Declaring a local is what gives it a type, and CSV/TSV cells load as
    ``_StrToken`` precisely because they have none of their own — they rely on a
    target leaf type a local does not have.  A local declared from such a file
    would stay a string and silently turn ``${locals.n * 2}`` into string
    repetition, so the namespace accepts only self-describing formats.
    """

    def test_csv_include_into_locals_raises(self, tmp_path: Path) -> None:
        """A CSV reached through __include__ is rejected, naming the offending path."""
        write(tmp_path, "vars.csv", "base\n/srv\n")
        cfg = write(
            tmp_path,
            "config.yaml",
            f"locals:\n  base:\n    {INCLUDE_KEY}: ./vars.csv\nroot: ${{locals.base}}\n",
        )
        with pytest.raises(InvalidConfigFileError, match="self-describing"):
            confarg.load(Cfg, argv=["--config", str(cfg)], env={})

    def test_csv_appended_into_locals_raises(self, tmp_path: Path) -> None:
        """A CSV reached through --config.locals.<field>+ is rejected too."""
        data = write(tmp_path, "vars.csv", "base\n/srv\n")
        cfg = write(tmp_path, "config.yaml", "locals:\n  items: []\nroot: x\n")
        with pytest.raises(InvalidConfigFileError, match="self-describing"):
            confarg.load(
                Cfg,
                argv=["--config", str(cfg), "--config.locals.items+", str(data)],
                env={},
            )

    def test_yaml_locals_are_accepted(self, tmp_path: Path) -> None:
        """The same shape from YAML is fine — the format, not the value, is the issue."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).root == "/srv"


# ---------------------------------------------------------------------------
# Declaration and modification
# ---------------------------------------------------------------------------


class TestLocalsDeclarationAndModification:
    """A local is *declared* in a config file and *modified* from any channel.

    Declaring is what gives a local its type, and only a self-describing file
    format carries one — so declaration stays file-only while modification has
    full cross-channel parity.  A write to an undeclared name is an error rather
    than a new variable, which is what keeps typos catchable.
    """

    def test_cli_modifies_a_declared_local(self, tmp_path: Path) -> None:
        """The documented handle: --locals.<name> retargets a declared variable."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        result = confarg.load(Cfg, argv=["--config", str(cfg), "--locals.base", "/home/bob"], env={})
        assert result.root == "/home/bob"

    def test_env_modifies_a_declared_local(self, tmp_path: Path) -> None:
        """The env channel does the same, with the usual case-insensitive segments."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        result = confarg.load(
            Cfg,
            argv=["--config", str(cfg)],
            env={"MYAPP_LOCALS__BASE": "/home/bob"},
            env_prefix="MYAPP_",
        )
        assert result.root == "/home/bob"

    def test_override_keeps_the_declared_type(self, tmp_path: Path) -> None:
        """A CLI override of an int local stays an int, so arithmetic still adds."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  k: 3\nn: ${locals.k * 2}\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg), "--locals.k", "5"], env={}).n == 10

    def test_undeclared_local_raises(self, tmp_path: Path) -> None:
        """Setting a name no file declared is an error, not a new variable."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        with pytest.raises(LocalsError, match="declared by no configuration file"):
            confarg.load(Cfg, argv=["--config", str(cfg), "--locals.nope", "x"], env={})

    def test_undeclared_local_from_env_raises(self, tmp_path: Path) -> None:
        """Same in the env channel, instead of the usual warn-and-drop."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        with pytest.raises(LocalsError, match="declared by no configuration file"):
            confarg.load(
                Cfg,
                argv=["--config", str(cfg)],
                env={"MYAPP_LOCALS__NOPE": "x"},
                env_prefix="MYAPP_",
            )

    def test_type_changing_override_raises(self, tmp_path: Path) -> None:
        """A local's scalar type comes from its declaration and cannot change."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  k: 3\nn: ${locals.k}\n")
        with pytest.raises(TypeCoercionError):
            confarg.load(Cfg, argv=["--config", str(cfg), "--locals.k", "abc"], env={})

    def test_scalar_over_a_declared_container_raises(self, tmp_path: Path) -> None:
        """The rule holds for containers too, with a message naming the declared kind."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  d:\n    b: 1\nn: ${locals.d.b}\n")
        with pytest.raises(TypeCoercionError, match="declared as a dict"):
            confarg.load(Cfg, argv=["--config", str(cfg), "--locals.d", "x"], env={})

    def test_nested_local_can_be_modified(self, tmp_path: Path) -> None:
        """Dotted paths reach into a declared mapping, leaving its siblings alone."""
        cfg = write(
            tmp_path,
            "config.yaml",
            "locals:\n  d:\n    b: 1\n    c: 2\nn: ${locals.d.b + locals.d.c}\n",
        )
        assert confarg.load(Cfg, argv=["--config", str(cfg), "--locals.d.b", "9"], env={}).n == 11

    def test_declared_list_element_can_be_modified(self, tmp_path: Path) -> None:
        """An index into a declared list is a modification like any other."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  xs: [1, 2]\nn: ${locals.xs[0] + locals.xs[1]}\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg), "--locals.xs.0", "10"], env={}).n == 12

    def test_whole_namespace_cannot_be_assigned(self) -> None:
        """A bare --locals would replace the namespace; that is rejected explicitly."""
        with pytest.raises(LocalsError, match="cannot be assigned as a whole"):
            confarg.load(Cfg, argv=["--locals", "x"], env={})

    def test_a_local_cannot_be_deleted(self, tmp_path: Path) -> None:
        """Which locals exist is the declaring file's business, so delete is rejected.

        Without this the ``_DELETE_`` sentinel would fall through to coercion and
        surface as a baffling "cannot coerce _DeleteSentinel" error.
        """
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        with pytest.raises(LocalsError, match="cannot be added or removed"):
            confarg.load(Cfg, argv=["--config", str(cfg), "--locals.base-"], env={})

    def test_a_declared_list_cannot_be_restructured(self, tmp_path: Path) -> None:
        """Element delete is rejected for the same reason; assignment by index is not."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  xs: [1, 2]\nn: ${locals.xs[1]}\n")
        with pytest.raises(LocalsError, match="cannot be added or removed"):
            confarg.load(Cfg, argv=["--config", str(cfg), "--locals.xs.1-"], env={})
        assert confarg.load(Cfg, argv=["--config", str(cfg), "--locals.xs.1", "9"], env={}).n == 9

    def test_config_locals_file_declares(self, tmp_path: Path) -> None:
        """--config.locals FILE still declares, so it can introduce brand-new locals."""
        base = write(tmp_path, "config.yaml", "root: ${locals.extra}\n")
        extra = write(tmp_path, "extra.yaml", "extra: /opt\n")
        result = confarg.load(Cfg, argv=["--config", str(base), "--config.locals", str(extra)], env={})
        assert result.root == "/opt"

    def test_override_may_be_an_expression(self, tmp_path: Path) -> None:
        """A ${...} override is deferred past coercion and resolved in build()."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}/data\nn: 7\n")
        result = confarg.load(Cfg, argv=["--config", str(cfg), "--locals.base", "/srv/${n}"], env={})
        assert result.root == "/srv/7/data"

    def test_cli_beats_env_beats_file(self, tmp_path: Path) -> None:
        """Overrides follow the ordinary config < env < CLI precedence."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\nroot: ${locals.base}\n")
        argv = ["--config", str(cfg), "--locals.base", "/from-cli"]
        env = {"MYAPP_LOCALS__BASE": "/from-env"}
        assert confarg.load(Cfg, argv=argv, env=env, env_prefix="MYAPP_").root == "/from-cli"
        assert confarg.load(Cfg, argv=argv[:2], env=env, env_prefix="MYAPP_").root == "/from-env"


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestLocalsRoundTrip:
    """merge() keeps the namespace, so a config file survives a save/reload cycle."""

    def test_merge_dump_reload(self, tmp_path: Path) -> None:
        """merge() → dump_file() → load(files=[saved]) preserves locals and expressions."""
        cfg = write(
            tmp_path,
            "config.yaml",
            "locals:\n  base: /srv\n  k: 3\nroot: ${locals.base}\nn: ${locals.k * 2}\n",
        )
        data = confarg.merge(Cfg, argv=["--config", str(cfg)], env={})
        assert data["locals"] == {"base": "/srv", "k": 3}
        assert data["root"] == "${locals.base}"

        saved = tmp_path / "saved.yaml"
        confarg.dump_file(data, saved)
        assert confarg.load(Cfg, argv=[], env={}, files=[saved]) == Cfg(root="/srv", n=6)

    def test_build_leaves_the_caller_dict_intact(self) -> None:
        """build() copies rather than pops: resolve_expressions may return the input itself."""
        data = {"locals": {"base": "/srv"}, "root": "/srv", "n": 1}
        confarg.build(Cfg, data)
        assert "locals" in data


# ---------------------------------------------------------------------------
# Reserved-name policy
# ---------------------------------------------------------------------------


class TestLocalsNameResolution:
    """The namespace's name is derived from the target, not passed in.

    ``locals`` and ``_locals`` both address it, unless the target owns that name:
    a real field always wins, the same rule that makes a field named ``json`` win
    over the ``.json`` force cast.  A target owning both names has no namespace at
    all, and declaring under both spellings at once is ambiguous.
    """

    def test_either_spelling_declares(self, tmp_path: Path) -> None:
        """With `locals` free, `_locals:` is the namespace just as `locals:` is."""
        cfg = write(tmp_path, "config.yaml", "_locals:\n  base: /srv\nroot: ${_locals.base}\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).root == "/srv"

    def test_either_spelling_is_modifiable(self, tmp_path: Path) -> None:
        """The CLI and env handles follow the spelling the declaration used."""
        cfg = write(tmp_path, "config.yaml", "_locals:\n  base: /srv\nroot: ${_locals.base}\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg), "--_locals.base", "/opt"], env={}).root == "/opt"
        from_env = confarg.load(
            Cfg,
            argv=["--config", str(cfg)],
            env={"MYAPP__LOCALS__BASE": "/opt"},
            env_prefix="MYAPP_",
        )
        assert from_env.root == "/opt"

    def test_declaring_under_both_spellings_is_ambiguous(self, tmp_path: Path) -> None:
        """Two declaration blocks give no answer to "which one holds the variables?"."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  a: 1\n_locals:\n  b: 2\nroot: x\n")
        with pytest.raises(LocalsError, match="ambiguous"):
            confarg.load(Cfg, argv=["--config", str(cfg)], env={})

    def test_a_locals_field_keeps_its_name(self, tmp_path: Path) -> None:
        """A real `locals` field takes the name; the namespace moves to `_locals`."""
        cfg = write(
            tmp_path,
            "config.yaml",
            "locals: iamafield\n_locals:\n  base: /srv\nroot: ${_locals.base}\n",
        )
        result = confarg.load(Shadow, argv=["--config", str(cfg)], env={})
        assert result.locals == "iamafield"
        assert result.root == "/srv"

    def test_a_locals_field_stays_cli_settable(self, tmp_path: Path) -> None:
        """`--locals` reaches the field, `--_locals.x` the namespace — no interception."""
        cfg = write(
            tmp_path,
            "config.yaml",
            "locals: iamafield\n_locals:\n  base: /srv\nroot: ${_locals.base}\n",
        )
        result = confarg.load(
            Shadow,
            argv=["--config", str(cfg), "--locals", "other", "--_locals.base", "/opt"],
            env={},
        )
        assert result.locals == "other"
        assert result.root == "/opt"

    def test_owning_both_names_disables_the_namespace(self, tmp_path: Path) -> None:
        """No name is left, so both keys are ordinary fields and nothing raises."""
        cfg = write(tmp_path, "config.yaml", "locals: a\n_locals: b\n")
        result = confarg.load(ShadowBoth, argv=["--config", str(cfg)], env={})
        assert result == ShadowBoth(locals="a", _locals="b")

    def test_dict_root_has_no_namespace(self, tmp_path: Path) -> None:
        """Every name is a real key of a dict target, so `locals:` stays data."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  base: /srv\n")
        assert confarg.merge(dict[str, dict[str, str]], argv=["--config", str(cfg)], env={}) == {
            "locals": {"base": "/srv"},
        }

    def test_config_flag_collision_raises(self) -> None:
        """`--locals` would be eaten as the config flag, so that pairing is refused."""
        with pytest.raises(ConfargError, match="also a name of the local-variables"):
            confarg.load(Cfg, argv=[], env={}, config_flag="locals")


# ---------------------------------------------------------------------------
# Scalar (``__root__``) targets
# ---------------------------------------------------------------------------


class TestLocalsWithScalarTarget:
    """The namespace coexists with the ``__root__`` key used for non-struct targets."""

    def test_scalar_root_can_use_locals(self, tmp_path: Path) -> None:
        """A scalar target's value may be an expression over a local variable."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  k: 3\n__root__: ${locals.k * 2}\n")
        assert confarg.load(int, argv=["--config", str(cfg)], env={}) == 6

    def test_scalar_root_local_is_modifiable(self, tmp_path: Path) -> None:
        """Grafting the namespace must not break scalar-root detection."""
        cfg = write(tmp_path, "config.yaml", "locals:\n  k: 3\n__root__: ${locals.k * 2}\n")
        assert confarg.load(int, argv=["--config", str(cfg), "--locals.k", "5"], env={}) == 10


# ---------------------------------------------------------------------------
# Namespaces below the root
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """Block a fragment can describe, with its own scratch values."""

    host: str = ""
    port: int = 0


@dataclass
class Tree:
    """Target mounting :class:`Node` under a key the namespace must not claim."""

    db: Node = dc_field(default_factory=Node)
    name: str = ""


@dataclass
class OwnsLocals:
    """Nested block that claims ``locals`` for itself."""

    locals: str = ""
    host: str = ""


@dataclass
class TreeOwning:
    """Target whose nested block claims ``locals``, pushing the namespace to ``_locals``."""

    db: OwnsLocals = dc_field(default_factory=OwnsLocals)


class TestNestedLocals:
    """A namespace may sit at any node the target does not claim.

    An included file's root -- and with it its ``locals:`` block -- lands wherever
    the file is mounted, so the namespace is not a root-only affair.  The name is
    derived per node with the same rule the root uses, and declaring, typing,
    stripping and overriding all follow it down.
    """

    def test_a_fragment_declares_and_uses_its_own_locals(self, tmp_path: Path) -> None:
        """The block reads its own namespace by the same bare path it would at the root."""
        write(tmp_path, "db.yaml", "locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"name: app\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert confarg.load(Tree, argv=["--config", str(cfg)], env={}).db.host == "db.internal"

    def test_the_nested_namespace_is_stripped(self, tmp_path: Path) -> None:
        """It never reaches the target, which has no field of that name."""
        write(tmp_path, "db.yaml", "locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert confarg.load(Tree, argv=["--config", str(cfg)], env={}) == Tree(db=Node(host="db.internal"))

    def test_a_nested_local_is_modifiable_from_the_cli(self, tmp_path: Path) -> None:
        """Modification has the same parity below the root as at it."""
        write(tmp_path, "db.yaml", "locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        result = confarg.load(Tree, argv=["--config", str(cfg), "--db.locals.h", "other"], env={})
        assert result.db.host == "other"

    def test_a_nested_local_is_modifiable_from_the_environment(self, tmp_path: Path) -> None:
        """The env channel derives the namespace per node too."""
        write(tmp_path, "db.yaml", "locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        result = confarg.load(
            Tree,
            argv=["--config", str(cfg)],
            env={"MYAPP_DB__LOCALS__H": "from-env"},
            env_prefix="MYAPP_",
        )
        assert result.db.host == "from-env"

    def test_a_nested_local_keeps_its_declared_type(self, tmp_path: Path) -> None:
        """The declaration fixes the type at depth exactly as it does at the root."""
        write(tmp_path, "db.yaml", "locals:\n  p: 5432\nport: ${locals.p}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert confarg.load(Tree, argv=["--config", str(cfg), "--db.locals.p", "6000"], env={}).db.port == 6000
        with pytest.raises(TypeCoercionError):
            confarg.load(Tree, argv=["--config", str(cfg), "--db.locals.p", "many"], env={})

    def test_an_undeclared_nested_local_raises(self, tmp_path: Path) -> None:
        """A typo is caught at depth, naming the full path."""
        write(tmp_path, "db.yaml", "locals:\n  h: db.internal\nhost: ${locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        with pytest.raises(LocalsError, match=r"db\.locals\.hh"):
            confarg.load(Tree, argv=["--config", str(cfg), "--db.locals.hh", "x"], env={})

    def test_a_nested_csv_declaration_is_rejected(self, tmp_path: Path) -> None:
        """The self-describing-format rule follows the namespace down."""
        write(tmp_path, "vars.csv", "h\nsrv\n")
        write(tmp_path, "db.yaml", f"locals:\n  h:\n    {INCLUDE_KEY}: ./vars.csv\nhost: ${{locals.h}}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        with pytest.raises(InvalidConfigFileError, match="self-describing"):
            confarg.load(Tree, argv=["--config", str(cfg)], env={})

    def test_declaring_under_both_spellings_is_ambiguous(self, tmp_path: Path) -> None:
        """The ambiguity rule applies per node, and the message names the node."""
        write(tmp_path, "db.yaml", "locals:\n  h: a\n_locals:\n  h: b\nhost: ${locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        with pytest.raises(LocalsError, match="ambiguous"):
            confarg.load(Tree, argv=["--config", str(cfg)], env={})

    def test_a_nested_locals_field_keeps_its_name(self, tmp_path: Path) -> None:
        """A real field wins at depth, and the namespace moves to ``_locals``."""
        write(tmp_path, "db.yaml", "locals: a string\n_locals:\n  h: db.internal\nhost: ${_locals.h}\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        result = confarg.load(TreeOwning, argv=["--config", str(cfg)], env={})
        assert result.db == OwnsLocals(locals="a string", host="db.internal")

    def test_a_dict_typed_node_keeps_locals_as_data(self, tmp_path: Path) -> None:
        """Every name is a real key of a dict, so no namespace exists there."""

        @dataclass
        class WithDict:
            bag: dict[str, Any] = dc_field(default_factory=dict)

        write(tmp_path, "bag.yaml", "locals:\n  h: kept\n")
        cfg = write(tmp_path, "app.yaml", f"bag:\n  {INCLUDE_KEY}: ./bag.yaml\n")
        assert confarg.load(WithDict, argv=["--config", str(cfg)], env={}).bag == {"locals": {"h": "kept"}}
