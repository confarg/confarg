# REF-76 — `FlagSpec.accumulates` has no reader left in the merge

**Where:** `src/confarg/cli/_spec.py` (`FlagSpec.accumulates`) · `src/confarg/cli/_build.py`
(the five sites that set it) · `src/confarg/cli/argparse/_register.py` (`action="extend"`) ·
**Filed:** 2026-10-01
**Effort:** S · **Risk:** low · **Impact:** none

`accumulates` made argparse register a repeated multi-token flag with `action="extend"`, so the
Namespace the flat collector read held every occurrence's tokens rather than the last
(BUG-37). Since REF-72 the adapters' CLI channel is read off argv by vanilla's loop, and the
Namespace is only checked for flags argv does not spell, so the value argparse stores no longer
reaches the merge. The field still keeps a host application's own read of the Namespace honest
(`ns.tags` holds what was typed), which may be reason enough to keep it — but that is a
public-API promise `FlagSpec` never made explicitly. Decide: document it as that promise, or
drop the field (it is public on `confarg.cli.FlagSpec`, so dropping it is a breaking change for
anyone building specs by hand). See
[cli-adapters/list-syntax-divergence.md#list-syntax-divergence](../../architecture/cli-adapters/list-syntax-divergence.md#list-syntax-divergence).
