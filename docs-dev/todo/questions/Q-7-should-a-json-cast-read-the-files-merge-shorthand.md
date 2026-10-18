---
filed: 2026-10-11
where:
  - src/confarg/_merge.py::_normalize_merge_ops
  - src/confarg/_cast.py::resolve_forced_value
---
# Q-7 — Should a JSON cast read the files' merge shorthand?

A `.json` cast is documented as storing its decoded value raw ([force casts](../../architecture/cli-parsing/casts-and-reserved-words.md#force-casts)), yet every merge runs `_normalize_merge_ops` over it as over a file's document. So `--sec.json '{"a-": null}'` deletes the file's `sec.a`, `{"xs+": [1]}` appends, and a dict field can never receive a key that ends in `+` or `-` through a cast. Only a file was meant to spell an op by name ([no channel types an op](../../architecture/pipeline/deep-merge.md#no-channel-types-an-op)). The reserved `__append__` keys go the same way: a flag naming one is refused, but the same key inside a cast's JSON becomes the op.

The options:

- **The cast is a file's document in one token.** The shorthand and the reserved keys apply, and a decoded value is one more way to write a patch. BUG-228 then makes every position honor it. This is the behavior today, minus the positions BUG-228 lists.
- **The cast is a value.** Its keys are data, as a field flag's are, and only a file spells a patch. Then `{"a-": null}` sets a key named `a-`, and BUG-228 closes by keeping the decoded value out of normalization.

BUG-228 waits on the answer.
