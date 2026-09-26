# Plan — A post-resolve transform layer

**Drafted:** 2026-09-27 · **Status:** approved · **Ticket:**
[FEAT-23](../todo/features/FEAT-23-post-resolve-transform-layer.md)

Handling a configuration is two jobs. **Composing** one is well served: `__include__` at any node,
subpath mounting, `locals:`, the expression engine, and the designs in FEAT-19/20/21/22.
**Manipulating** an existing one is not. The whole vocabulary is `+`, `-`, `~`, `*`, index patches
and `DICT_DELETE` — per-channel sigils that grew by accretion, unordered as a set, with no rename at
all ([01](../architecture/01-pipeline-and-contracts.md#deep-merge-semantics)) and no append spelling
in the environment (FEAT-18).

## What bounds the feature

> A mutation is in scope only where an expression at a known path cannot say it.

That test is what keeps this from becoming a second mechanism competing with the expression engine —
the shape [09](../architecture/09-invariants.md#delegate-to-the-canonical-function) forbids, and the
one that sank `link_arguments`' compute function in FEAT-19. Four things pass it:

1. **Read-modify-write of a value.** The motivating case, and unreachable two ways over: a field
   referencing itself is a `CircularReferenceError`, and `_deep_merge` replaces the value an overlay
   expression would have to read, so the prior value is gone before resolution runs.
2. **Addressing many nodes.** An expression names one path, and a list element cannot know its own
   index — deliberately, since not naming its index is the property the node anchor exists to
   provide
   ([07](../architecture/07-expressions.md#a-relative-reference-is-never-serialized-as-an-absolute-path)).
3. **Changing a key** rather than a value.
4. **Conditional absence.** `${None}` yields `None`, not an absent key, and `DICT_DELETE` is a
   merge-layer sentinel no expression can produce.

What fails the test stays with the engine that already answers it. A **single-path value
conditional**: `type: ${"truck" if length > 10 else "car"}` resolves today, lives at the field it
governs, survives `merge()` to `dump_file()` verbatim, and is still overridable by `--type car`. And
**one guard over many sibling fields**, because a local may hold the guard —
`locals: {big: ${length > 10}}` resolves, and `--locals.big false` overrides it from any channel
([08](../architecture/08-locals.md#declare-in-files-modify-anywhere)).

The test governs the design and the documentation; it is **not enforced**. Deciding that an
expression could have said the same thing requires knowing whether a rule's predicate reads its own
target, which is not decidable in general, so the engine does not refuse a single-path `set` — the
how-to steers instead.

## Decisions taken

| Decision | Choice |
|---|---|
| Scope | The admission test above, as guidance rather than enforcement |
| Stage | Post-resolve, in the shared helper behind `build()` and `resolve()` |
| Precedence | Sources merge by precedence, then transforms rewrite the result. No conflict check |
| Semantics | Sequential, RFC 6902: one pass, later rules see earlier effects |
| Ordering | Depth-first walk of the merged document in key order; declaration order within a block |
| Declaration | A reserved dunder key, a rules-only file, or `transforms=` |
| Cascade shape | Flat rules. No grouped match form in v1 |
| Convention | Own surface, borrowing RFC 6902's op vocabulary and ordered-stream semantics |
| Absorbs | FEAT-11. FEAT-4 stays filed |

### Why post-resolve, and what it costs

After `resolve_expressions` nothing expression-shaped survives, so **a `move` cannot dangle a
reference** — which is the whole reason not to run before resolution. A pre-resolve stage would have
to repair every reference a move invalidates, and the hard case is undecidable: to know whether a
node-relative `${..db.host}` pointed *into* the moved subtree, the stage must resolve the anchor,
which depends on the node's position — the very thing the move is changing. `canonicalize_references`
is forbidden from resolving `${.x}` at all
([09](../architecture/09-invariants.md#fragile-couplings)), so the stage would see uninterpreted
dots. Refusing the move whenever a node-relative reference is in reach is the honest fallback, and it
cripples the most-wanted op.

The cost is that the three source dicts are gone by then, so **a rule cannot know whether a value
came from a file or from `--type car`**, and no conflict check is possible. That is not a regrettable
side effect: read-modify-write *is* a rule overwriting a value a source wrote, so a stage that raised
on the conflict would error on every firing of the motivating case. The precedence promise is
restated rather than broken — `files < env < CLI` orders the three **sources**, and a transform is
declared post-processing of the merged result, not a fourth source.

Silent last-word patching is nonetheless the Kustomize behaviour most complained about, so the
contract cannot be a footnote: it leads the how-to, and a per-firing trace ships **with** the feature
rather than waiting for FEAT-8 or FEAT-10, neither of which exists.

### Why sequential, and what it forces

Sequential semantics make the cascade work as written and keep deliberate chaining available. They
also make rule order decide the **result**, not merely the order, so leaving order unspecified across
mount points is not available to a library whose contract suite asserts byte-identical merged dicts.
The order is therefore fixed and asserted: a single depth-first walk of the merged document in key
order, declaration order within one block.

The alternative considered and declined was *snapshot semantics with first-writer-wins* — all
predicates evaluated against the document as it stood on entry, effects applied once. It makes the
cascade correct by construction rather than by each rule happening to overwrite the field it matched
on, and it forecloses rules-triggering-rules entirely. It was declined because it also forecloses
deliberate chaining. Revisit if order dependence proves to bite.

### Rejected alternatives

**On the stage.** *Pre-resolve, in `_merge_sources`*: the only placement where a conflict check is
possible, at the cost above. *Two phases*, structural pre-resolution and value post-resolution: the
only shape where both halves are fully correct, but two rule kinds and two places to look.

**On the precedence conflict.** *Raise*, FEAT-20's assertion shape: incompatible with
read-modify-write, as above. *Source wins*: a rule could then never change anything, which is the
feature. *Per-rule disposition*: covers every case, and makes "what is my configuration" a per-rule
question.

**On the convention.** *JSON Patch (RFC 6902) wholesale*: its op vocabulary and ordered-stream
semantics are exactly right and are borrowed; its JSON Pointer paths are not — `/db/host` in a file
beside `--db.host` on argv is a fresh cross-channel divergence bought for nothing, and `~0`/`~1`
escaping is hostile in YAML. *JSON Merge Patch (RFC 7386)*: this is already confarg's deep merge.
*JSONPath (RFC 9535)*: the right shape for a filtered selector, wrong syntax here — `$.` was already
weighed and rejected for the root anchor in favour of `::`
([10](../architecture/10-design-decisions.md)), and `$` or `@` would be a third sigil family beside
`${}`, `::`, `+` and `-`. *jq*: a complete transformation language and a second evaluation model.
*CUE, Jsonnet, Nix, Dhall*: adopting a language, against a safety model that deliberately stops at a
whitelisted AST; CUE's unification-as-assertion is already cited by FEAT-20. *Kustomize*: the hybrid
architecture — a readable native form plus RFC 6902 where precision is needed — is the model followed
here, but its selectors are Kubernetes-shaped and its `replacements` push form was already rejected
as FEAT-19's `Broadcast`. *Hydra's override grammar*: the closest Python-ecosystem precedent and
CLI-first, but its `+` and `~` collide with confarg's existing readings of the same characters.
*Jinja, Ansible templating, Helm*: arbitrary-expression risk the safety model rules out. *Rego/OPA*:
a dependency and a whole language, in a library with zero runtime dependencies.

Ansible's `when:` and git's `includeIf` are the precedent for conditionality as a configuration
clause, and are followed.

**On the surface.** A *grouped match/case form* reads as the decision table it is and makes
first-match-wins local and obvious, but it is a second construct in the grammar — the half-language
Kustomize is the cautionary tale for. Flat rules first; revisit if the repetition bites. *CLI
spellings for the unconditional ops*: declined. A rule's knobs are locals, which are already
modifiable from every channel with parity, typo detection and type-preserving coercion, so the complex
forms stay file-only without a CLI mutation grammar being invented. A rename could not reach argv
anyway — an unknown flag is an error at parse time, before any config file is read.

## The contract

```yaml
__transforms__:
  - select: .vehicles[*]
    when: .type == "warship" and .length > 120
    set: {type: destroyer}
  - select: .vehicles[*]
    when: .type == "warship" and .length > 60
    set: {type: frigate}
  - select: .vehicles[*]
    when: .type == "warship"
    set: {type: corvette}
  - move: {log_level: logging.level}
```

- **Stage**: merge, then `resolve_expressions`, then transform, then strip, then construct — in one
  internal helper called from `build()` and `resolve()`, so all five front-ends and every public seam
  get it. `from_dict` is unaffected, being documented as taking already-resolved data, which is the
  same boundary `_strip_locals` has.
- **Declaration**, three spellings of one mechanism:
  - `__transforms__` inside the document being transformed. A dunder key, and therefore file-only by
    construction: the default env separator is also `__`
    ([02](../architecture/02-files-and-env.md#reserved-file-only-keys)). Declarable at any node.
  - **A rules-only file layered above the input** — a second config file carrying only
    `__transforms__`, mounted by `--config` or the env config pointer like any other. This is the
    spelling the how-to leads with.
  - `transforms=` on `load()` and `merge()`, root-anchored, applied after file-declared rules, for an
    application shipping policy without requiring a file.
- **Two anchors in one rule**: `select` is relative to the *declaring* node, like `__include__` and
  locals; `when` and `set` value expressions are evaluated with the **match** as anchor, so `.length`
  means the matched node's.
- **Ops**: `set`, `move`, `remove`. A rename is `move` within the same parent — one spelling only,
  which [10](../architecture/10-design-decisions.md) already argues at length for the `+` operator.
  No `test` op; that is `when`.
- **Selector**: `[*]` over one list segment, nesting allowed, no inline predicates. This is the only
  new grammar in the feature.
- **No match** is a silent no-op; `require: true` opts into an error.
- **Rules are consumed by the stage.** `merge()` carries them verbatim, so `dump_file(merge(...))`
  round-trips and reloads identically; `resolve()` applies and strips them, which also makes a second
  `transform()` call a safe no-op.
- **Values are file-native** — no `_StrToken`, so no coercion. `build()` validates a rule's output
  exactly as it validates a file's
  ([09](../architecture/09-invariants.md#merge-stays-unvalidated)).

## Phases

1. **The engine, `src/confarg/dicttransform/`.** A sibling of `dictexpr`: standard library plus
   `confarg.exceptions` only, no knowledge of channels, files or target types, testable standalone.
   Holds the rule model, the `[*]` selector walk, the three ops and the single-pass executor. Reuse
   the dotted-path walk `dictexpr._expressions._get_nested` and `_set_nested_by_path` already carry
   rather than adding a fourth copy (REF-43).
2. **The dictexpr entry point.** Expose an anchored single-expression evaluator over the existing
   `_resolve_single(expr, namespace, node_path)`; the anchor parameter is already there. And **skip
   the reserved key in `_collect_expressions`**, which currently walks every dict and list value and
   so collapses a rule's `when` early and against the root instead of the match. That needs a
   regression test of its own.
3. **Wiring.** A public `transform(data, *, transforms=None)` as the fourth seam, matching
   [01](../architecture/01-pipeline-and-contracts.md#public-api-seams), with a `trace=` list callers
   may pass to collect one record per firing: rule, selector, matched path, before, after. The shared
   helper at the two resolution call sites; strip the key after application; `TRANSFORMS_KEY` into
   `_defaults.py` beside `LOCALS_KEYS` and `ROOT_KEY`, the stated home for reserved names.
   `transforms=` reaches `load()` and `merge()` and therefore the five front-ends, so size it against
   REF-40 before spelling it.
4. **Errors and documentation.** A `TransformError` family on `LocalsError`'s classmethod-factory
   shape, messages built in the factories (REF-51). A how-to and an `examples/` entry whose example
   is one an expression cannot say.

**Deferred**: `split` and `merge` ops; the grouped match form; and the approved divergences —
file-only declaration, and a rename never reaching argv — recorded in
[09](../architecture/09-invariants.md#cross-channel-parity) when the code lands. Plus the migration
half, below.

### Deferred: versioning and migrations, absorbed from FEAT-11

Renaming or moving a field today breaks every configuration file, environment variable and
command-line flag in the wild. The shape: a configuration declares its schema version (a reserved
`version` file key, or an implicit version 1), the program registers migrations, and confarg applies
the chain from the declared version up to the current one before the data reaches `build()`. The ops
worth having declaratively are these ops, which is why the two tickets became one; an escape hatch
taking an arbitrary dict-to-dict function covers the rest.

It is deferred rather than folded into the phases above because **it wants a different stage**. A
migration must run *per source, before the deep merge*, so each file is migrated on its own terms and
an old file and a new one still merge correctly — and so the rewritten document still carries its
`${...}`, which is what a `confarg migrate` subcommand needs to write back. A post-resolve stage can
produce neither. Two axes are still open: whether a single version key can honestly describe a stack
of files of different vintages, and **parity**, the hard part — a renamed field renames its
environment variable and its CLI flag too, so a file-only migration is exactly the silent divergence
[09](../architecture/09-invariants.md#cross-channel-parity) forbids. Tooling: `confarg migrate` wants
the console script FEAT-9 and FEAT-10 also want, so the packaging question is settled once for all
three.

The precedents each picked a different point on the scale. Terraform has `moved` blocks for renamed
resources and a `required_version` constraint; Cargo gates behavior on an `edition` key with
`cargo fix --edition` to migrate; Kubernetes pairs an `apiVersion` field with conversion webhooks
between versions; Hydra's `version_base` gates its own behavior changes but leaves user-config
migration manual; ESLint ships a one-shot codemod rather than a registry; serde and pydantic-settings
stop at field aliases (`#[serde(alias)]`, `AliasChoices`) with no version concept at all. The
declarative-ops-plus-version-chain shape is the Kubernetes/Terraform end; the alias-only shape is the
serde end, and that lighter half is separable — it lives on FEAT-6 as `Annotated` metadata and needs
no version key.

## Verification

1. The suite, pre-commit, then the type checker.
2. **The use case**, end to end: the four-branch cascade over `.vehicles[*]`, including that
   rewriting a discriminant changes which union variant `build()` selects. Asserted through all three
   declaration spellings, with identical results.
3. **Ordering determinism**: rules declared across two mounted files produce one specified result —
   required, because sequential semantics make order decide the outcome.
4. **Cross-channel parity** for all five front-ends, and `merge()` still byte-identical
   ([09](../architecture/09-invariants.md#adapter-output-equals-vanilla-output)).
5. **Fixpoint**: `load(dump_file(merge(X)))` equals `load(X)` for a configuration whose rules have
   fired, and `transform()` applied twice equals once.
6. **Precedence**: `--type car` plus a matching rule yields the rule's value, and the trace names the
   rule that did it.
7. **Regression**: a `when` inside the reserved block is not resolved by the ordinary pass.
8. **No new mechanism for the old ops**: the `+ - * ~ N` sentinel tests unchanged, proving the
   vocabulary was extended rather than duplicated.

## Open

- **Reference repair is moot post-resolve, but `move` still has to decide what happens to a key the
  target type does not have.** `build()` rejecting it is probably right; confirm it reads well.
- **`transforms=` against REF-40.** Whether the parameter earns fourteen more spellings, or whether
  the rules-only file covers the case well enough for v1.
- **`dicttransform` or `dictpatch`** as the package name. The former keeps one vocabulary with
  `__transforms__` and `transform()`; the latter is shorter and matches the borrowed op semantics.
