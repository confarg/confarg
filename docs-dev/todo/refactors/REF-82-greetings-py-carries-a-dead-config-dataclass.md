# REF-82 — `greetings.py` in two examples carries a dead `Config` dataclass

**Where:** `examples/18_callables/greetings.py`, `examples/19_bindings/greetings.py` ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

Both copies define a `Config` dataclass with a `greetings_fn` field that nothing references:
the scripts define their own `Config` with `greet_fn`, and confarg reaches the module's
callables by FQN at load time, not by import. Delete it. Its `greetings_fn` spelling — the
field name no script uses — is what muddied REF-59's account of the invented yaml blocks,
so the dead class is not only dead weight but an active source of confusion.
