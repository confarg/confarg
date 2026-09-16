# FEAT-1 — Uneven shell-completion coverage

**Where:** `src/confarg/cli/argparse/_completion.py`, `src/confarg/cli/click/_completion.py` ·
**Filed:** 2026-09-12
**Effort:** L · **Risk:** low · **Impact:** behavior

argparse (argcomplete) and click have completion helpers; cyclopts has none. Click completion
covers bash and zsh, not fish. Completion is the one place where per-framework divergence may
turn out to be acceptable — decide that explicitly rather than by omission.
See [04-cli-adapters.md](../../architecture/04-cli-adapters.md).
