# Review of `yrruworo` — fix(cli)!: Type each key below a node by the class it names, on every channel (BUG-233, BUG-236, BUG-110, BUG-114)

Reviewed by reading the revision's full diff (204 files; the source half is the substance — `_naming.py` new, `_parse_cli.py`, `_parse_env.py`, `_typed_merge.py`, `_pipeline.py`, the four adapters, `cli/_sources.py` new, `cli/_build.py`), by probing the corners against the working copy (Python 3.12) with `merge()` for vanilla and `make_parser`/click for the adapters, and by running the revision's own tests (`tests/cli/test_backend_contract.py -k ANodeTypesItsKeys`, 129 cases over every front-end, all green).
The probes were run on the working copy, which sits eight revisions after `yrruworo`; every finding below was checked to still hold there, and to be absent from the code before the revision.
`ty check` passes on the tree as it stands.

## What the revision gets right

- **One decision-maker, two consumers.**
  `_naming.named_child` / `named_variant` answer "what is this key below a node that names a class" for both the CLI type walk and the typed merge, so the channel that *refuses* a key at parse and the channel that *builds* it cannot drift — BUG-84/86's old "let `build()` judge" whack-a-mole is gone at the root.
  Probed end to end: a subclass that overrides an annotation is coerced by the subclass, a key only another subclass declares is refused, nothing lies below a tag's or an opener's class-path value (`--db.class.junk` refused), and a restated opener drops the tokens the first class accumulated (`--json` naming plus a later `--db.class` does not leak the JSON's keys).
- **The layering is honest, and documented with rare candor.**
  The pipeline reads the layers lowest first, each typed over what lies below it; the design-decision note states the whole rule ("which naming types a key"), lists five rejected alternatives with reasons, records the costs (an opener after its keys takes one token; `merge()` now coerces a key as the named class reads it, not as the token stood), and cites real precedents (jsonargparse, LightningCLI, click's envvar-at-registration, Hydra).
  BUG-262 (a `RecursionError` in the new argv scan) and BUG-263 (a stale docstring) were already filed against it by earlier passes — the note's rule set is otherwise truthful to the probes.
- **`NamingView` is a clean seam.**
  `_walk_path` takes "what the data names at each node" as a `Callable`; argv supplies `_ParseCtx.naming` (own data, root `--json`, then below), the environment supplies `layered_naming` (its own pre-computed namings, then the config level).
  Dependency inversion done right: the walk knows nothing about layers or channels.
- **The adapters' problem is correctly diagnosed and correctly solved in shape.**
  A framework splits argv by the arity registration gives each flag *before* confarg's merge runs, so registration must read the very sources the merge reads — hence `populate_*`/`make_parser` taking the one option set (`**opts: Unpack[MergeOptions]`), `below_argv` reading the layers, `Registration` recording what was read, `reconcile` refusing a differing option, and `_collect_loop_typed_specs` running vanilla's own loop over argv with an `observe` callback.
  The API change is source-compatible (the old keywords `cli_prefix`, `union_tag`, `config_flag`, `argv` are all `MergeOptions` members), and the examples show the intended new spelling with a two-line diff each.
- **BUG-114's fix is minimal and correct**: one `Group` per name per `load_flags_into_app` call, which is exactly what cyclopts requires and no more.

## Broken invariants and defects

### 1. A naming-typed run loses to the static shape of the same flag — filed as BUG-272

The adapter invariant this revision states ("the framework accepts every flag `from_*` will later consume", `build_dynamic_flags`' docstring) breaks where a node's naming types a *statically registered* flag wider than the declared fold:

- a subclass widens a field's annotation (`x: int` → `x: list[int]`); a file names the subclass; argv spells `--db.x 1 2`;
- static registration built `--db.x` with the fold's shape (one token), `_collect_loop_typed_specs` builds a second, wider `FlagSpec` of the same name (`nargs="*"`, since its guard only skips a name whose widest naming type *equals* the declared one);
- every loader's first-wins skip drops the wider spec (static loaded first), so the framework binds one token: argparse refuses `2` ("unrecognized arguments"), click refuses ("Got unexpected extra argument (2)") — while `merge()` accepts `{'db': {'class': …, 'x': [1, 2]}}`;
- and `bound_runs(static + dynamic, cli_prefix)` reads the *built* spec lists, not what the loaders kept, so the stray check now believes the framework bound a run it never bound.

Verified both halves: the spec lists carry `('db.x', None)` and `('db.x', '*')`, and `runs` contains `db.x` though argparse never loaded the `*` spec.
Before the revision, vanilla typed the flag by the base's annotation too and refused the run, so both sides agreed — a parity regression, filed as BUG-272 with the reproduction.

### 2. `_env_spelling` walks its prefix twice, once with the naming and once without

The function computes member names from `_field_types(target, prefix, union_tag, named=named)` — the naming-aware walk — and then, one branch down, computes `reached = _field_types(target, prefix, union_tag)`, with `named` dropped, to feed `named_member_names`.
The two calls in three lines answer the same question ("what does the walk reach at this prefix") differently: the second can reach types of variants a naming narrows away, so a segment can match the spelling of a member no branch of the resolved walk holds.
The outcome is only a more permissive spelling match (the path resolution behind it is naming-aware and refuses), so the user sees an unknown-field refusal where a "no such member" one would be sharper; but the inconsistency is real, and the second call cannot be intentional — with `named` passed, both walks agree and the union of names is the same, because `named_member_names` adds the named class's members itself.
Fix direction: pass `named=named` to the second call, and reuse the first call's branches instead of walking twice.

### 3. Two `_UNREADABLE` tuples for one event

`_naming._UNREADABLE` is `(Exception,)`; `_typed_merge._UNREADABLE` is `(ConfargError, ImportError, ValueError, TypeError, NameError, AttributeError, KeyError)`.
The same event — a class a path names cannot be imported or inspected — is swallowed with two different nets by the two modules that share the naming decision.
The broad one is deliberate ("what importing a class… may raise at parse; the key is then untyped"), but it also swallows any exception a user module's top level raises for a *genuine bug* and silently degrades the walk to untyped keys — the parse-time counterpart of what BUG-269 just made construction refuse politely.
`import_tagged_classes` narrows the same risk with `contextlib.suppress(Exception)` around the import alone; `_naming` catches `Exception` around signature reads too.
Align the two tuples (or let `_naming` import `_typed_merge`'s), keeping `(Exception,)` only where an arbitrary module top level actually runs.

### 4. `below_argv` and `_collect_loop_typed_specs` disagree about silence

`below_argv` suppresses *every* warning (`warnings.simplefilter("ignore")`) while it loads the lower layers for registration; `_collect_loop_typed_specs` suppresses only `ConfargWarning` (`simplefilter("ignore", ConfargWarning)`), a revision-later refinement the other site did not get.
A `UserWarning` a config file's loader or a target import raises is eaten at registration and shown once at the merge — the "warns of nothing, which the merge warns of" contract — but the blanket filter also eats unrelated warnings raised between the two steps.
Narrow `below_argv` to `ConfargWarning` for symmetry with its sibling.

## Uncovered corner cases

- **`_argv_named_nodes` never looks inside JSON lists.**
  `nested()` recurses dict values only, so a `{…}` naming that arrives as a list element (`--f '[{"bind": "pkg.fn"}]'`) names nothing lexically; `_env_namings` has the same shape.
  Both channels agree (the naming view stays empty, keys stay untyped), but neither the scan nor the doc says so — one line in the design note would make the boundary intentional rather than accidental.
  *(inferred from the code; not probed)*
- **A `call:` whose target names a class can leak its fields into env spellings.**
  `named_member_names` has no `_is_typed_call` branch: below a `call:` node whose target is a struct-shaped class with `__call__`, it lists that class's *fields* as member spellings, where `named_child` answers only `call`/`args`.
  A variable spelled like such a field resolves its spelling and then fails path resolution — refused, but by a message that names a field the spelling matched.
  *(inferred from the code; not probed)*
- **The scan marks every node argv writes a value at.**
  `_argv_named_nodes` adds the path of *every* flag with a bare value to `argv_named`, not only where the node takes the callable shorthand; a lower layer's naming at such a node types nothing argv writes below it.
  Documented ("lexical, so it may name more nodes than construction reads as named; such a node's keys are only left untyped"), and my probes could not make it bite — the conservative direction — but the gap between "names" (opener, tag, shorthand, delete) and "marks" (everything with a value) deserves a sentence in the docstring it has not got.
- **A delete does not cut the lower layers' naming, on either channel.**
  The design note counts "a whole-field delete" among what argv names (so `--db-` blocks a file's naming at `db`), and `_env_namings` skips delete variables — yet the probed behavior is that both channels still type keys written *after* the delete below the deleted node by the lower layer's class (`--db- --db.x.0 5` and its env twin both give `{'db': {'x': {'0': 5}}}`, identically).
  Consistent across channels, and construction judges the result — but the "cuts the layers below off" phrasing covers the *data*, not the *naming*, and no test pins this corner.
- **One command, one registration.**
  `cli._clicklike._context.registration` returns the first option that carries a `Registration`; a command populated twice (two targets) has two, and the merge of either target may read the other's.
  The same first-found scan already served `registered_prefix`, so the pattern is pre-existing — but `reconcile`'s refusal makes a wrong match louder than a wrong prefix ever was.
  Not probed.
- **`os.environ` is read twice, by design.**
  Registration reads it (recorded as `None`, "read again at the merge"), the merge re-reads it; a variable set in between types the merge's walk by what the framework did not see.
  The design note rejects a snapshot for exactly this reason — recorded here because nothing tests the two-reads-see-different-things case.

## Missed mutualization and simplification

- **`_config_pairs_in` generalizes `_collect_config_file_pairs` and leaves it standing.**
  The new function is the old one plus prefix handling, built off the same message builders; cyclopts' pre-parse refusal (`_context.py`) still runs its own copy.
  One scan, one message set: the old one could delegate (strip the prefix, call the new one), the way `_check_mount_subpath`'s docstring already promises ("both vanilla's scan and the adapters' re-scan read it from here").
- **The adapter path reads every file twice and parses the environment twice.**
  `below_argv` (registration) and `_lower_layers` (merge) each load `files=`, `env_config`, the `CONFIG__*` mounts and argv's `--config` files; `_env_namings` resolves every variable with the progressive view and the main loop resolves them all again with the full one (necessary — the views differ — but the second pass could reuse what the first resolved where they agree).
  The design note rejects a snapshot of the *environment* (a variable set after the parser is built must be read); the config *files* have no such liveness argument, and a `Registration` that carried its loaded config level would halve the I/O.
- **argv is scanned five times on the adapter path** — `_config_pairs_in` at registration and again at the merge, `_argv_named_nodes`, the patch scan, and the loop-typed `_parse_cli` run (which is itself a sixth consumer, the full parse).
  Each scan is cheap and single-purpose; the count is worth knowing before a sixth is added.
- **`named_member_names` re-implements `named_child`'s decision structure** (tag → class, object opener → class, computation openers → none) by hand.
  The docstring says "the listing view of `named_child`", but nothing mechanical keeps the two together: a new branch in `named_child` (FEAT-13's bound generics, say) must be mirrored by hand or the environment's spellings silently stop knowing about it.
  At minimum, a comment cross-referencing each branch to its `named_child` counterpart would make the mirroring auditable.
- **The two token-count families are stated three times**: `_binds_a_run` (over types), `bound_runs` (over spec attributes) and `_arity_rank` (ints).
  `_binds_a_run`'s docstring asserts the three cannot disagree (via `_shaped`), and BUG-272 is what happens when one of the three is read off the wrong list — a fourth statement of the same taxonomy ("multi-token", "fixed-arity", "one token") as a shared helper would leave nowhere to disagree.
- **`Registration.sources`'s `env=None` convention and `reconcile`'s `unread` set re-encode the defaults of `env_prefix`/`env_config`**, which `_resolve_options` owns; a future option that changes what "read nothing" means must update `reconcile` too.
  The current encoding is correct — probed by reading only — but it is a second place that knows the first place's business.
- Micro: `dict(namespace)` in `_arguments_class` (`namespace` is a dict built one line above); `opener_keys(union_tag)` rebuilds its frozenset per call; `_same`'s `dict(given_env) == dict(recorded_env)` copies two mappings `==` already compares; `_argv_named_nodes`'s `host_parsed` parameter is taken only to be `del`-ed (the docstring already says the host's flags name nothing).

## Unwanted or unforeseen side effects

- **`merge_*` / `from_*` now refuse options registration read differently.**
  Deliberate, documented, and correct for a library that has not shipped ("the framework split the command line by the sources registration read") — but it is a behavior change in an area apps hit at startup: an app that passed, say, a corrected `env=` to the merge to make up for a populate-time mistake now gets a `ConfargError`, and the message (good as it is) is the only documentation of the rule on the API surface.
- **Registration does most of the merge's work.**
  `populate_*` loads every file, parses the environment, and runs a full `_parse_cli` over argv — on every populate call, best-effort and silent (`below_argv`'s `except Exception`, `_collect_loop_typed_specs`'s `suppress(Exception)`).
  A config file that fails to load at registration defers its error to the merge with no symptom in between; that is the documented contract, but the cost is paid even when `argv=[]` registers only the static flags.
- **The argparse Namespace carries a second dunder key** (`__confarg_registration__`), on every parse, so user code spreading `**vars(ns)` sees it; `merge_namespace` filters it, exactly as it filters the prefix key — same treatment, same visibility, worth knowing.
- **The loop-typed family observes only the value-flag branch of vanilla's loop.**
  `observe` sits after the delete, append and force-cast branches return, so those families stay registered by the older argv-scanned paths (append and delete unconditionally when spelled, casts when the fold or the patch scan can type them — probed: index, delete, append and cast spellings below a named node all register when argv spells them).
  The seam works today because the other families' registration does not need the naming; it is worth a comment at `observe` saying so, or the next family that *does* (BUG-272's widening, for one) will be patched by moving the callback rather than by adding one.

## Custom logic that could lean on the standard library

- `_arguments_class` building a throwaway dataclass through `dataclasses.make_dataclass`, with `functools.lru_cache` keyed on `(path, obj)` so a re-bound path gets a fresh class — the right stdlib answer to "a mapping typed by a signature", and the cache key's `del obj` trick is honest about what it is for.
- `_env_namings`/`_ParseCtx.naming` use `contextlib.suppress` and small closures where a visitor class would be heavier — appropriately proportioned.
- `Named` as an `enum.Enum` sharing a return channel with types works and reads well; callers check `isinstance(answer, Named)` before using `answer` as a type.
  Nothing in the stdlib models a sealed union better; the alternative (separate `named_child`/`named_child_refusal` functions) would trade one channel for two call sites at every consumer.
- `json.loads` in `_argv_named_nodes` where `decode_json` is the one decoder of a JSON value — already BUG-262, with the fix direction stated there.

## SOLID and design patterns

- **Single source of truth / open-closed**: the revision's core is exactly this — the naming rule lives in `_naming`, and new *channels* (a new front-end, a new layer) plug in as `NamingView`s without touching `_walk_path`; new *naming sources* (a new opener, a new tag kind) open `named_child` in one place and both the walk and the merge follow.
  The five-sided rewrite of BUG-28/69/84/86/214's tests to the parse's side is the OCP dividend: one rule, every channel agrees, by construction.
- **Chain of responsibility**: `_ParseCtx.naming` (own data → root `--json` → argv_named gate → below) and `layered_naming` (own namings → below) are two clean chains over one contract; the argv-named gate in the middle is the revision's subtlest rule ("a key the node names nowhere is typed by the nearest lower layer; one it names only after stays untyped") and it is *in* the chain rather than scattered over the loop.
- **Observer**: `observe` gives registration a read-only tap into vanilla's loop — the right pattern for "registration must learn what the loop consumes".
  Its placement (value flags only, see above) is the one structural criticism; an observer of the whole loop would have made BUG-272's family visible as a missing spec.
- **Value object + reconciliation**: `Registration` (frozen dataclass, recorded where the merge can find it) and `reconcile` (reuse what is not given, refuse what differs) mirror the existing `resolve_prefix` pattern precisely — consistency with the neighbor is itself a design decision, and a good one.
- **SRP pressure**: `_walk_path` (now `noqa: C901`, five interacting dimensions: `str_subtree`, `in_spec`, `naming`, `variant`, `below_spec`) and `_parse_cli`'s loop (long since `noqa`-ed, and now with `observe` and `ctx.naming` threaded through) both crossed a complexity bar in this revision.
  The noqa comments say why ("read inline"), and splitting either would hurt — but the *next* addition to the walk's step should come as a `_Step` value object (what the segment names here, what it opens, what it refuses) rather than a sixth flag, or the walk will spend its reviewers.

## Suggested follow-ups

1. Fix BUG-272: widen the *loaded* shape of a flag the naming types wider than the fold, and make `bound_runs` read what the loaders kept.
2. Pass `named=` to `_env_spelling`'s second `_field_types` call, and reuse the first call's branches (one walk, one view).
3. Align the two `_UNREADABLE` tuples, keeping the broad catch only where an arbitrary module top level runs.
4. Narrow `below_argv`'s warning suppression to `ConfargWarning`, matching `_collect_loop_typed_specs`.
5. Have cyclopts' `_collect_config_file_pairs` call `_config_pairs_in`; consider letting `Registration` carry the loaded config level so the merge does not re-read the files.
