# Type-guided parsing

Argv is not parsed as generic `key=value` pairs: each dotted path is resolved against the
target type (`_resolve_field_type`) to decide whether a segment names a field, indexes a
sequence, keys a dict, enters a callable spec, or is a cast. That is what lets
`--db.hosts.0.port 5432` produce the right nested structure and what lets values be coerced
eagerly. Env parsing walks the same type tree ([environment parsing](../environment-parsing.md#environment-parsing)).

An unknown flag is an error (`UnknownArgumentError`); an unresolvable path under a dict is
accepted as a dict key.

The one path not resolved *while* it is parsed is the config flag's subpath: the flag is
intercepted before field lookup
([design decisions](../design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)), so the check runs
once the interception is over (`_check_mount_subpath`, one walk shared with the environment
channel and the adapters' rescan). A subpath that names no node — a misspelled field, or a
descent through a scalar — is an error at parse time, not a silent mount at an invented key
that surfaces much later as an unknown-field error from `build()` (BUG-50, closed). What the
node *holds* is still not the scan's question: a path is accepted at any depth it resolves to,
because whether the fragment fits is the mount's call.

## One walk, many questions

Every question the parsers ask about a dotted path is a question about one walk over the target
type: which type the path reaches (`_field_types`, folded by `_resolve_field_type`), whether it
keys into a callable's spec (`_addresses_callable_key`), whether it is a collection patch
(`_is_collection_patch_path`), whether a dict lies above it (`_is_dict_at_path`). The walk is
`_parse_cli._walk_path`, and the questions are short loops over what it yields (REF-43).

**The walk forks at a union and yields whole branches.** A union met before the path ends is
walked once per non-None variant, in variant order, so each branch is the walk that took one
variant at every union it met. A branch carries a *stone* per segment it stood before and the
type it reached at the end, `None` if it refused a segment. A stone holds two types: the one
the walk *reached* there, a union left unexpanded, which is what a walk of that prefix alone
answers; and the *node* the branch stands on, the resolved variant it took. The steps between
stones are the walk's own and every question gets them: a member, an index or a dict value
(`_advance_field_type`); a local-variables namespace, entered as a `dict[str, Any]`; an
opener whose value is a target (`_opens_target`: a callable's `bind` or `call` key, the
`call` key of a field that takes a typed call), below which every segment is a `str`; the
union tag, reached only where no member of its spelling is
([real field wins](casts-and-reserved-words.md#real-field-wins)); and, last, a segment no
member reaches below a path where the command line opens a typed call, a `str` leaf
([callables](../callables.md#cli)).

Each question reads the part of a branch it needs, and states its own difference in its own
lines:

- `_field_types` reads the ends of the branches that accept the path.
- `_addresses_callable_key`: does any branch stand on a callable, or step into a typed call,
  before the path ends.
- `_is_collection_patch_path`: does a branch stand on a list, tuple, set or dict, or enter a
  namespace, before it stands on a callable. A namedtuple stops nothing: the static walk lists
  its own fields and indices, so a path ending on one is no patch, but a list, a dict or a
  namespace below its fields is as open-ended as one below a struct's (BUG-157). The stop is
  per branch, which is why the walk yields branches rather than a flat stream of nodes: a
  stream loses which branch a node belongs to, and with it the stop that leaves the sibling
  branches walking.
- `_is_dict_at_path`: does any branch stand on a dict before the path ends. It reads the node,
  not the reached type: a field typed `dict[str, Any] | None` or `dict[str, Any] | Inner`
  reaches the union, which is no dict, and a prefix the branches disagree on folds to `str`
  (`_common_type`), so reading what `_resolve_field_type` of the prefix answers refused every
  key below a union-typed dict field — on the CLI only, for the environment checks a path's
  first segment alone and never asked (BUG-158). "Any branch", as every other question here asks:
  a path one variant accepts is accepted, and which variant the value is built as is
  construction's call.

Before, each question was its own copy of the loop, restating the union recursion and the
bail-out around a one-line test, and two of them stopped where the others went on: neither
`_addresses_callable_key` nor `_is_collection_patch_path` entered a namespace, followed a bind
key or took the tag. Taking those steps changes neither answer, and that is what made the
collapse possible: a namespace is a `dict[str, Any]` and holds no callable, the collection
question answers yes on entering it, and past a bind key or the tag a branch stands on nothing
but `str`. A mistake in a shared walk is silent in every channel and every front-end at once,
so the cross-channel contract suite pins each question at a union
(`TestUnionPathWalkContract`).

This is the collapse
[look-alike code that behaves differently stays apart](../design-decisions/look-alike-code-that-behaves-differently-stays-apart.md#look-alike-code-that-behaves-differently-stays-apart)
keeps: the copies were the same code, and the walk takes no parameter for any caller's
difference (`tag_fallback` is the walk's own, asked by `_names_tag_by_fallback`; `calls` is
what the command line opens, `_typed_call_openings`, which every CLI question about the same
argv gets alike, and which a caller with no argv leaves empty). Rejected:
handing the walk the question as a callback, which would need a three-way answer — yes, no,
keep walking — to stop one branch, and walking breadth-first by depth, which serves the fold
but cannot stop one branch either. The shape is `os.walk`'s and `ast.walk`'s: one traversal as
a generator, each question a loop over what it yields.
