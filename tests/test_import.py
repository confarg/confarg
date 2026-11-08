# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for _import_dotted (symbol import by dotted path) and dotted_name, its writer.

Covers dotted module paths, chained getattr, the builtins fallback for bare
names (regression: `type` fields with `--value int`), the error path, and the
module a written path names.
"""

from __future__ import annotations

import ntpath
import os
import sys
from collections import OrderedDict
from typing import TYPE_CHECKING

import pytest

from confarg._import import _import_dotted, dotted_name
from confarg.exceptions import SymbolImportError, SymbolNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class TestImportDotted:
    """Unit tests for _import_dotted(path)."""

    def test_bare_builtin_int(self) -> None:
        """A bare builtin name resolves against the builtins module."""
        assert _import_dotted("int") is int

    def test_bare_builtin_str(self) -> None:
        """`str` resolves to the str type."""
        assert _import_dotted("str") is str

    def test_bare_builtin_type(self) -> None:
        """`type` resolves to the type metaclass."""
        assert _import_dotted("type") is type

    def test_qualified_builtin_still_works(self) -> None:
        """An explicit `builtins.int` path still resolves (real-module route)."""
        assert _import_dotted("builtins.int") is int

    def test_dotted_module_path(self) -> None:
        """A dotted path into a real module resolves via import + getattr."""
        assert _import_dotted("collections.OrderedDict") is OrderedDict

    def test_unimportable_path_raises(self) -> None:
        """A path that is neither a module nor a builtin raises SymbolImportError."""
        with pytest.raises(SymbolImportError):
            _import_dotted("no.such.module.Class")

    def test_unknown_bare_name_raises(self) -> None:
        """A bare name that is not a builtin raises SymbolImportError."""
        with pytest.raises(SymbolImportError):
            _import_dotted("definitely_not_a_builtin_xyz")

    def test_broken_dependency_is_surfaced_not_masked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """A broken transitive dependency is surfaced, not masked (REF-5).

        A ``ModuleNotFoundError`` raised inside an importable module — here a
        missing dependency it imports — is a real error, not a typo'd path: the
        loader must not swallow it and walk down to shorter prefixes.
        """
        pkg_dir = tmp_path / "ref5_broken_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "broken.py").write_text("import ref5_missing_dependency_xyz\n")
        monkeypatch.syspath_prepend(str(tmp_path))

        pkg_name = "ref5_broken_pkg"

        def _purge() -> None:
            for key in [k for k in sys.modules if k == pkg_name or k.startswith(pkg_name + ".")]:
                sys.modules.pop(key, None)

        request.addfinalizer(_purge)

        with pytest.raises(SymbolImportError) as exc_info:
            _import_dotted("ref5_broken_pkg.broken.Thing")
        msg = str(exc_info.value)
        assert "ref5_missing_dependency_xyz" in msg
        assert "no importable module found" not in msg

    def test_import_error_inside_module_is_surfaced(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """An ImportError raised inside a module is surfaced, not masked (REF-5).

        A non-``ModuleNotFoundError`` ``ImportError`` (failed ``from x import y``,
        a circular import, an explicit ``raise ImportError``) comes from inside a
        module that does exist, so it is a real failure to report.
        """
        pkg_dir = tmp_path / "ref5_initerr_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "broken.py").write_text('raise ImportError("ref5 custom init failure")\n')
        monkeypatch.syspath_prepend(str(tmp_path))

        pkg_name = "ref5_initerr_pkg"

        def _purge() -> None:
            for key in [k for k in sys.modules if k == pkg_name or k.startswith(pkg_name + ".")]:
                sys.modules.pop(key, None)

        request.addfinalizer(_purge)

        with pytest.raises(SymbolImportError) as exc_info:
            _import_dotted("ref5_initerr_pkg.broken.Thing")
        assert "ref5 custom init failure" in str(exc_info.value)


def _purge_modules(name: str) -> None:
    """Drop the module *name* and its submodules from ``sys.modules``."""
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        sys.modules.pop(key, None)


class TestSymbolNotFound:
    """A path that names nothing is a ``SymbolNotFoundError``; a module that fails is not (BUG-230).

    A union lets its next variant read a string that names nothing, and propagates a failure
    raised inside a module that does exist, so the two must be told apart.
    """

    @pytest.mark.parametrize(
        "path",
        ["hello", "no.such.module.Class", "os.nope", "hello world", "x/y", "1.5", "", ".hidden", "a..b", "pkg."],
    )
    def test_a_path_naming_nothing_is_not_found(self, path: str) -> None:
        """No module, no attribute, or a string that is no dotted path of identifiers at all."""
        with pytest.raises(SymbolNotFoundError):
            _import_dotted(path)

    def test_a_module_that_fails_while_importing_is_not_a_not_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """A broken dependency stays a plain SymbolImportError: the module exists."""
        pkg_dir = tmp_path / "bug230_broken_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "broken.py").write_text("import bug230_missing_dependency_xyz\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        request.addfinalizer(lambda: _purge_modules("bug230_broken_pkg"))

        with pytest.raises(SymbolImportError) as exc_info:
            _import_dotted("bug230_broken_pkg.broken.Thing")
        assert not isinstance(exc_info.value, SymbolNotFoundError)

    def test_an_undotted_name_imports_no_module(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest,
    ) -> None:
        """A bare word is looked up in builtins only: a module would be no class and no callable.

        So a plain word a union tries as a reference never runs a module's code.
        """
        (tmp_path / "bug230_undotted_mod.py").write_text("RAN = True\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        request.addfinalizer(lambda: _purge_modules("bug230_undotted_mod"))

        with pytest.raises(SymbolNotFoundError):
            _import_dotted("bug230_undotted_mod")
        assert "bug230_undotted_mod" not in sys.modules
        assert _import_dotted("bug230_undotted_mod.RAN") is True


class TestAFailingModuleIsNamed:
    """A module that fails while imported is named by itself, not by the path being tried (BUG-256)."""

    @pytest.fixture
    def modules(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        """Lay out sound and broken modules, every one prefixed ``bug256_``, on ``sys.path``."""
        (tmp_path / "bug256_broken.py").write_text("raise RuntimeError('boom')\n")
        (tmp_path / "bug256_helper.py").write_text("raise RuntimeError('helper boom')\n")
        (tmp_path / "bug256_app.py").write_text("import bug256_helper\n\n\nclass Thing:\n    pass\n")
        (tmp_path / "bug256_recursing.py").write_text("def f():\n    return f()\n\n\nf()\n")
        (tmp_path / "bug256_oom.py").write_text("raise MemoryError\n")
        (tmp_path / "bug256_sound.py").write_text("class Thing:\n    pass\n")
        (tmp_path / "bug256_brokenpkg").mkdir()
        (tmp_path / "bug256_brokenpkg" / "__init__.py").write_text("raise RuntimeError('pkg boom')\n")
        (tmp_path / "bug256_brokenpkg" / "sub.py").write_text("class Thing:\n    pass\n")
        (tmp_path / "bug256_pkg").mkdir()
        (tmp_path / "bug256_pkg" / "__init__.py").write_text("")
        (tmp_path / "bug256_pkg" / "badsub.py").write_text("raise RuntimeError('sub boom')\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        yield
        for name in [k for k in sys.modules if k.startswith("bug256_")]:
            sys.modules.pop(name)

    @pytest.mark.parametrize(
        ("path", "module", "cause"),
        [
            pytest.param("bug256_broken.Thing", "bug256_broken", "boom", id="module"),
            pytest.param("bug256_brokenpkg.sub.Thing", "bug256_brokenpkg", "pkg boom", id="package"),
            pytest.param("bug256_pkg.badsub.Thing", "bug256_pkg.badsub", "sub boom", id="submodule"),
            pytest.param("bug256_app.Thing", "bug256_app", "helper boom", id="the-module-it-imports"),
        ],
    )
    @pytest.mark.usefixtures("modules")
    def test_the_module_on_the_path_that_fails_is_named(self, path: str, module: str, cause: str) -> None:
        """The first module on the path whose import raises is the one named, its cause chained."""
        with pytest.raises(SymbolImportError) as exc_info:
            _import_dotted(path)
        assert str(exc_info.value) == f"Cannot import {path!r}: error loading module {module!r}: {cause}"

    @pytest.mark.parametrize(
        ("path", "error"),
        [
            pytest.param("bug256_recursing.Thing", RecursionError, id="recursion"),
            pytest.param("bug256_oom.Thing", MemoryError, id="memory"),
        ],
    )
    @pytest.mark.usefixtures("modules")
    def test_the_interpreters_own_errors_pass_through(self, path: str, error: type[BaseException]) -> None:
        """A RecursionError or a MemoryError is raised as it is: the import cannot tell whose it is."""
        with pytest.raises(error):
            _import_dotted(path)

    @pytest.mark.usefixtures("modules")
    def test_a_deep_caller_stack_does_not_blame_a_sound_module(self) -> None:
        """An import that runs out of the caller's stack raises the RecursionError, naming no module.

        Every spare stack depth up to 200 frames is tried, since where the import machinery runs
        out depends on the interpreter: each either imports or raises the RecursionError, and
        both happening shows the sweep crossed the depth the import needs.
        """

        def depth() -> int:
            frame, n = sys._getframe(), 0
            while frame is not None:
                frame, n = frame.f_back, n + 1
            return n

        def called_from(frames: int) -> object:
            return _import_dotted("bug256_sound.Thing") if frames == 0 else called_from(frames - 1)

        outcomes = set()
        for spare in range(1, 200):
            sys.modules.pop("bug256_sound", None)
            try:
                called_from(sys.getrecursionlimit() - depth() - spare)
            except RecursionError:
                outcomes.add("raised")
            else:
                outcomes.add("imported")
        assert outcomes == {"raised", "imported"}


class TestAPathNamesTheModuleThatPublishesTheObject:
    """A dotted path names the module that publishes the object, not the one that defines it (BUG-279).

    A platform module, a private submodule or an accelerator defines what a public module
    publishes, and a path through it loads on no other platform or version.
    """

    @pytest.mark.parametrize(
        ("path", "written"),
        [
            pytest.param("os.getcwd", "os.getcwd", id="platform-module"),
            pytest.param("os.path.join", "os.path.join", id="platform-path-module"),
            pytest.param("os.path.normpath", "os.path.normpath", id="platform-path-renamed"),
            pytest.param("os.path.getsize", "os.path.getsize", id="generic-path-module"),
            pytest.param("os.path.commonprefix", "os.path.commonprefix", id="generic-path-pure"),
            pytest.param("getpass.getpass", "getpass.getpass", id="renamed-per-platform"),
            pytest.param("asyncio.SelectorEventLoop", "asyncio.SelectorEventLoop", id="platform-submodule"),
            pytest.param("pathlib.Path", "pathlib.Path", id="private-submodule"),
            pytest.param("json.JSONDecodeError", "json.JSONDecodeError", id="public-submodule"),
            pytest.param("concurrent.futures.ThreadPoolExecutor", "concurrent.futures.ThreadPoolExecutor", id="lazy"),
            pytest.param("functools.reduce", "functools.reduce", id="accelerator"),
            pytest.param("threading.Lock", "threading.Lock", id="thread-accelerator"),
            pytest.param("io.StringIO.write", "io.StringIO.write", id="accelerator-c-method"),
            pytest.param("types.FunctionType", "types.FunctionType", id="builtins-unnamed"),
            pytest.param("bisect.bisect", "bisect.bisect_right", id="own-name-first"),
        ],
    )
    def test_a_stdlib_object_is_named_where_python_publishes_it(self, path: str, written: str) -> None:
        """What a module defines on one platform or version, its public module publishes on all."""
        obj = _import_dotted(path)
        assert dotted_name(obj) == written
        assert _import_dotted(written) == obj

    def test_ntpath_is_written_as_os_path_where_it_is_os_path(self) -> None:
        """Where ``ntpath`` is ``os.path``, its functions are one object under both names, written as ``os.path``.

        Elsewhere ``ntpath.join`` is another function than ``os.path.join``, and keeps its name.
        """
        expected = "os.path.join" if os.path is ntpath else "ntpath.join"
        assert dotted_name(ntpath.join) == expected

    @pytest.fixture
    def packages(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        """Lay out packages publishing what their submodules define, every one prefixed ``bug279_``."""
        for package in ("bug279_open", "bug279_closed", "bug279_lazy"):
            (tmp_path / package).mkdir()
        (tmp_path / "bug279_open" / "models.py").write_text(
            "class Dog:\n"
            "    @staticmethod\n"
            "    def make():\n"
            "        return Dog()\n\n"
            "    class Collar:\n"
            "        pass\n\n\n"
            "class _Hidden:\n"
            "    pass\n\n\n"
            "def _impl():\n"
            "    pass\n\n\n"
            "class Forged:\n"
            "    pass\n\n\n"
            "Forged.__qualname__ = 'Dog'\n"
        )
        (tmp_path / "bug279_open" / "__init__.py").write_text(
            "from bug279_open.models import Dog, _Hidden, _impl as run\n"
        )
        (tmp_path / "bug279_closed" / "models.py").write_text("class Cat:\n    pass\n")
        (tmp_path / "bug279_closed" / "__init__.py").write_text(
            "from bug279_closed.models import Cat\n\n__all__ = []\n"
        )
        (tmp_path / "bug279_lazy" / "thread.py").write_text("class Thread:\n    pass\n")
        (tmp_path / "bug279_lazy" / "process.py").write_text("class Process:\n    pass\n")
        (tmp_path / "bug279_lazy" / "broken.py").write_text("class Broken:\n    pass\n")
        (tmp_path / "bug279_lazy" / "__init__.py").write_text(
            "import importlib\n\n"
            "__all__ = ['Broken', 'Process', 'Thread']\n\n\n"
            "def __getattr__(name):\n"
            "    if name == 'Broken':\n"
            "        raise ValueError('hook boom')\n"
            "    if name in __all__:\n"
            "        return getattr(importlib.import_module(f'bug279_lazy.{name.lower()}'), name)\n"
            "    raise AttributeError(name)\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        yield
        for name in [k for k in sys.modules if k.startswith("bug279_")]:
            sys.modules.pop(name)

    @pytest.mark.parametrize(
        ("path", "written"),
        [
            pytest.param("bug279_open.models.Dog", "bug279_open.Dog", id="no-all"),
            pytest.param("bug279_open.models.Dog.make", "bug279_open.Dog.make", id="static-method"),
            pytest.param("bug279_open.models.Dog.Collar", "bug279_open.Dog.Collar", id="nested-class"),
            pytest.param("bug279_open.models._impl", "bug279_open.run", id="renamed"),
            pytest.param("bug279_open.models._Hidden", "bug279_open.models._Hidden", id="private-name"),
            pytest.param("bug279_closed.models.Cat", "bug279_closed.models.Cat", id="unlisted-in-all"),
            pytest.param("bug279_open.models.Forged", "bug279_open.models.Forged", id="forged-qualname"),
        ],
    )
    @pytest.mark.usefixtures("packages")
    def test_a_package_publishes_what_import_star_takes(self, path: str, written: str) -> None:
        """Its ``__all__``, or every name not starting with ``_``; an object defined in a class goes with it.

        A class whose qualified name was rewritten to another class's is written by the name its
        module publishes it under, which imports back as it, where its qualified name does not.
        """
        assert dotted_name(_import_dotted(path)) == written

    @pytest.mark.usefixtures("packages")
    def test_a_lazy_hook_that_fails_publishes_nothing(self) -> None:
        """The hook's error is not raised from the path: the next module that publishes the class is."""
        broken = _import_dotted("bug279_lazy.broken.Broken")
        assert dotted_name(broken) == "bug279_lazy.broken.Broken"

    @pytest.mark.usefixtures("packages")
    def test_a_lazy_export_runs_no_other_names_hook(self) -> None:
        """The object's own name is read with ``getattr``; the package's other lazy names are not."""
        thread = _import_dotted("bug279_lazy.thread.Thread")
        assert dotted_name(thread) == "bug279_lazy.Thread"
        assert "bug279_lazy.process" not in sys.modules

    def test_a_class_defined_in_a_function_keeps_its_unloadable_path(self) -> None:
        """No module publishes it, so its path is its qualified name, which a dump refuses."""

        class Local:
            pass

        assert dotted_name(Local) == f"{__name__}.{Local.__qualname__}"
