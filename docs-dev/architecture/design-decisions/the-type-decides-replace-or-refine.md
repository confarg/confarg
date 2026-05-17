# The type decides whether a value replaces or refines

Between two layers, and between two parts of one source, a dict written over what lies below either **replaces** it (a new value: nothing below belongs to it) or **refines** it (a patch, merged key by key).
Which one it is, is the type's to say, not the key's: the merge asks the type at the node, as construction will read the value there.
`_merge.MergeAt` is the question the merge asks at each node, and `_typed_merge.TypedAt` the typed answer; `typedload._construct.reads_as_new_value` is the one predicate that answers it, which the default layer asks too.

| The type at the node | A dict replaces what lies below when it holds |
|---|---|
| a Callable, an `Any` | an opener (`bind`, `class`, `call`, `classfn`) naming a target |
| a struct, a union of several members, a leaf | the union tag, unless a member owns its spelling ([real field wins](../cli-parsing/casts-and-reserved-words.md#real-field-wins)) |
| any field that takes a typed call | `call` ([call in a typed field](../callables.md#call-in-a-typed-field)) |
| a union of several members | also an opener its Callable or `Any` member reads, unless a struct member owns the opener's key ([a Callable beside another variant](../callables.md#a-callable-beside-another-variant)) |
| a `dict`, a sequence, a struct owning the key | nothing: the key is data, and the dict refines |

So `labels: {class: confidential}` adds an entry to a `dict[str, str]` a lower file filled, `--job.kind stream` refines a `Job` whose own field is spelled like a custom tag, and `{bind: g}` over `{bind: f, args: {a: 1}}` is `g` alone.
A lower layer's union tag, call or opener is replaced as before ([a class tag replaces](class-tag-replaces.md), [a call replaces what lies below](a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)), and the rule is the same at every depth, the root included, a list element reached by an index patch, an include and the keys beside it, and the root `json` fold.

Three refinements of the rule:

- **An opener naming no target refines.**
  `{call: {k: 3}}` or `{bind: {x: 5}}`, a dict holding no opener of its own under the opener (`--n.call.k 3`, `--fn.bind.x 5`), refines the nested target spec below rather than replacing the whole spec: it names nothing new.
  So does a delete of the opener.
  Under the key-alone rule, `--n.call.k 3` over a file's `{call: {classfn: C.m, k: 1}, args: {k: 2}}` left `{call: {k: 3}}`, a spec with no opener.
- **A shorthand below opens.**
  A bare string a Callable reads as `{bind: <string>}` (`_parse_cli._takes_callable_shorthand`, which decides it within a source too) is opened into that form under a higher dict that refines it, so `fn: pkg.shout` in a file and `--fn.args.punct !` build `partial(shout, punct="!")`, as the two flags do in one argv ([whole value then subkey](whole-value-then-subkey.md)).
  An expression is opened the same way, since `{bind: X}` with no argument is `X` whatever `X` resolves to.
  A bare string on an `Any` is text, so a dict replaces it.
- **The data names a class the type does not.**
  Below a node whose class only the data names, a subclass by its tag, the class of a `class:` spec, the owner of a `classfn:` or the target of a `bind:` or `call:` under `args`, the merge imports it to type the node's members, as the default layer does for a tag.
  Where it cannot type a node at all (a key the type does not declare, a name that does not import, a parameter with no annotation, a merge given no target), it falls back to the shape rule: the union tag and `call` replace, every other key refines.

**Within one source, a restated opener or tag starts the node afresh too.**
The CLI and the environment write a source key by key, so a second opener or tag at a node that already names its target arrives as one more key: `--fn.bind pkg.f --fn.args.a 1 --fn.bind pkg.g`, a `{…}` value then `--fn.bind`, `--task.class A --task.extra 1 --task.class B`.
Before it is stored, `_parse_cli._restart_restated_node` empties the node, asking the same predicate through the same typed reading, so the source means what two layers holding the two spellings mean (BUG-238); the CLI loop forgets the tokens a multi-token flag accumulated below it too, or `--task.class A --task.tags a b --task.class B --task.tags c` built `B(tags=['a', 'b', 'c'])`.
The first opener restates nothing, so a key written before it stays, in any order (`--task.retries 1 --task.class Sub`).
Nor does an object opener written beside a computation word, which it reads as a field as one dict holding both would: the environment has no argv order, and `APP_FN__BIND__BIND` sorts before `APP_FN__BIND__CLASS`.
Any opener restates, not only the same one: `--fn.call f --fn.bind g` is `g`, as `{bind: g}` over `{call: f}` is across layers; two openers in one spec are still refused by construction when one write holds both (`--fn '{"call": …, "bind": …}'`).
The alternative weighed was to restate only the same key and leave a different opener a conflict for construction to refuse, which keeps an argv's two openers loud but gives one pair two meanings, depending on whether it spans two layers or one.
Precedent: argparse's last-wins for a repeated option.

Why: the merge decided by the key alone, and construction by the type, so the same input meant one thing within a source and another across layers.
A key the type holds as data silently erased what lower layers gave the node: a struct field fell back to its default, a dict lost its entries (BUG-232).
And the openers a Callable reads, other than `call`, merged with the spec below them, so the old target's arguments reached the new one, as a partial nobody wrote or as an unknown parameter (BUG-231).
Each was a bug fix moving one half of a shared decision: BUG-102 let a real field win the tag's spelling in construction, BUG-23 opened the shorthand within one source, BUG-190 made `call` replace by key; the merge kept the other half.

Rejected:

- **Widen the key-alone rule to every opener**, the one-line change to the former `_merge._is_call_dict`.
  It fixes BUG-231 and widens BUG-232: each word added drops lower layers' keys wherever the type holds it as data, and it does nothing for the shorthand.
- **Mark each source by type**, a type-guided walk rewriting each opener the type reads as a whole-field delete followed by the spec before its layer merges, so the merge stays shape-only.
  It cannot open the shorthand, which may only open when a higher layer refines it, so a second mechanism would be needed anyway; and the type has to reach file loading, includes and mounts all the same, which is the cost that rejected it for `call` alone.
- **Defer to `build()`**, the merge carrying both values under a marker for construction to choose.
  It needs a marker in what `merge()` returns, a reserved file key for `dump_file(merge())` to read back, and every `${...}` reading through the marker, the cost BUG-220 shows for deferred list patches.
- **Keep the arguments the new target accepts** when an opener replaces another.
  That is BUG-231's first case exactly: an argument written for the old target, carried into the new one because a name matched.
- **Replace only when the target changes.**
  Restating the target (`{bind: f}` over `{bind: f, args: {a: 1}}`) would keep the arguments; it diverges from the union tag, which drops the fields when the same class is named again, and "the same target" is fuzzy between a path and a spec that names the same callable.

Precedents: Kubernetes' strategic merge patch reads its merge strategy off the Go types (`patchStrategy`, `patchMergeKey`), where JSON Merge Patch merges by shape alone; OmegaConf merges a structured config by its schema, so a `Dict[str, Any]` node and a dataclass node merge differently.
Hydra merges a node holding `_target_` key by key, so a later config switching the target keeps the old one's arguments, the pitfall this rule removes.

Cost: the merge imports what the data names below a node, a tag's class, a spec's class or target, as the default layer already does; a name that does not import leaves the node to the shape rule, and construction reports it.
The merge stays unvalidated ([merge/build contract](../pipeline/merge-build-contract.md#merge-build-contract)): it reads the type only to tell a value from a patch and to open a shorthand, and still defers what a list patch means to `build()`.
