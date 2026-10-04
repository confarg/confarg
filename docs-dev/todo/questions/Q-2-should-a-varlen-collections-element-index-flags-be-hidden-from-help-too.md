# Q-2 — Should a varlen collection's element index flags be hidden from help too?

**Where:** `src/confarg/cli/_build.py` (`_addresses_fixed_seq_element`) · **Filed:** 2026-09-30

Filed while fixing BUG-80 (closed). The hiding decision BUG-80 landed hides an index
spelling only when its parent node is a *fixed-length* sequence — a `tuple[X, Y]` or a
namedtuple — because that is the scope that was asked for. A varlen collection's element
flags (`--tags.3`, `--items.-1`) are the same patch syntax, registered from argv by the
same scan, and keep their `Set the collection element at '...'` line in `--help` whenever
the flag is also spelled in the argv the parser was built from.

The question: one rule for every index spelling, or the fixed-length boundary? Arguments
each way:

- one rule: an index spelling patches a position wherever it lives, and a help line for
  `--items.3` is exactly the clutter the hiding was for;
- keep the boundary: a fixed-length sequence's element flags are the *only* per-element
  spelling it has besides `--field.N`, while a list also advertises `--field+`, and the
  element flag is how the docs teach list patching — hiding it removes the one
  discoverable spelling of a form vanilla's own READMEs show.

Precedent to weigh: namedtuple index spellings are *static* (always in help before
BUG-80's hiding), while varlen element flags only appear when argv already spells them —
so the boundary mostly changes the `--items.3 --help` case, and the cost of a wrong
either-way answer is small.
