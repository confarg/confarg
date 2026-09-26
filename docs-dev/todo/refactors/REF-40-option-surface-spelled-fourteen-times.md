# REF-40 — The nine-keyword option surface is spelled out fourteen times

**Where:** `src/confarg/_api.py`, `src/confarg/cli/*/_namespace.py`,
`src/confarg/cli/*/_context.py`, `src/confarg/cli/_clicklike/_context.py` ·
**Filed:** 2026-09-24
**Effort:** L · **Risk:** medium · **Impact:** behavior

`argv / env / env_prefix / env_separator / cli_prefix / config_flag / files / env_config /
union_tag` appears in **fourteen signatures** — `_api.py` four times (`merge`, both `load`
overloads, `load`), and twice each in the argparse, click, typer, cyclopts and `_clicklike`
merge modules. Measured cost across `src/`:

- **148 lines** that are nothing but `name=name,` pass-through arguments;
- **39 `# noqa: PLR0913`**, by far the most-suppressed rule in the package, and almost every one
  of them is this block;
- roughly **240 lines** of duplicated `Args:` prose;
- eight of the twenty-two longest functions in the package are these wrappers and contain **no
  logic at all** (`_api.merge` 92 lines, `cyclopts.merge_app` 86, `argparse.merge_namespace` 71,
  `_api.load` 71, `argparse.from_namespace` 70, `cyclopts.from_app` 69, `click.from_context` 68,
  `typer.from_context` 67).

It has already drifted, which is what makes this more than tidiness: `env_prefix` is documented
**five different ways**. `_api.py` says `""` reads every variable; `cli/cyclopts/_context.py`
does not mention it; `cli/_collect.py` is a single clause; `_pipeline.py` another. The invariant
that defaults live in `_defaults.py` and the literals are never repeated
([10-design-decisions.md#shared-reserved-key-names-live-in-_defaultspy](../../architecture/10-design-decisions.md#shared-reserved-key-names-live-in-_defaultspy))
holds for the *values* while the *documentation* of those values diverges.

Fix direction: a `MergeOptions(TypedDict, total=False)` in `_defaults.py`, consumed as
`**opts: Unpack[MergeOptions]`. Keyword-level type checking survives, and every default keeps one
home. Stage it — collapse the duplicated `Args:` blocks to one canonical block plus
cross-references first (low risk, ~240 lines), then the signatures.

Why **behavior** and not **none**: mkdocstrings renders `**opts`, so the published parameter
table moves to the `MergeOptions` page. A user changes nothing, but the documentation they read
changes shape. Settle that before starting, and record it in
[01-pipeline-and-contracts.md#public-api-seams](../../architecture/01-pipeline-and-contracts.md#public-api-seams).
Overlaps [REF-9](REF-9-review-public-argument-names.md), which reviews the *names* in this same
set — do that review first or in the same pass, since both rewrite these signatures.
