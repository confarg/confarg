# REF-78 — `.ruff.toml` selects "PL" twice

**Where:** `.ruff.toml` · **Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

`[lint] select` lists `"PL"  # Pylint` twice, at the pylint position and again between `TRY` and
`RUF`. Harmless — a selected prefix stays selected — but a reader scanning the list learns the
wrong alphabet (the second entry sits after `TRY`, as if a rule family were being appended out of
order), and a future split of the `PL` selection into per-code entries could easily edit the one
copy and leave the other [found while fixing REF-57]. Drop the second entry.

No behavior question attached: `uvx ruff@0.15.16 check .` passes before and after the deletion.
