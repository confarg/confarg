---
filed: 2026-11-12
where:
  - src/confarg/cli/_build.py::_collect_struct_specs  # the subclass recursion BUG-113 would filter
  - src/confarg/cli/_build.py::_collect_loop_typed_specs  # what registers the flags a naming types, when argv spells them
  - tests/cli/cyclopts/test_cyclopts_integration.py  # BUG-114's regression test, test_subclasses_sharing_a_struct_field_name_share_its_group
---

# Q-10 — What should `--help` and completion list below a field the subclasses type differently?

Filed while planning [BUG-113](../bugs/BUG-113-a-path-below-a-field-the-subclasses-type-differently-is-refused-by-vanilla-and-accepted-by-the-adapters.md), which is `blocked_by` it.
The BUG-113 fix as its ticket words it, registering nothing where the canonical walk answers `None`, takes flags out of `--help` and of shell completion that are listed today, and makes BUG-114's regression test unreachable.
Both are the maintainer's.

The shape, from the ticket (`Base` with `S1(inner: A)` and `S2(inner: B)`, `Cfg.item: Base`):

```python
@dataclass
class A:
    a: int = 0


@dataclass
class B:
    a: int = 0
    b: str = ""


@dataclass
class Base: ...


@dataclass
class S1(Base):
    inner: A = field(default_factory=A)


@dataclass
class S2(Base):
    inner: B = field(default_factory=B)


@dataclass
class Cfg:
    item: Base = field(default_factory=Base)
```

## What changes

The fix was simulated as a plugin that drops a subclass spec whose path the walk refuses (run, argparse; the other adapters take the same specs).

`make_parser(Cfg, argv=[]).print_help()`, untagged, today:

```text
usage: h113.py [-h] [--item JSON] [--item.class DOTTED.CLASS.PATH]
               [--item.inner JSON] [--item.inner.a INT] [--item.inner.b STR]
               [--config [FILE ...]] ...
item:

  --item.class DOTTED.CLASS.PATH
  --item.inner JSON     (default: A(a=0))

item.inner:

  --item.inner.a INT    (default: 0)
  --item.inner.b STR    (default: '')
```

Under the simulated fix the usage reads `[--item.inner JSON] [--config [FILE ...]] ...` and the `item.inner:` group is gone.

`make_parser(Cfg, argv=["--item.class", "__main__.S1"]).print_help()`, the tagged command line, shows the same `item.inner.a` and `item.inner.b` today, and under the simulated fix shows neither: the flags a naming types register only when argv spells them (`_collect_loop_typed_specs`), never as the named class's whole field list.
So a user who types the tag and then `--help` sees less than today, though `--item.class __main__.S1 --item.inner.a 5` still works.

Shell completion loses the same two paths until the tag and the flag are typed, since the argparse completion builds on the same registration.

What does not change, from a run of eight spellings on all five front-ends (untagged, tag before the flag, tag after, a whole-value JSON naming, a `--config` file, a `--config.item` mount, an environment tag, the other subclass): every spelling that completes today still completes.
The untagged and tag-after spellings are refused by vanilla today and still are; on the four adapters the refusal moves from confarg's `UnknownArgumentError` at merge to the framework's own usage error (exit 2, "unrecognized arguments") at parse.

## The question

What should `--help` and completion list for a field the subclasses type differently, untagged and with a tag naming one of them?

- **A, the ticket as written.**
  Register nothing below the field where the walk refuses the path, tagged or not.
  `--help` and completion lose `--item.inner.a` and `--item.inner.b`; the tagged help lists only what argv spells.
  Discovery of a plugin's own flags is [FEAT-15](../features/FEAT-15-inspect-flags-of-unnamed-class.md)'s, which could take "list the flags of the class a tag names" into its scope.
  Smallest change, and the adapters then refuse what vanilla refuses at the same stage as every other unknown flag.
- **B, A plus the named class's fields.**
  Where a tag or a naming names a subclass (argv, a file, the environment), register that class's fields at the node, typed by the naming, so `--item.class __main__.S1 --help` lists `--item.inner.a` as today.
  Keeps tagged help whole, but it is new design: registering the flags of the class a naming selects, not only the ones argv spells, raises how they are grouped (dynamic flags carry no group today) and what `--help` says for them, and it overlaps FEAT-15.

Precedent, read from FEAT-15 (jsonargparse 4.52.0, verified there, not re-run here): a subclass's sub-arguments never appear in the top-level help, and `--<field>.help CLASS_PATH` prints exactly one class's parameters, which is A with FEAT-15's opener.

## BUG-114's regression test

`test_subclasses_sharing_a_struct_field_name_share_its_group` is the only test of the suite that fails under the simulated fix (12735 passed, 1 failed).
It builds a `populate_app` over exactly this shape, `_GroupS1.inner: _GroupA` and `_GroupS2.inner: _GroupB`, and asserts `--item.inner.a` and `--item.inner.b` are both registered, to prove cyclopts registers the shared group `item.inner` once (BUG-114, closed).
The fix removes those flags, so the test cannot pass unchanged, and the collision it guards cannot be reached any more:

- subclasses that agree on `inner`'s type merge into one spec of one group, so there is no second group to collide (checked on cyclopts: `item.inner.a` registered once);
- a tag-typed flag is registered without a group.

The project's rule is that a closed bug's test stays green unchanged, so rewriting it, to assert the refusal and that the build still does not crash, or deleting it, is for the maintainer to allow.
Under B the test would still fail too, since an untagged build still lists nothing.

Answering this unblocks BUG-113, whose fix then follows the chosen option, with the cast correction recorded on that ticket.
