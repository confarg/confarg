# REF-64 — The clicklike completion tests assert that nothing was added

**Where:** `tests/cli/click/test_click_integration.py`,
`tests/cli/typer/test_typer_integration.py` (`TestSetupCompletion`) ·
**Filed:** 2026-09-26
**Effort:** S · **Risk:** medium · **Impact:** none

`test_completion_mode_extends_command` is documented "When `_PROGNAME_COMPLETE` is set, dynamic
flags are added to the command", but its body asserts `len(cmd.params) == before` — that nothing
was added. It passes for a reason unrelated to its claim: the target is the flat dataclass
`Simple`, and `build_dynamic_flags(Simple, [])` correctly returns `[]`, so there is nothing to
add. The test therefore passes with the whole body of `setup_completion` deleted. Same family as
[REF-38](REF-38-collect-names-keyword-args-or-asserts-away-claim.md) and
[REF-39](REF-39-dict-field-env-test-or-asserts-away-claim.md).

Mutation testing makes the consequence measurable: 63 of the 81 mutants of
`cli/_clicklike/_completion.py` survive (22% mutation score, the lowest in the library), 56 of
them in `setup_completion` alone. `cli/click/_completion.py` and `cli/typer/_completion.py` score
30% each. The `try: … except Exception: _log.debug(…)` wrapper that keeps completion from ever
crashing the shell ([04-cli-adapters.md#completion](../../architecture/04-cli-adapters.md#completion))
is what makes this invisible: every mutation degrades silently to fewer suggestions, so only a
test that asserts the *positive* outcome can catch one.

Fix direction: give the test a target and a `COMP_WORDS` that actually produce a dynamic flag,
then assert the flag arrived. A collection-patch token is the smallest case —
`build_dynamic_flags` on a `list[int]` field with `argv=["--items.0", "5"]` returns a spec named
`items.0`, and `setup_completion` adds exactly that param:

```python
@dataclass
class Cfg:
    items: list[int] = field(default_factory=list)

# COMP_WORDS="cli --items.0 5 ", COMP_CWORD=3, _CLI_COMPLETE=bash_complete
before = [p.name for p in cmd.params]
setup_completion(cmd, Cfg)
assert "items.0" in [p.name for p in cmd.params]   # observed: added
```

Keep `test_completion_exception_is_swallowed` as it is — it pins the never-crash contract, which
is a separate claim. Per [cross-channel parity](../../architecture/09-invariants.md#cross-channel-parity)
the same assertion belongs in the typer copy of the class, which has the identical gap.
