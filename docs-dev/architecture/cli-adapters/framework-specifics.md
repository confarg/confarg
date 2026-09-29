# Framework specifics

- **argparse**: value-less flags become `store_true` (argparse forbids `nargs=0` on store);
  argument groups from `FlagSpec.group`; `make_parser` defaults `allow_abbrev=False` so
  adding a field later cannot silently change what an abbreviated flag means.
- **click**: options cannot take `nargs=-1`, so `"*"` maps to `multiple=True` — hence the
  repeated-flag list syntax; no argument groups; `_ConfargOption` allows dotted names; the
  command callback is wrapped to strip confarg parameters from its kwargs.
- **typer**: everything click's entry says, since the option class is a fork of click's —
  `multiple=True` for `"*"`, no argument groups, dotted names via the shared mixin. What
  differs: `autocompletion` rather than the deprecated `shell_complete`, and
  `populate_command` takes the command `typer.main.get_command(app)` returns, not the
  `typer.Typer` app ([the clicklike seam](clicklike-seam.md#the-clicklike-seam)).
- **cyclopts**: flags become a synthetic default function whose `inspect.Signature` holds one
  keyword-only parameter per flag; `_pyname` maps dotted names to unique identifiers and a
  name map restores them; metadata is kept in module-level `_app_meta` keyed by `id(app)`
  (App is unhashable) and holding a reference to the app so the id cannot be reused after GC;
  `negative=()` suppresses `--no-*`/`--empty-*`; there is no metavar, so the type name is
  prefixed to the help text. Cyclopts accepts both list syntaxes.
