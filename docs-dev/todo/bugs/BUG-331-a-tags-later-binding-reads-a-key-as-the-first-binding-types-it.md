---
filed: 2026-11-12
where:
  - src/confarg/_naming.py::named_variant  # types the keys below a tag by the first binding
  - src/confarg/_parse_cli.py::_step  # the walk narrows to the variant named_variant answers
  - src/confarg/_typed_merge.py::_union_child  # the merge, and the reader through it, step into that variant
  - src/confarg/_typed_read.py::TypedReading  # a reference reads the key by the type the merge steps to
effort: M
needs_design: true  # the pass decides whether the keys are typed by every binding, and what a reference reads
risk: high
impact: config  # option B changes what two configurations that build today build
severity: critical  # a reference reads a value the built field does not hold, with no error
introduced_by: [FEAT-13]  # the first binding types the keys, "as construction tries it first"
---

# BUG-331 — A tag's later binding reads a key as the first binding types it

A tag naming a class two variants bind apart (`Box2[bool] | Box2[int]`) builds the first binding that builds, but argv, the environment and a reference read the keys below it by the first binding's types (`_naming.named_variant`).
When a later binding builds, it gets a token the first one already coerced, a cast flag only it holds is refused, and a reference reads the value as the first binding would build it.
A file, whose values no walk coerces, builds what construction picks.
[BUG-300](BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md), as decided, extends the same reading to bindings of two classes (`Both` under `Src[bool] | Snk[int]`).

Option B, prototyped while planning BUG-300 (monkeypatched, not built): below a tag selecting several distinct bindings, the walk forks over the bound variants only, as it does over an untagged union's, so a key is typed where every binding agrees and kept as text where they disagree; the merge reads a key by that agreement, and the environment lists the one class's names.
On all five front-ends it made case 1 build `Box2(item=1, other=7)` from argv and from the environment, and case 2 build `Box(item='3')`.
It changes two configurations that build today:

- `u: Box2[int] | Box2[Any]` with `--u.class Box2 --u.item 1 --u.other x` builds `Box2(item=1, other='x')` today and `Box2(item='1', other='x')` under B, the text a lone `Box2[Any]` reads the token as; a file's `item: 1` still builds `1`.
- `w: Box2[float] | Box2[Any]` with `{w: {class: Box2, item: 3, other: 4.5}, label: "v${w.item}"}` builds `item=3.0` either way, and `label` is `'v3.0'` today and `'v3'` under B, which reads the key as written where the bindings disagree.

So neither A nor B makes a reference read the built value in every case: case 3 is wrong under A, the second configuration above under B. An exact answer needs the reader to read through the binding construction builds, as `typedload._construct.read_union_leaf` does for a union leaf ([a typed leaf reads as its object](../../architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object)), which the node's other keys decide.

Precedent, run: jsonargparse 4.53 tries each member of `Union[Box2[bool], Box2[int]]` on the whole value, and builds `Box2(1, 7)` from `--x jmod.Box2 --x.item 1 --x.other 7` and from `{"class_path": "jmod.Box2", "init_args": {"item": "1", "other": "7"}}` alike.

Origin: latent since FEAT-13, which let a tag pick among one generic class's bindings by the value (`_construct_bound_tag`) and had the naming walk type the keys by the first binding, "as construction tries it first"; the walk's eager coercion, a cast's admission by the branch the walk reaches (BUG-214) and the reader's typed step all read that one binding.
[The limitations](../../architecture/limitations.md#subclasses) record the token half (`Box[str]` cannot be given the token `3` on argv) as a boundary, not the casts or the reference.

```python
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import confarg
import confarg.exceptions


@dataclass
class Box[T]:
    item: T


@dataclass
class Box2[T]:
    item: T
    other: T


@dataclass
class C:
    u: Box2[bool] | Box2[int] | None = None
    b: Box[int] | Box[str] | None = None
    w: Box2[float] | Box2[Any] | None = None
    label: str = ""


def show(label, fn):
    try:
        print(f"{label}: {fn()!r}")
    except confarg.exceptions.ConfargError as e:
        print(f"{label}: {type(e).__name__}: {e}")


def config_file(data):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    return path


# 1. A token argv or a variable coerces by the first binding reaches the binding that builds coerced.
argv = ["--u.class", "__main__.Box2", "--u.item", "1", "--u.other", "7"]
show("argv", lambda: confarg.load(C, argv=argv).u)
env = {"APP_U__CLASS": "__main__.Box2", "APP_U__ITEM": "1", "APP_U__OTHER": "7"}
show("env ", lambda: confarg.load(C, argv=[], env=env, env_prefix="APP_").u)
path = config_file({"u": {"class": "__main__.Box2", "item": 1, "other": 7}})
show("file", lambda: confarg.load(C, argv=["--config", path]).u)

# 2. A cast flag the second binding holds is refused, where a file's cast reaches it.
show("argv", lambda: confarg.load(C, argv=["--b.class", "__main__.Box", "--b.item.str", "3"]).b)
cast = {"b": {"class": "__main__.Box", "item": {"__cast__": "str", "__value__": "3"}}}
show("file", lambda: confarg.from_dict(C, cast).b)

# 3. A reference reads the key by the first binding where the second builds.
data = {"w": {"class": "__main__.Box2", "item": 3, "other": "x"}, "label": "v${w.item}"}
show("build", lambda: confarg.build(C, data))

# expected: argv, env and file each Box2(item=1, other=7); argv and file each Box(item='3'); label='v3'
# actual:   argv: TypeCoercionError: Cannot coerce bool True to int at 'u.item'
#           env : TypeCoercionError: Cannot coerce bool True to int at 'u.item'
#           file: Box2(item=1, other=7)
#           argv: UnknownArgumentError: Unknown argument: '--b.item.str' (field 'b.item.str' not found)
#           file: Box(item='3')
#           build: C(u=None, b=None, w=Box2(item=3, other='x'), label='v3.0')
```
