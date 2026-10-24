# A computation's arguments nest under args

A `bind:` or `call:` spec holds its target's arguments under `args`, the only other key it takes: `{call: torch.optim.Adam, args: {lr: 0.001}}`, `--opt.call torch.optim.Adam --opt.args.lr 0.001`, `APP_OPT__ARGS__LR=0.001`. A `class:` or `classfn:` spec keeps its fields beside the opener, `{class: pkg.H, x: 1}`, as a tagged struct does. The escaped openers (`_bind`, `_call`, `_class`, `_classfn`) are removed outright: their words are ordinary keys.

Why: a computation's arguments belong to its target, which is not the spec, so any word could be one of them, and sharing a level with the opener made every opener word a collision. The flat grammar paid for that in three places:

- the escaped set of openers, its mode selection shared by every channel (`active_directives`), the hint naming a mixed pair (BUG-25) and the dump's refusal of a keyword no form could hold (BUG-217);
- on the CLI, a sibling of a typed call was indistinguishable from a typo below the field, so it was accepted only where argv itself opened the call (`_typed_call_openings`), and a call opened by the environment, a `files=` file or a `--config.<path>` mount could not be refined from flags;
- a lower layer's keys merged beside a higher layer's `call` read as its arguments, so `p: {a: 5}` under `p: {call: square}` built `square(a=5)` without a word (BUG-190). Nested, they are keys no computation takes, and the call refuses them.

An object, though, is its fields: `{class: Sub, x: 1}` is how a union tag selects a struct on every typed field, and a `class:` spec under a Callable builds exactly the same way. Nesting its fields would make `class:` read one way on a Callable field and another on a struct field. So the kind of opener decides: an object opener reads every other key as a field, a `bind` or `call` word beside it included, and a computation opener takes `args` and nothing else. `class` can name no Python parameter, so no constructor argument collides with it.

On the CLI, `args` is a subtree below every field a call can fill (`_parse_cli._opens_spec_subtree`), whatever opened the call, so the opener scan is gone. Leniency stands only where `args` asks for it: `--port.typo 3` stays a parse error, and `--port.args.x 3` with no call anywhere fails in `build()`.

Rejected:

- **Keep every argument beside the opener** (the grammar this replaced, Hydra's `_target_`). Shortest to write, but it needs the escaped set and the opener scan above, and it leaves BUG-190 silent.
- **Nest `class:` fields under `args` too.** One rule for the four openers, but `class:` would then differ between a Callable field and a tagged struct field, the one place it is the same word for the same thing.
- **Reserved dunder openers** (`__call__: pkg.f`, beside the arguments). No argument collides, but reserved keys are file-only ([reserved keys](../config-files/reserved-keys.md#reserved-file-only-keys)), and the environment's `__` separator would spell `APP_N____CALL__`.
- **The target as the key** (`{call: {pkg.f: {a: 1}}}`, serde's externally tagged form). A dotted path is no CLI segment.
- **Accept any key below a field that could hold a call**, as the environment already did, instead of the opener scan. Simplest, but it gave up parse-time typo detection below every typed field on every front-end; `args` keeps it everywhere else.
- **Read the opener from the merged lower layers** to accept `args`. The adapters registered their flags at `populate_*` time, before those layers were known, so vanilla would have accepted flags the frameworks rejected. Registration now reads them, and an opener argv or a lower layer names types the arguments ([a node types its keys by the class it names](a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key)); `args` stays a subtree where none is named.

Precedents: jsonargparse nests a class's arguments under `init_args` beside its `class_path`, and LightningCLI spells them `--model.init_args.lr`; GitHub Actions nests a step's inputs under `with` beside `uses`; serde calls this an adjacently tagged representation, and confarg's own cast pin is one, `{__cast__: int, __value__: "3"}`. Hydra keeps `_target_` and its arguments in one mapping, and reserves `_args_`, `_partial_` and the other underscored words that would collide.

Cost: one more level in every computation's spelling, in files, flags and variables. A struct with a member named `args` keeps it, so a call's arguments on such a field can be written in a file but not spelled on the CLI, where the member wins. A constructor parameter named `classfn` is reachable only under the `args` of a `call` or `bind` of its class, since two object openers are refused.
