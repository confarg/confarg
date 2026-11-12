---
filed: 2026-11-12
where:
  - src/confarg/typedload/_construct.py::_list_index_of
  - src/confarg/_merge.py::_apply_list_ops
  - src/confarg/_merge.py::_patch_needs_the_type
---

# Q-11 — Should a list read an index key with `int()`, or as `str()` writes one?

A list's index keys are read by bare `int()` in construction (`_list_index_of`, REF-94) and in the merge (`_apply_list_ops`, `_patch_needs_the_type`), where a fixed tuple's and a namedtuple's are read by `_fixed_position`, which accepts only an index as `str()` writes it ([collection patches](../../architecture/cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index) records the split: argv and the environment refuse `--xs.01`, a file's `xs: {"01": 5}` patches index 1; [limitations](../../architecture/limitations.md) lists it).
So a dict that builds as a list today reads, with `int()`:

| Key | List (`int()`) | Fixed tuple (`_fixed_position`) |
|---|---|---|
| `"01"`, `"+1"`, `" 1"`, `"1_0"` (index 10), `"١"` (Arabic-Indic one) | an index | refused as no integer index |
| `True` | index 1 | refused |
| `1.5` | index 1 | refused |
| `float("inf")` | refused as no integer index (REF-94 folded the raw `OverflowError`) | refused |

Run on `{"x": {"+1": 1, "0": 2, "2": 3}}`: `list[int]` builds `[2, 1, 3]`, `tuple[int, int, int]` raises `dict keys must be integer indices`.

The options:

- **Keep `int()` for a list.**
  Nothing that builds changes, and the merge, construction and the file notes keep agreeing; the cost is that a list and a fixed tuple read one key differently, and that a bool or a float key is an index.
- **Read a list's key as `str()` writes it** (`_list_index`, what argv, the environment, a `${xs.0}` reference and JSON Pointer's array index read).
  One rule on every sequence and every channel, a file included; the cost is that a file's `xs: {"01": 5}` is refused, and a bool or float key too, so a configuration that loads today fails.
- **Keep `int()` for text, refuse a bool or a float key**: the smallest change, which removes the `True` and `1.5` readings and leaves the file leniency.

Precedents: JSON Pointer (RFC 6901) and jq take only `0|[1-9][0-9]*` as an array index, and the notes already cite them for the walk; Python's own `int()` is the lenient reading and the one the code started with.
