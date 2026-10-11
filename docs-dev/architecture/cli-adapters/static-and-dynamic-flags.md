# Static and dynamic flags

**Static flags** come from a walk of the target type (`build_static_flags`): leaves, tuples,
namedtuples (whole, then per name, per index and per negative index whatever that field type
takes as a struct's field, recursively — the index spellings hidden from `--help`: BUG-68, BUG-80,
BUG-112), union tags and variant fields, plain callable
openers (`.bind`/`.class`/`.call`), `--config` and `--config.<mount point>` (a struct field, a dict field — where a fragment of
unknown keys belongs — or a union whose variants are all structs, whose help entry says the
fragment's top level must name its variant with the tag, because the field's own flags are
per-variant), and
`--config.<locals>` (the CLI way to declare locals). `build_static_flags` takes `argv` too, but
only to import the classes it names by `union_tag` before the walk starts; it never adds a flag
from it, so `argv=[]` still describes exactly the declared type.

**Dynamic flags** (`build_dynamic_flags`) are those whose existence depends on what the
user typed, found by scanning argv (and config files named on argv):

- the target's parameters (`--f.<p>`) of callables, whether the target is named by
  `--f.bind/.class/.call`, by a whole-value `--f '{"class": …}'` blob, or by a config file.
  A nested target spec names two: its own parameters below the opener (`--f.call.<p>`), and
  the arguments of the callable it yields beside it (`--f.<p>`). One function,
  `_callable_argument_targets`, lists them for registration and for argparse's completion
  ([callables](../callables.md#cli));
- escaped openers (`--f._class`) actually typed;
- a typed call's opener (`--n.call`) and its siblings, on a field that is no Callable,
  registered only when typed, on the same help-noise ground as the escaped openers: a sibling
  only where argv opens the call (`_parse_cli._typed_call_openings`, the answer vanilla's
  loop reads too). Its discovered flags carry no group, since a struct field's own flags
  already hold the field's group name, and cyclopts refuses two groups of one name
  ([design decision](../design-decisions/a-typed-call-sibling-needs-its-opener-on-the-command-line.md));
- keys typed in argv below a callable that no signature describes: a nested `bind` or `call`
  target spec's keys in either spelling (`--f.bind.class`, `--f._call.x`), and a directive word
  the opener left inactive, which is ordinary data
  ([callables](../callables.md#plain-and-escaped-directives));
- `--config.<any.depth>[+]`;
- collection patches (`--f.N`, `--f+`, `--f.N-`, `--f.key`) and `.json` casts;
- the typed scalar cast flags on plain leaf fields (`--host.str`, BUG-72), registered only
  when typed on the same help-noise ground as `.json`: the leaf's own flag is the ordinary
  spelling, and one flag per castable type would clutter `--help` for an escape hatch. The
  leaf answer is `_scalar_cast_parent_is_leaf`: struct, collection, dict, callable and
  registered-leaf parents keep their own spellings and their cast spelling stays refused
  (BUG-93). Which spelling wrote last, the plain flag or a cast, is vanilla's loop's answer,
  since it writes the occurrences sequentially;
- the flat tagged-leaf flags typed below a registered leaf field (`--id.class`,
  `--id.hex`, BUG-56), or below a registered leaf that *is* the target — the root, with
  no field to descend from, is the leaf at the empty prefix of the path (BUG-71) —
  registered only when typed, on the same help-noise ground as the
  escaped openers: a registered leaf's ordinary spelling is its scalar, and one flag per
  `__init__` parameter would clutter `--help` for the escape hatch. A root's parameters
  are an exception the *static* walk already owns: the root is walked structurally, as a
  union holding the same leaf is, so only its tag flag is argv-scanned.
- the union-tag flags the static walk gave none (`--<path>.<union_tag>`, and
  `--<union_tag>` at the root, BUG-92 / BUG-106), registered only when typed, on the same
  help-noise ground: a path's ordinary spelling is its own value or fields. They are
  replayed writes, admitted wherever the walk reaches the tag by its fallback
  ([a tag is a replayed write](collection-patch-parity.md#a-tag-is-a-replayed-write)).
  `import_tagged_classes` runs at the start of `build_dynamic_flags`, so a tag naming a real
  subclass is visible to every scan that follows.

Why dynamic: the framework must accept every token the user types, but registering every
possible index, key or bind parameter statically is impossible, and registering rarely used
forms (escaped openers, `.json`) statically would clutter `--help`. Dynamic registration is
**best-effort**: any exception returns no extra flags rather than breaking `populate_*`; the
worst case is the framework rejecting a flag.

Best-effort, but not silent (BUG-5). A failure emits a `ConfargWarning` naming the original
exception: the rejection the user then sees comes from the host framework and says nothing
about the real cause, so without the warning a bug inside registration is indistinguishable
from a flag the user mistyped. Swallowing stays the default because the alternative — letting
the exception escape — takes down every `populate_*` call and shell completion over a flag
that may not even be typed; a caller who wants it fatal has
`warnings.filterwarnings("error", ConfargWarning)`, the hatch `exceptions.py` documents. The
warning fires from the one shared `build_dynamic_flags`, so all four adapters report
identically; vanilla `load()` registers nothing and has no analogue.

Escaped opener specs carry no group: sharing a group name with a different description
trips cyclopts' "2 distinct Group objects with same name" check.

Everything below a callable field, and below a typed call, is the one family registered
from the **path** rather than from a signature (BUG-25, BUG-28). `_parse_cli._addresses_callable_key` is the shared
predicate, so whatever the vanilla parser accepts below the field the host framework accepts
too. A signature cannot answer here at all: not for a bind subkey in the spelling the opener
left inactive, whose keys are data ([callables](../callables.md#plain-and-escaped-directives)); not
for a sibling kwarg the named target does not carry; and not for a field with no opener
anywhere, which names no target to inspect. Letting the framework reject those first is what
made the five front-ends disagree — the flag is the adapter's to accept and the kwarg is
construction's to judge, so the user hears the real complaint (`Unknown kwargs [...]`,
`must specify one of 'bind', 'class', 'call' or 'classfn'`) instead of `unrecognized arguments`.

The values are vanilla's loop's to write, and it has always written every key below a
callable field — the opener decides what a key *means*, never whether it is stored. (The other
half of BUG-28 was the adapters' own collector, which gathered sibling `--<field>.<param>` flags
only when an opener was present.)

The predicate answers about a *path*, so the caller strips an append/delete suffix before
asking. Those flags are registered by the patch-flag scan, in the shape their mode demands; claiming `--f.<key>-` here registered a value-less delete as if it took an
argument (BUG-29).
