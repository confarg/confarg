# FEAT-17 — An end-of-options separator (`--`)

**Where:** `src/confarg/_parse_cli.py` (`_looks_like_flag`, the parse loop)
· **Filed:** 2026-09-17
**Effort:** M *(design pass; implementation not sized)* · **Risk:** medium · **Impact:** behavior

A bare `--` is an ordinary token in every front-end: nothing marks "everything after this is a
value". The `=` form is the escape for a dashed value and closes BUG-27
([10-design-decisions.md#the--form-is-the-escape-for-a-dashed-value](../../architecture/10-design-decisions.md#the--form-is-the-escape-for-a-dashed-value)),
but it can only shield one token, so a variable-length flag still cannot take a dashed element
after the first (`--tags=--a --b` reads `--b` as a flag).

The design pass has to answer three things before any code is written, which is why this is
filed rather than folded into BUG-27:

- **Adapter parity.** The host framework tokenizes argv before confarg is called, so an
  adapter cannot honor a separator confarg invented — the same wall that
  [11-limitations.md#cli-front-ends](../../architecture/11-limitations.md#cli-front-ends)
  records for whole-value flags under click. A vanilla-only `--` is a new parity gap
  ([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).
- **Scope of the separator.** argparse's `--` ends option parsing for the rest of the command
  line, which confarg has no use for — it has no positionals. A per-flag "the next N tokens are
  values" reading is closer to what is wanted and has no precedent to copy.
- **The other channels.** Neither the environment nor a config file has an equivalent, so a
  CLI-only spelling has to be justified as such
  ([feature-design.md](../../../docs-agents/feature-design.md)).
