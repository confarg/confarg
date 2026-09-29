# The clicklike seam

Typer was once a layer over click, which is why the typer examples were written against
`confarg.cli.click` and why no typer adapter existed. It now **vendors click**
(`typer/_click/__init__.py`: *"Code taken and adapted from Click 8.3.1"*; verified against
typer 0.27.2, which is the floor — the release that introduced the fork was not checked), so
`typer._click.Context`, `.Parameter` and `.Command`, `typer.core.TyperOption` and
`typer._types.TyperChoice` are now unrelated to the real click classes of the same shape.
Registering a real `click.Option` on a typer command therefore fails inside click's own
`Parameter.handle_parse_result`, which reaches for a `Context` slot typer's fork does not have
(BUG-7); and `Context.get_parameter_source` returns a member of *typer's* `ParameterSource`,
which is never equal to a member of click's. Neither break is in the merge path.

Typer is consequently a front-end in its own right, not a click spelling — but the two
frameworks' APIs still match almost everywhere, so `cli/_clicklike/` holds every part that
does not name a framework class and each adapter supplies only what its framework spells
differently:

| Shared in `_clicklike` | Supplied by the adapter |
|---|---|
| `option_kwargs` — the whole `FlagSpec` → option-keyword mapping | the choice class, the completion keyword |
| `DottedNameMixin` — `--db.host` is not an identifier | the option base class |
| `ExpressionTolerantChoiceMixin` — the `${...}` bypass | the choice base class |
| `StandsBareMixin` — a flag that may carry no value ([a flag that stands bare](a-flag-that-stands-bare.md#a-flag-that-stands-bare)) | the option base class |
| `load_flags_into_command`, `populate_command` | the option factory and class |
| `flat_from_ctx`, `registered_prefix`, `merge_from_ctx`, `construct_from_ctx` | nothing — the Context is duck-typed |
| `setup_completion`, `partial_argv_from_env` | the option factory |

These are supplied as **mixins placed ahead of the framework's own class**, not as a wrapper
around it: each framework must keep its real base (typer inspects `TyperOption` to render help
and to wire completion), so what is shared is the behavior, not the hierarchy.

`flat_from_ctx` compares the parameter source **by member name** (`"COMMANDLINE"`) rather than
by identity. That is the one place the fork is visible in shared code, and the alternative —
passing each framework's enum in — buys nothing: the question "did the user type this?" has one
answer, and the name is what both forks agree on.

`_clicklike` imports neither click nor typer, so `import confarg.cli.typer` leaves click out of
`sys.modules` and vice versa — the same property REF-1 bought for `cli/_build.py` against
argparse ([framework-neutral flag model](flag-model.md#framework-neutral-flag-model)).

Where the frameworks genuinely disagree, the seam widens rather than the shared code branching.
Completion is the only such case so far: click takes a `shell_complete` callback returning its
own `CompletionItem`s, while typer deprecates that in favour of an `autocompletion` callback
returning bare strings which typer wraps itself. So `option_kwargs` takes a
`completer_kwargs` builder instead of a completion-item class. Typer additionally filters the
result by `startswith(incomplete)`, which changes nothing: a confarg completer
(`_build._make_path_completer`) already prefix-filters.

The adapter reaches into two private typer modules (`typer._types`, `typer._click`), because
`TyperChoice` and the fork's `Context`/`Command` types have no public spelling. The exposure is
confined to `cli/typer/_register.py`'s imports, and `cli/typer/__init__.py` probes those names
in its availability guard so a typer too old to vendor click reports confarg's own message
rather than an ImportError on a private module. `typer>=0.27` is therefore the floor.
