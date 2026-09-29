# Testing architecture

## Layout

Tests mirror `src/confarg/` — `tests/cli/` for `src/confarg/cli/`, `tests/typedload/` for
`src/confarg/typedload/`, `tests/dictexpr/` for `src/confarg/dictexpr/`; cross-cutting tests
live directly in `tests/`.

`tests/tooling/` mirrors nothing, because what it covers ships with nobody: the repository's own
scripts, `docs-dev/todo/index.py` first. They sit under `tests/` rather than beside the scripts
so that one suite runs everything and the test files inherit the `tests/**` lint profile. A
script there is imported by path — `docs-dev` is not a legal package name — and has its module
level `TODO` root monkeypatched at a `tmp_path` tree, so a test never touches the real boards.

## Contract suite

Parity is enforced by tests, not by review. `tests/_loaders.py` wraps the five front-ends
behind a `confarg.load()`/`merge()`-compatible interface:

| Loader | Pipeline |
|---|---|
| vanilla | `confarg.load` |
| argparse | `make_parser` → `parse_args` → `from_namespace` |
| click | `populate_command` → `CliRunner.invoke` → `from_context` |
| typer | `populate_command` → `TyperCommand.main` → `from_context` |
| cyclopts | `populate_app` → `from_app` |

typer has no runner that takes a pre-built command — `typer.testing.CliRunner.invoke` calls
`get_command` on the app itself and would discard the populated one — so `TyperLoader` invokes
`command.main` directly under a redirected stdout/stderr. Standalone mode exits on success too,
so an empty result holder is what tells the loader typer rejected argv itself.

`tests/cli/test_backend_contract.py` holds every behavior shared by the front-ends, written
once against the parametrized `loader` fixture. Only framework-specific behavior (help text,
registration idioms, completion) goes in the per-backend directories; what the click and typer
adapters *share* is covered once by the contract suite, so `tests/cli/test_clicklike.py` holds
only the shared helpers neither public surface exposes
([04](04-cli-adapters.md#the-clicklike-seam)). Writing a shared
behavior per backend would let the backends drift.

Fixtures (`tests/conftest.py`): `loader` (all five), `space_sep_loader`, `repeated_loader`,
`populating_loader` (front-ends with a `populate_*` step, exposing `registered_flags()`).

Several contract classes document past divergences, one test each (`TestPipelineParity`,
`TestCollectionPatchContract`, `TestExpressionOverCliContract`,
`TestExpressionIntoRestrictedFieldContract`). Keep them as regression guards.

`TestBareVarlenFlagContract` is one of them and carries a second job: it is what pins
`FlagSpec.stands_bare` to the flags the merge step knows how to read a dropped token back for
([04](04-cli-adapters.md#a-flag-that-stands-bare)). A case per multi-token type, plus the union
that has no empty value to store and must still be refused; the dict-subkey and element spellings
of the same rule sit with the rest of their family in `TestCollectionPatchContract`.

## List syntax split

List syntax differs by framework ([04](04-cli-adapters.md#list-syntax-divergence)). The
difference must stay **visible**: write separate tests per convention (`space_sep_loader`
for vanilla/argparse/cyclopts, `repeated_loader` for click/typer/cyclopts) instead of hiding it
behind a helper.

Only the *spelling* is split that way. What repeating a multi-token flag **means** is shared, so it
is a `loader` contract (`TestRepeatedFlagAccumulationContract`), written in the repeated form every
front-end accepts — and a case only the space-separated form can express keeps `space_sep_loader`.
Reaching for `repeated_loader` for anything but a spelling is the mistake that let the two answers
drift apart in the first place (BUG-37).

## Examples and documentation

`examples/*/README.md` console blocks are executed as subprocess tests by the
`pytest-markdown-console` plugin during a full `uv run pytest`; a Markdown file opts out with
`<!-- pytest-markdown-console-file: notest -->` (the root README does, since it illustrates a
fictitious app).

That verbatim subprocess replay is the only mechanism covering the example commands. An
in-process variant was started once — `tests/examples/_registry.py` curated, per script, the
`confarg.load` arguments and output rendering needed to replay each README command through every
CLI loader — but its harness never landed, and the registry was deleted rather than the harness
rebuilt (BUG-52). The subprocess replay executes the README command exactly as a reader would, so
there is nothing a curated second copy of it can add, only drift: a script changed without a
matching registry entry failed the suite loudly, which is the failure mode the subprocess replay
cannot have.

`docs-dev/` is excluded from collection instead, via `norecursedirs` in `pyproject.toml`:
internal documentation is never test material, and a board reproduction is meant to be read,
not run — its commands are repository-root-relative, and the block runs from the ticket's own
directory, so a replay can only fail (BUG-55). The first fix was the per-block
`<!-- pytest-markdown-console: notest -->` directive, one decision left to each filer; the
exclusion makes the decision once, at collection time. One caveat: explicitly naming a
`docs-dev` path on the command line still replays it, because pytest's ignore mechanisms do
not apply to arguments passed explicitly — that is the invoker asking for documentation.

Each block runs with the README's own directory as its working directory, so a script that
writes a file writes it there — `21_expressions` and `22_variable_scopes` end their scripts
with `dump_file()` and leave `saved_config_*.yaml` behind on every run. Those artifacts are
`.gitignore`d rather than redirected: writing next to the configuration is what the tutorials
show a reader getting, and parameterizing the path would put test scaffolding into script
source the documentation site renders verbatim. The alternative — copying each example into a
per-block temporary directory with `cwd:${tmpdir}` and a fixture — was rejected as the larger
change: it needs a `conftest.py` inside the published `examples/` tree and a `UV_PROJECT`
injection, because `uv run` outside the project root resolves no project environment.

## Asserting against a front-end's internals

A white-box test on a framework object asserts **what the adapter registered**, never the
framework's normalization of it. `tests/cli/cyclopts/test_cyclopts_integration.py::test_choices`
reads the `Literal` back off cyclopts' `Argument.hint`, and cyclopts 5.0 changed that field from
`converter=resolve` to `converter=partial(resolve, optional=False)`: the registered
`Literal[...] | None` used to arrive as `Literal[...]` and now arrives as
`Optional[Literal[...]]`. The change was not a documented breaking change, because `hint`'s shape
never was documented — 5.0's union rework (members of a union may consume different token counts,
and `"none"` parses to `None`) needs `NoneType` to survive resolution.

So the test normalizes through `_literal_of` instead of matching one version's spelling, and no
`cyclopts` version is named in the assertion. Do not "simplify" the helper away against whichever
version happens to be locked: the dev floor is `cyclopts>=4.11.2` and the test is expected to hold
from there to the latest release.

## Property tests

`tests/test_hypothesis.py` uses Hypothesis. Generated strings escape `${` as `$${` so random
text is not mistaken for an expression.
