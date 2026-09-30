# Q-1 — Should a mixed name/index spelling of a namedtuple build?

**Where:** `src/confarg/typedload/_construct.py` (`_construct_namedtuple`) · **Filed:** 2026-09-30

Filed while fixing BUG-65 (closed). Each spelling of a namedtuple's sub-flags builds on its
own — `{'0': 7, '1': 8}` constructs positionally, `{'x': 7}` by name — but a mix of the two is
refused: `{'0': 7, 'y': 9}` raises `Unknown field(s) ['0']`, a message that calls a spelling
the same function accepts on its own "unknown". BUG-65 made the five front-ends agree on the
dict (keys as spelled, name and index alike), so the refusal is now shared — but before it,
the adapters silently renamed the index flag, and a user who mixed the spellings on one of
them got a build where vanilla refuses. The question is which way the agreement should lean:

- keep the refusal — a mixed spelling is rare and the per-key reconciliation has a priority
  question to answer (does `--pt.x 13 --pt.0 9` mean x is 13 or 9?); the message could still
  name the spelling rather than call it unknown;
- reconcile per key, as the all-index form already does — index keys fill the positions the
  name keys did not take, name keys win per field, so `{'0': 7, 'y': 9}` builds
  `Point(x=7, y=9)` and `{'x': 13, '0': 9}` picks one by a stated rule.

Precedent inside the same site: `_promote_namedtuple_positional` merges positional and
name keys by field name at parse time (`--pt 1 2 --pt.x 9` is `{'x': 9, 'y': 2}`), i.e. the
library already reconciles the two spellings when one arrives as positional tokens — the
mixed dict is the same collision one channel later.
