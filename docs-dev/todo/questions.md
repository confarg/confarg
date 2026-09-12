# Questions

Points only the maintainer can settle: missing rationale, undecided trade-offs, anything where
guessing would bake in a choice nobody made. Ask, then record the answer in
[../architecture/](../architecture/README.md) and delete the entry.

See [README.md](README.md) for the ticket format.

### Q-1 — Why was implicit subclass discovery removed?

**Where:** `src/confarg/typedload/_construct.py` · **Filed:** 2026-09-12

PR #58 inferred a subclass from CLI or file input without a `union_tag`; PR #63 removed it.
Both commits have empty bodies, so the reason is lost — ambiguity, import cost, surprising
action at a distance, something else. It matters because several open ideas (structural
disambiguation, `Annotated` metadata) would brush against the same ground. Do not reintroduce
any form of inference before this is answered.
See [05-types-and-construction.md#inheritance](../architecture/05-types-and-construction.md#inheritance).
