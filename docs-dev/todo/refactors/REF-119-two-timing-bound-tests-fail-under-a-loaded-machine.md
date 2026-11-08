---
filed: 2026-10-26
where:
  - tests/test_copies.py::TestReferences  # test_a_reference_bomb_is_refused_at_once, refused_within(5, ...)
  - tests/test_merge_roundtrip.py::TestCliRoundTrip  # test_cli_flat_roundtrip, Hypothesis's default deadline
effort: S
risk: low
impact: none
severity: trivial
inferred: true  # the failure messages were not kept; the timing cause rests on the run's length and the reruns
---

# REF-119 — Two timing-bound tests fail under a loaded machine

A full `uv run pytest -n 4 -p no:markdown-console`, run while another session loaded the machine, failed three tests out of 11 805 and took 263 s; the same tree passed every test in 150 s once the load was gone, and each failing file passed alone.
Two of the three are known: `test_a_reference_bomb_is_refused_at_once[env]`, which asserts the refusal lands within 5 s of wall clock, and `test_cli_flat_roundtrip`, a Hypothesis test of 200 examples under the default 200 ms per-example deadline *(inferred: the cause)*; the third was cut from the output.
`test_cli_flat_roundtrip` had failed once before under `-n 4`, during BUG-266, and failed again alone in a later full run of 128 s; it passed in each of three runs of its file.

Direction: give the round-trip tests `deadline=None`, as a round trip through files has no latency contract to keep, and measure the reference bomb against a bound a loaded run keeps, or by the positions it copies rather than by the clock, which [the copy budget](../../architecture/design-decisions/a-configuration-copies-at-most-100000-positions.md) already counts.
