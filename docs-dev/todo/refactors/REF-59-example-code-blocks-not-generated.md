# REF-59 — Twenty code blocks under `examples/` are still hand-copied

**Where:** `examples/11_include/README.md`, `examples/18_callables/README.md`,
`examples/1_three_input_sources/README.md`, `examples/19_bindings/README.md`,
`examples/20_factories/README.md`, `examples/22_variable_scopes/README.md`,
`examples/23_local_variables/README.md`, `examples/4_leaf_types/README.md`,
`examples/6_unions/README.md`, `examples/9_child_configurations/README.md` ·
**Filed:** 2026-09-25
**Effort:** M · **Risk:** low · **Impact:** none

The `markdown-code-snippet` hook now generates 36 yaml and 36 python blocks under `examples/`
from the files they quote, so those cannot drift. Thirteen python blocks and seven yaml blocks
could not be annotated and remain hand-copied, which is how
`pair_of_ints.yaml`, `PostgreSQLConfig.port` and `SQLiteConfigChild`'s decorator came to
disagree with the code in the first place. Each needs a different fix, not one sweep:

- **No source exists.** `11_include` shows an app-level `Config` with a `db: DBBaseConfig`
  field, and a `User`/`Config(users=...)` pair for the CSV section; no script under
  `examples/11_include/` defines either. `9_child_configurations` shows an `APIConfig`-less
  `Config`-shaped block with no counterpart. Either ship the script the prose implies, or
  accept these as prose.
- **The tool cannot address it.** `type Config = A | B` appears in `6_unions` and
  `9_child_configurations`; `_extract/_python.py` handles `ClassDef`, `FunctionDef`,
  `AnnAssign` and `Assign` but not `ast.TypeAlias`, so `#Config` fails on a `type` statement.
  A one-node addition upstream would annotate two more blocks.
- **Deliberately partial.** `20_factories` elides a body with `...`; `4_leaf_types` stitches a
  top-level `serialize_int` to a `register_leaf_type` call that lives inside `main()`; five
  blocks are single expressions quoted from the middle of a function
  (`18_callables`, `1_three_input_sources`, `4_leaf_types`, `23_local_variables`). A snippet is
  whole-file or whole-symbol, so these want either a real file to quote or to stay as they are.
- **Invented for teaching.** Three yaml blocks in `19_bindings` use `greet_fn` and
  `greetings.print_greetings` where `config.yaml` has `greetings_fn` and
  `configs.binding.print_greetings`; `22_variable_scopes` and `11_include` each carry one
  yaml block matching nothing on disk. Aligning the prose with the shipped files would make
  four of these annotatable.
- **Generated at run time.** `examples/*/saved_config_*.yaml` is gitignored, so the two blocks
  quoting them in `22_variable_scopes` must stay hand-written: annotating them fails the hook
  on a clean checkout.

The 90_integration blocks are a separate defect, filed as BUG-46.
