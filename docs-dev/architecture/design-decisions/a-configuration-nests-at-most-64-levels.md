# A configuration nests at most 64 levels

Every walker over the data recurses in Python: loading a document, reading its ops, the merge, the default layer, resolution, construction and `dump()`.
Each one recurses at least once per level, so data a JSON parser reads gave a raw `RecursionError`: from an empty stack, construction of a recursive struct (`child: Node | None`) gave up at 124 levels, of `Any` dicts at 245, the merge and the file walk at about 490, and PyYAML's and `tomllib`'s own parsers at about 491 and 496 (BUG-248).
A YAML anchor holding its own alias, or a Python dict holding itself, recursed until the same error.
How deep a given configuration could go also depended on the caller's stack: 150 levels built from an empty stack and failed from 500 frames down.

**A configuration nests at most 64 levels, counted from its root; deeper data is refused with a confarg error before any walker recurses through it.**
A position is one key, list index or struct field below the root, so `{"d": {"a": 1}}` holds `1` at depth 2, and a position more than 64 segments from the root is refused.
A key confarg reserves (a file's op key, a cast pin's `__value__`, `__root__`) and a pending `ListOp` are no level: their value is held at the dict's own position, so a configuration measures the same whether it is written with `__base__` or plainly, and the refusal names a path a flag could spell.

The count is from the configuration root, not from each source's own: a fragment 32 deep mounted 32 deep holds its leaves at 64, which is what the walkers recurse through after the mount.
So a mount path, a flag's or a variable's path and the position a decoded JSON value lands at all count.

## Why 64

The bound is half of where the costliest walker gave up on an empty stack, construction of a recursive struct at about 8 frames per level, which is BUG-145's rule for an expression body applied to data.
At the bound that walker uses about 512 frames, leaving about 480 of the default 1000 to the caller: pytest, a framework's dispatch, the application's own code.
Real configurations rarely pass 10 to 30 levels (a Kubernetes manifest nests 10 to 15).

| Limit | Worst case at the limit | Left to the caller |
|---|---|---|
| 128 (serde_json) | about 1024 frames | none: a typed configuration still crashes |
| 100 (BUG-145's number) | about 800 | about 190 |
| **64** | about 512 | about 480 |
| 32 | about 256 | about 740, but a generated configuration may need more |

The bound is fixed, not derived from `sys.getrecursionlimit()` or the stack in use: whether a configuration loads depends on the configuration alone, never on who calls.
It is not configurable either: a `max_depth` keyword would be carried through the five front-ends, and above about 120 it brings back the crash it lifts the refusal for.

`tests/test_depth.py::TestHeadroom` builds, loads and dumps a tree at the bound of each costly shape with 300 frames already on the stack, so a change that makes a walker costlier per level fails there before a user meets it.
A tagged union of recursive structs is left out while its locals walk is exponential in depth, a cost in time rather than stack ([BUG-258](../../todo/bugs/BUG-258-a-tagged-union-chain-takes-time-exponential-in-its-depth.md)).

## Where it is counted

`_depth.overflow` is the one count, without recursing: a dict, a list and a tuple are levels, a stored cast pin holds its value at its own position, and a container met again at no greater depth is not walked again, so a value sharing its parts (YAML aliases) is walked once per part, not once per path.
`_depth.refuse_overflow` raises with it, the class following the channel: `InvalidConfigFileError` for a document, as for one that does not parse, `ConfargError` elsewhere, as for a reserved key.
It is asked wherever a value enters, before the first walker meets it:

- **A document**, by `_files._load_any`, counted from its *mount*, the whole path from the configuration root: a root file, `--config.<path>`, `<PREFIX>CONFIG__<PATH>`, an `__include__` and an appended fragment, whose item index is part of its mount.
  A parser that gives up first is reported the same way, by `_files._load_document`, without a position.
- **A decoded JSON value**, by `_cast.decode_json`, counted from where it lands; a decoder that gives up first is reported the same way.
- **A flag's, a variable's or a mount point's path**, by `_depth.refuse_long_path`: before the type walk, which recurses once per segment, with one segment to spare for a trailing cast, and again, exactly, once the parse has told a cast from a key.
- **The data a caller hands** to `build()`, `from_dict()` and `resolve()`.
- **The tree its expressions resolve to**, in `_api._resolve_over_defaults`, which `build()` and `resolve()` share: an expression standing for a value copies it where it is written, so `right: ${left}` 40 levels down holds `left` 80 levels down.
  A default nothing touched is left out of the count, as construction never walks it.
- **What `dump()` writes**: the serializer is the one walk of an instance, so it counts its own descent, `len(path)` in `_serialize._open`, rather than a second walk re-implementing how a dataclass, a namedtuple, a plain class and a partial are descended into.
  A value a typed dump writes untyped is counted where it is written (`_serialize._untyped_at`), and a dict `dump_file()` writes is counted whole.
  So `dump()` never writes a file `load()` refuses.

A refusal names the first position past the bound, its middle elided past eight segments, with its length: `Cannot read config.json: it nests deeper than 64 levels, at 'd.a.a ... a.a' (65 levels).`

## A value that holds itself is refused as one

A container met again below itself is refused naming both positions: `Cannot read cycle.yaml: 'd.x' holds 'd', a value that contains itself.` The count tracks the containers on the path it is walking, so a shared part that is no ancestor (`a: *b`, `b: *b`) is no cycle.
The serializer tracks the instances it is serializing the same way; the same instance entered again at its own position, as a union serializes it as its variant, is no cycle either.
The depth bound alone would stop a cycle at level 65, but it would name a symptom: the user wrote two lines, not 65 levels.

## Rejected

- **Iterative walkers, and no bound.**
  Every walker, construction calling the user's constructors included, rewritten with an explicit stack, as msgspec's C code and Go's `encoding/json` (bounded at 10 000 levels) avoid the problem.
  A rewrite of the whole library for data no configuration holds, and PyYAML's and `tomllib`'s own parsers would still crash at about 490 levels.
- **Catching `RecursionError` at the public functions.**
  Cheap, but whether a configuration loads would depend on the caller's stack, and it would relabel a genuine recursion bug, such as a type walk that never ends, as data too deep.
- **Counting each source from its own root.**
  A fragment at a deep mount point, or a long flag path, still reached the walkers deeper than any source.
- **Counting raw nesting, op keys included.**
  `d.x: {__base__: …}` would be one level deeper than `d.x: …`, and a refusal could name a position spelled with an op key.
- **The same refusal for a cycle.**
  See above.
- **A `TooDeepError` class.**
  No other rule shared by every channel has a class of its own, and a document too deep would not be an `InvalidConfigFileError`.

## Precedents

- serde_json refuses past 128 levels, "recursion limit exceeded", and offers `disable_recursion_limit` only to a caller bringing its own stack growth.
- pydantic's JSON parser (jiter) refuses past 200 levels; validating a recursive model from Python data it refuses at 99, but reports it as "cyclic reference detected", the mislabelling the cycle message above avoids.
- orjson refuses `loads` past 1024 levels ("depth limit exceeded") and `dumps` past 254 ("Recursion limit reached").
- `json.dumps` reports a cycle on its own, "Circular reference detected".
- OmegaConf, PyYAML, `tomllib` and `tomli_w` raise the raw `RecursionError`, at 98, about 491, 496 and 994 levels.
- BUG-145 bounds an expression body at 100 levels, by the same reasoning ([expressions](../expressions/resolution.md#resolution-algorithm)).
