# Testing architecture

## Layout

Tests mirror `src/confarg/` — `tests/cli/` for `src/confarg/cli/`, `tests/typedload/` for
`src/confarg/typedload/`, `tests/dictexpr/` for `src/confarg/dictexpr/`; cross-cutting tests
live directly in `tests/`.

## Contract suite

Parity is enforced by tests, not by review. `tests/_loaders.py` wraps the four front-ends
behind a `confarg.load()`/`merge()`-compatible interface (minus `cli_prefix`):

| Loader | Pipeline |
|---|---|
| vanilla | `confarg.load` |
| argparse | `make_parser` → `parse_args` → `from_namespace` |
| click | `populate_command` → `CliRunner.invoke` → `from_context` |
| cyclopts | `populate_app` → `from_app` |

`tests/cli/test_backend_contract.py` holds every behavior shared by the front-ends, written
once against the parametrized `loader` fixture. Only framework-specific behavior (help text,
registration idioms, completion) goes in the per-backend directories. Writing a shared
behavior per backend would let the backends drift.

Fixtures (`tests/conftest.py`): `loader` (all four), `space_sep_loader`, `repeated_loader`,
`populating_loader` (front-ends with a `populate_*` step, exposing `registered_flags()`).

Several contract classes document past divergences, one test each (`TestPipelineParity`,
`TestCollectionPatchContract`, `TestExpressionOverCliContract`,
`TestExpressionIntoRestrictedFieldContract`). Keep them as regression guards.

## List syntax split

List syntax differs by framework ([04](04-cli-adapters.md#list-syntax-divergence)). The
difference must stay **visible**: write separate tests per convention (`space_sep_loader`
for vanilla/argparse/cyclopts, `repeated_loader` for click/cyclopts) instead of hiding it
behind a helper.

## Examples and documentation

`examples/*/README.md` console blocks are executed as subprocess tests by the
`pytest-markdown-console` plugin during a full `uv run pytest`; a Markdown file opts out with
`<!-- pytest-markdown-console-file: notest -->` (the root README does, since it illustrates a
fictitious app).

Each block runs with the README's own directory as its working directory, so a script that
writes a file writes it there — `21_expressions` and `22_variable_scopes` end their scripts
with `dump_file()` and leave `saved_config_*.yaml` behind on every run. Those artifacts are
`.gitignore`d rather than redirected: writing next to the configuration is what the tutorials
show a reader getting, and parameterizing the path would put test scaffolding into script
source the documentation site renders verbatim. The alternative — copying each example into a
per-block temporary directory with `cwd:${tmpdir}` and a fixture — was rejected as the larger
change: it needs a `conftest.py` inside the published `examples/` tree and a `UV_PROJECT`
injection, because `uv run` outside the project root resolves no project environment.

## Property tests

`tests/test_hypothesis.py` uses Hypothesis. Generated strings escape `${` as `$${` so random
text is not mistaken for an expression.
