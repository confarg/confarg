---
filed: 2026-10-20
where:
  - src/confarg/_depth.py::_shortened
  - src/confarg/_depth.py::refuse_long_path
  - src/confarg/exceptions.py::_spell_long_path
  - src/confarg/exceptions.py::ConfargError
effort: S
risk: low
impact: behavior  # every too-deep refusal of a flag, a variable or a mount point changes its text, under (b) and (c)
severity: trivial
---

# REF-117 — Two rules elide a long path

A refusal elides a long path twice over: `exceptions._spell_long_path` keeps the first three and last two segments past eight, `_depth._shortened` keeps the first 24 and last 12 characters of a flag past 40, and its docstring says it does so "as a path is".
The flag is its path spelled with dots, so one rule — by segments — would serve both, the ticket first said.
It is not that simple, because one message carries both:

```text
Cannot set '--n.n.n.n.n.n.n.n.n.n.n. ... .n.n.n.n.n.v': it nests deeper than 64 levels, at 'n.n.n ... n.v' (71 levels).
Cannot set 'APP_N__N__N__N__N__N__N_ ... __N__N__N__V': it nests deeper than 64 levels, at 'N.N.N ... N.V' (71 levels).
```

A flag is its path plus what the channel wraps it in: the `--` prefix, an environment variable's prefix and `__` separators, a cast or a `+` suffix, a mount's `--config.` head.
Cutting it by segments needs a splitter per channel, or a different message, so unifying the two rules changes what a user reads, and the choice is the maintainer's:

- **(a) Keep both rules**, reword `_shortened`'s docstring so it no longer claims to elide "as a path is", and close the ticket.
  Nothing a user reads changes; the two rules stay, each on what it cuts (a spelling by characters, a path by segments).
- **(b) Cut the flag by segments**, through a splitter per channel (`--` and dots, the environment's separator and prefix, a mount's head and suffix).
  One rule, but every too-deep message of a flag, a variable and a mount point changes its text, and the splitters are three more places a channel's spelling is decided.
- **(c) Drop the flag from the message**, since `at '<path>' (N levels)` already names the position: `Cannot set: it nests deeper than 64 levels, at 'n.n.n ... n.v' (71 levels).` One rule and no splitter, but the user no longer sees the flag they typed, which the other refusals of a flag (`Cannot set '--d.__base__'`, `Unknown argument: '--x'`) all name.

The recommendation is (a): the two rules cut different things, and the message is already readable.

The other half of the ticket, the two depth bounds sharing the name `_MAX_DEPTH`, is done: `dictexpr._expressions._MAX_EXPRESSION_DEPTH` bounds how deep an expression's syntax tree nests (BUG-145), `_depth.MAX_DEPTH` how deep a configuration nests.

See [a-configuration-nests-at-most-64-levels.md](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels).
