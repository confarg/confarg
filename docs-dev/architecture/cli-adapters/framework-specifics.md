# Framework specifics

- **argparse**: value-less flags become `store_true` (argparse forbids `nargs=0` on store); argument groups from `FlagSpec.group`; `make_parser` defaults `allow_abbrev=False` so adding a field later cannot silently change what an abbreviated flag means.
- **click**: options cannot take `nargs=-1`, so `"*"` maps to `multiple=True` — hence the repeated-flag list syntax; no argument groups; `_ConfargOption` allows dotted names; the command callback is wrapped to strip confarg parameters from its kwargs.
- **typer**: everything click's entry says, since the option class is a fork of click's — `multiple=True` for `"*"`, no argument groups, dotted names via the shared mixin.
  What differs: `autocompletion` rather than the deprecated `shell_complete`, and `populate_command` takes the command `typer.main.get_command(app)` returns, not the `typer.Typer` app ([the clicklike seam](clicklike-seam.md#the-clicklike-seam)).
- **cyclopts**: flags become a synthetic default function whose `inspect.Signature` holds one keyword-only parameter per flag; `_pyname` maps flag names to distinct identifiers and a name map restores them ([below](#cyclopts-parameter-names)); metadata is kept in module-level `_app_meta` keyed by `id(app)` (App is unhashable) and holding a reference to the app so the id cannot be reused after GC; `negative=()` suppresses `--no-*`/`--empty-*`; there is no metavar, so the type name is prefixed to the help text.
  Cyclopts accepts both list syntaxes.

## Cyclopts parameter names

A flag name is a path, and a path segment below a dict is any key the user types: `--d.x[0].k`, `--d.a/b.k`, `--d.a b.k`.
`inspect.Parameter` accepts only an identifier, so `_pyname` escapes every character outside ASCII letters and digits, and, since the name map is a dict keyed by the identifier, it must also keep distinct flags distinct: two flags given one name register as one parameter, and cyclopts refuses the second as an unknown option.
It does both the way JNI's native-method mangling and GHC's Z-encoding turn arbitrary names into C symbols, by escaping the escape character itself: `_` doubles to `__`, and any other character spells its code point `_<hex>_`, so `--db.host` is `db_2e_host` and `--db_host` is `db__host`.
Read left to right, each `_` opens either a doubled `_` or a hexadecimal escape closed by the next `_`, so an identifier decodes to one name only.
A leading digit and the first letter of a keyword are escaped the same way (`1x` is `_31_x`, `class` is `_63_lass`), which keeps the mapping a pure function of the name (BUG-173).

Rejected: **a reserved token per non-identifier character** — `.` as `__`, `+` as `__append_`, `-` as `__delete_`, every other character left as it was.
A key holding any other character left the name invalid, and with `_` unescaped a key could spell a separator's token: `--d.a__b.c` and `--d.a.b__c` were both `d__a__b__c`.

Rejected: **a positional name** (`p0`, `p1`, …), unique by construction.
It would work as well, the name never reaching the user, but it ties a parameter's name to registration order, so a debugger or a traceback shows `p17` where the escape still reads as the flag.

The `name` cyclopts registers is the flag itself, and one character of it is cyclopts' own syntax: a trailing `*` flattens a parameter's members into its parent (`Parameter(name="*")`, `"foo.*"`), so `resolve_parameter_name_helper` strips one, with the dots before it.
`--d.a*` registered as `--d.a`, `--d.*` as `--d`, and cyclopts refused the flag the user typed, whatever it addressed: a dict key, a `--config` mount at one, a `cli_prefix` ending in `*` (BUG-180).
`_register._option_name` escapes it the way the identifier escape doubles `_`, and printf's `%%`, Make's `$$` and `str.format`'s `{{` double their own escape: a name ending in `*` gets one more, which cyclopts strips again, so `--d.a**` registers `--d.a*` and help prints the flag as typed.
The strip is single-pass on every cyclopts the project allows (checked on 4.11.2 and 4.24.0), which cyclopts does not document; the contract suite's star-ending flags are what would turn red if it changed.

Rejected: **a sentinel name and an argv rewrite**, the way `merge_app` drops bare occurrences.
It needs no cyclopts behaviour beyond the parse, but it rewrites both spellings (`--d.a* 1`, `--d.a*=1`) and prints the sentinel in help unless it is translated back.
Rejected: **refusing such a flag** with confarg's own error, which keeps a parity gap the escape closes.

## Cyclopts repeated one-token flags

A one-token flag spelled twice is the last occurrence's write on every front-end: `--port 1 --port 2` is `2`, as each later occurrence overwrites what an earlier one wrote at its path ([argv is the only writer](model.md#argv-is-the-only-writer)). argparse, click and typer keep the last occurrence on their own; a cyclopts parameter that consumes one token refuses the second with `Parameter --port specified multiple times.` unless it is registered `allow_repeating=True`.
Nothing reads the value cyclopts binds, vanilla's loop reading every occurrence off argv, so the registration allows the repeat, as it does for a value-less delete ([collection patch parity](collection-patch-parity.md#collection-patch-parity)).
A flag that consumes many tokens (`consume_multiple`) accumulates its repeats already.
The refusal dates from the adapter itself (PR-26) on field flags; it reached the element flags of a one-token type when they stopped registering greedily (BUG-179).

## Help text is format-neutral

The help of a flag reaches a framework that may read it as markup: cyclopts renders parameter help as Markdown unless the application sets another `help_format` (reStructuredText, rich markup, plain text), typer as rich markup or Markdown under its `rich_markup_mode`, and argparse `%`-formats it (`%(default)s`).
The format is the host application's setting, and one application may mix confarg's flags with its own, so confarg overrides none of them.
A help has two authors, and `FlagSpec` keeps them apart:

- `help` is the field's own prose — `FieldMeta.help` or its attribute docstring — and is handed over as written, so Markdown a cyclopts user writes in a docstring renders as it does on the host's own parameters, and an argparse user's `%(default)s` still formats.
- `note` is what confarg writes: a default's repr, a namedtuple's positional order, a class path, a dict key, a placeholder.
  It is data, so each adapter escapes it for the format its framework renders (`FlagSpec.rendered_help`, with the escapers in `cli/_markup.py`): every ASCII punctuation character backslashed for Markdown and reStructuredText, which both read such a backslash as the literal character; rich's own `markup.escape`, plus an empty tag pair after an emoji code's opening colon, which rich replaces otherwise and offers no escape for; `%` doubled for argparse; nothing for click.
  Before, cyclopts by default turned `'*.py|*.pyi*'` into `'.py|.pyi*'` and `__main__.Cat` into a bold `main.Cat`, and a default holding `[/x]` crashed `--help` with a `MarkupError` on cyclopts' rich format and on typer's default rich mode; argparse crashed on a default holding `%d`.

A group's description is the struct's docstring, its author's prose, so it is handed over as written too.
A dataclass that has none gets one from Python, its name and signature (`A(xs: list[int] = <factory>)`): that is data, not prose — rich printed it `A(xs: list = <factory>)`, Markdown would drop `<factory>` — and it restates the flags the group lists, so `_spec._struct_doc` leaves such a group without a description, as cyclopts leaves the dataclass parameters it flattens itself.

The cyclopts adapter (and the typer one) put confarg's text after the metavar, and escape that metavar too. cyclopts and typer render their own `[default: …]` and `[choices: …]` the same way, as a separate rich `Text` that never goes through the markup pass; confarg's note has no such slot, so escaping is how it gets the same treatment.

The fixed wording of a note is markup-free besides: a placeholder is an uppercase word, as argparse and click spell a metavar (`--config.FIELD FILE`, `--FLAG.PARAM`), and a dunder is spelled out (`constructor parameters`, not `__init__ parameters`).
It then reads the same where the format confarg escapes for is not the one rendered ([limitations](../limitations.md#cli-front-ends)), and in any custom adapter that prints `rendered_help()` unescaped.
`TestHelpReadsUnderEveryFormat` renders every note confarg writes through each cyclopts format and asserts it prints as written, and `TestHelpReadsUnderEveryMarkupMode` does the same for typer (BUG-226).

Rejected: **forcing `help_format="plaintext"`** on the parameters confarg registers.
It would keep any string intact, but it overrides a setting that belongs to the application, and it would disable the Markdown the user wrote on purpose in a `FieldMeta.help` or a field docstring.

Rejected: **escaping the whole help**.
It is simpler, the adapter needing no split, but it disables that same Markdown.

Rejected: **handing the default to the framework's own default display** (typer's `show_default=<str>`, cyclopts' `show_default`).
It renders the repr outside the markup pass, but it covers only the default: a class path or a dict key in a note has no such slot.
