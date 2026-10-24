# Type-guided parsing

Argv is not parsed as generic `key=value` pairs: each dotted path is resolved against the target type (`_resolve_field_type`) to decide whether a segment names a field, indexes a sequence, keys a dict, enters a callable spec, or is a cast.
That is what lets `--db.hosts.0.port 5432` produce the right nested structure and what lets values be coerced eagerly.
Env parsing walks the same type tree ([environment parsing](../environment-parsing.md#environment-parsing)).

An unknown flag is an error (`UnknownArgumentError`); an unresolvable path under a dict is accepted as a dict key.

The one path not resolved *while* it is parsed is the config flag's subpath: the flag is intercepted before field lookup ([design decisions](../design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)), so the check runs once the interception is over (`_check_mount_subpath`, one walk shared with the environment channel and the adapters' rescan).
A subpath that names no node — a misspelled field, or a descent through a scalar — is an error at parse time, not a silent mount at an invented key that surfaces much later as an unknown-field error from `build()` (BUG-50, closed).
What the node *holds* is still not the scan's question: a path is accepted at any depth it resolves to, because whether the fragment fits is the mount's call.

## One walk, many questions

Every question the parsers ask about a dotted path is a question about one walk over the target type: which type the path reaches (`_field_types`, folded by `_resolve_field_type`), whether it keys into a callable's spec (`_addresses_callable_key`), whether it is a collection patch (`_is_collection_patch_path`), whether a dict lies above it (`_is_dict_at_path`).
The walk is `_parse_cli._walk_path`, and the questions are short loops over what it returns (REF-43).
Its step is `_parse_cli._step`, taken from every state of a segment once (`_step_edges`), which a walker over data takes too, from each node to its child, carrying each state it lands on once ([locals](../locals.md#per-node-namespaces)).

**The walk forks at a union and goes on from each state once.**
A union met before the path ends is stepped once per non-None variant, in variant order.
A *state* is all the next step reads of what came before: the type reached, a union left unexpanded, and whether the walk is below an untyped token or a spec (`_WalkState`).
For each segment the walk keeps the *edges* it stepped: from a state, standing on a *stone*, to the state it lands on, `None` where that way refuses the segment; the ways that land on the same state go on as one, so a union met at every level costs a step per variant, not a branch per choice of variants.
A *way* is a run of edges from the root, the walk that took one variant at every union it met.
A stone holds two types: the one the walk *reached* there, a union left unexpanded, which is what a walk of that prefix alone answers; and the *node* the way stands on, the resolved variant it took.
The steps between stones are the walk's own and every question gets them: a member, an index, a dict value, or any key below an `Any`, which is a `dict[Any, Any]` and answers `Any` again ([callables](../callables.md#an-any-node-reads-every-opener)) (`_advance_field_type`); a local-variables namespace, entered as a `dict[str, Any]`; an subtree of a computation's spec (`_opens_spec_subtree`: a callable's `bind`, `call` or `args` key, the `call` or `args` key of a field that takes a typed call where no member holds it), a `bind` or `call` holding a Callable target and an `args` below which every segment is a `str` where no opener names the target ([callables](../callables.md#cli)); and, last, the union tag, reached only where no member of its spelling is ([real field wins](casts-and-reserved-words.md#real-field-wins)), whose value is a leaf.

**A node that names a class types the step below it.**
Asked with a naming view (`named`, the data a path is typed against), a node holding an opener or a tag steps into the class it names (`_naming.named_child`) and a union into the variant it names (`_naming.named_variant`), as the typed merge and construction read it: a field of the class, a Callable target, a target's parameters, refused where the class declares none.
A node naming nothing is stepped by its declared type, and below a Callable that is a `str` at any depth ([design decisions](../design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names)).

Each question reads the part of the walk it needs, and states its own difference in its own lines:

- `_field_types` reads the states the walk ends on, each type once, in variant order.
- `_addresses_callable_key`: does any edge stand on a callable, or step into a typed call, before the path ends.
- `_is_collection_patch_path`: does any edge stand on a list, tuple, set or dict, or enter a namespace.
  A namedtuple stops nothing: the static walk lists its own fields and indices, so a path ending on one is no patch, but a list, a dict or a namespace below its fields is as open-ended as one below a struct's (BUG-157).
  Nor does a callable: past one the walk stands on nothing but `str` — every key of a spec is one, a bind key opens a `str` subtree — and a callable holds no namespace, so the stop it once had never changed the answer (REF-86).
- `_is_dict_at_path`: does any way stand on a dict before the path ends.
  It reads the node, not the reached type: a field typed `dict[str, Any] | None` or `dict[str, Any] | Inner` reaches the union, which is no dict, and a prefix the ways disagree on folds to `str` (`_common_type`), so reading what `_resolve_field_type` of the prefix answers refused every key below a union-typed dict field — on the CLI only, for the environment checks a path's first segment alone and never asked (BUG-158).
  "Any way", as every other question here asks: a path one variant accepts is accepted, and which variant the value is built as is construction's call.
  It is one of the two questions that read a way's history: a way that refuses the path at a sequence below the dict takes nothing (BUG-170), so it counts the dicts on the ways that end otherwise (`_Walk.edges_on_ways`); the other is the adapters' registered-leaf scan, which counts the leaves on the ways that accept the whole path.

Before, each question was its own copy of the loop, restating the union recursion and the bail-out around a one-line test, and two of them stopped where the others went on: neither `_addresses_callable_key` nor `_is_collection_patch_path` entered a namespace, followed a bind key or took the tag.
Taking those steps changes neither answer, and that is what made the collapse possible: a namespace is a `dict[str, Any]` and holds no callable, the collection question answers yes on entering it, and past a bind key or the tag a branch stands on nothing but `str`.
A mistake in a shared walk is silent in every channel and every front-end at once, so the cross-channel contract suite pins each question at a union (`TestUnionPathWalkContract`).

This is the collapse [look-alike code that behaves differently stays apart](../design-decisions/look-alike-code-that-behaves-differently-stays-apart.md#look-alike-code-that-behaves-differently-stays-apart) keeps: the copies were the same code, and the walk takes no parameter for any caller's difference (`tag_fallback` is the walk's own, asked by `_names_tag_by_fallback`).
No question stops a way since the callable's stop went (REF-86), so the questions are asked of every edge.

**Each state once, not each branch.**
The walk once yielded whole branches, each the walk that took one variant at every union it met, with a stone per segment and its end; a union met at every level doubled them, so a 14-level path through `A | B | None` took a second on argv and five in the environment, a 30-level one hours (BUG-260).
It now goes on from each state once, as a Thompson-style regex engine (RE2, Go's `regexp`, Rust's `regex`) keeps the set of states its automaton is in at each character where a backtracking one (PCRE, Python's `re`) follows every path: the walk costs a step per state and variant per segment.
The pairing the questions read survives on the edges, which a flat stream of nodes would lose: a refusal is an edge landing on `None` with the stone it stood on (`_refuses_at_a_sequence`), an end a state the last segment's edges land on, and what a way stood on before its end is the edges from which the rest of the path reaches an end the question counts, which `_Walk.edges_on_ways` keeps by walking back from the last segment.
Two answers moved with it, neither read before: `_field_types` lists each end once, where it listed one per branch, which every caller folds, collects or tests with `any`; and where several ways refuse a variable at a sequence, the refusal names the shallowest segment any of them refuses (`_unreached` since BUG-265), where it named the first variant's ([collection patches](collection-patches.md#a-segment-below-a-sequence-is-an-index)).
The environment still spells each segment by the walk of the path above it (`_env_spelling`), so a variable costs a walk per segment: quadratic in its depth, which [the 64-level bound](../design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels) caps at a tenth of a second at the bound, kept over a second loop over the step outside the walk.

Rejected: handing the walk the question as a callback, which answers one verdict where the questions read what each way stood on and where it ended.
Rejected: carrying a question's history in the state (a "stood on a dict" bit), which keeps the states as few, but gives the walk a field per caller's question.
Rejected: threading the data's naming into every walker, which narrows a union to the variant it names but leaves a path nothing names exponential, and cannot reach a walk that runs before argv is read (`_tags`) or with no data at all (the adapters' registration).
