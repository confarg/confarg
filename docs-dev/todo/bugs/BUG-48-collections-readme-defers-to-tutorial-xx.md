# BUG-48 — `12_collections` cites "Tutorial XX" instead of a real tutorial

**Where:** `examples/12_collections/README.md:279` · **Filed:** 2026-09-27
**Effort:** S · **Risk:** low · **Impact:** none

The deferral to the environment-variable discussion names its target as "Tutorial XX", an
unfilled placeholder. [Tutorial #15](../../examples/15_json_inputs/README.md) is the likely
intended target — verify, then link it (or whatever tutorial actually covers JSON arguments
from the environment) and renumber the link.

<!-- pytest-markdown-console: notest -->
```console
$ grep -n "Tutorial XX" examples/12_collections/README.md
279:We defer the discussion on how to populate collections from environment variables to the more general mechanism of specifying arguments as JSON in Tutorial XX.
```
