# A configuration copies at most 100 000 positions

A configuration can name one part many times, and every walker over the data rebuilds a part at each position it is reached by: loading a document, the locals layer, stripping the locals, an expression's typed read, construction.
So a few hundred bytes could name millions of positions and stall the host for minutes (BUG-259), by three routes, on every channel:

| Route | Shape | Before |
|---|---|---|
| YAML aliases | each line aliasing the one before ten times (`l1: [*l0, *l0, …]`) | 349 bytes, 10⁶ leaves: 14 s |
| a location read again | each JSON file including the one before ten times, no alias at all | 10⁵ leaves: 21 s |
| references | each key referencing the one before ten times (`l1 = ["${d.l0}", …]`), in a file, `--d.json` or a variable | 631 bytes, 10⁶ leaves: 27 s to load, 11 s to dump |

A fourth sat inside PyYAML itself: `SafeConstructor.flatten_mapping` splices a merged mapping's pairs into the node holding `<<` without removing the duplicates, so a chain of mappings each merging the one before ten times held 10ⁿ pairs that only the final `dict` collapsed: 404 bytes took 1 s inside `yaml.safe_load`, each further line ten times more, for a result of ten keys.

The depth bound did not catch any of them: such a tree is only as deep as its lines ([a configuration nests at most 64 levels](a-configuration-nests-at-most-64-levels.md#a-configuration-nests-at-most-64-levels)).

**A configuration copies at most 100 000 positions; the copy past them is refused with a confarg error before any walker meets it.**
A position is what the depth bound counts, one key or list item; a *copy* is every position produced beyond the first occurrence of what it copies.
What an author wrote is never counted: a large document costs what its bytes cost, which is no amplification.

## What copies

- **A part met again**, a mapping or a sequence a YAML alias names twice, or a part a caller's data shares: every position below it, as expanded, each time it is met past the first.
  An alias of a scalar copies nothing; the alias is its one position, as written.
  `_depth._shape` counts it in the walk the depth count already takes, which meets a shared part once per path it is reached by and walks it once.
- **A YAML merge key**: each pair it merges into the mapping holding it, once the mapping's own keys and the earlier merged mappings have taken theirs.
  `_files._yaml_loader`'s `flatten_mapping` merges each key once, keeping YAML's precedence (a mapping's own key wins, then the earliest merged mapping), which makes flattening linear, and charges the pairs it merged.
- **A location read again**: every position of its document, by any route, a root file, `--config.<path>`, `<PREFIX>CONFIG__<PATH>` and `__include__` alike.
  The first read of a location is written; a location is its identity (`_sources._identity`), so `./t.json` and `t.json` are one, and its options (`orient`) are no part of it.
  `_files._load_any` charges it, where the document is read.
  A location is read once per configuration: what the configuration has read, `_files.Reads`, keeps its join, its identity and its document, so a read again costs the positions it copies and nothing else.
  A read costs about 3 ms on Windows whatever the document holds, most of it resolving the path, so 100 000 positions copied through ten-position fragments were 10 000 reads and 29 s; read once, they are 1 s.
  Charging each read a floor of positions, its own price, was rejected: a second number to choose, and every read but the first still paid it.
  The cost is that a configuration reads a snapshot: a file changing while one `load()` reads it is read as it first was, and a remote document is fetched once, as JSON-Schema resolvers (`referencing`, json-schema-ref-parser) fetch a `$ref` once per resolution.
- **A reference**: every position below what it reads, whatever the expression makes of it (`_expressions._read_through`), so `${len(d.big)}` is charged as `${d.big}` is.
  A typed read walks what it reads, a copy or not, and charging the walk bounds the time as well as the memory.
  This reverses the rule BUG-146 wrote, that a read "counts nothing: a hundred `${big}` cost no more than one" ([a computed value is bounded](../expressions/safety-model.md#a-computed-value-is-bounded)): it held for the evaluator, and not for the walkers after it.

`dump()` counts nothing: what it writes holds no copy, a shared part written out in full, so its cost is the size of what it writes, and a file it writes reads back without a copy.

## One budget per configuration

The count is one budget, `_depth.Copies`, opened by each public call — `load()`, `merge()`, `build()`, `resolve()`, `from_dict()`, an adapter's `merge_*` and `from_*` — and passed down every walk that charges it, as their other state is.
The merge carries it inside `_files.Reads`, what the configuration has read, which holds the budget and the locations read once; a read of a location only ever charges the budget of the configuration it was read for, and resolution takes the budget alone, since it reads no location.
Every source, channel and resolution of one configuration share it, and `load()` shares it between its merge and its build, so a file's aliases and the references over them are counted together.
A best-effort pass that reads before the merge, the tag scan and an adapter's registration, opens its own.
The tree resolution returns is not counted again: its shared parts are what the reads already charged.

## Why 100 000, fixed

Measured through `load()`, typed or `Any`, a copied position costs about 45 µs and 130 bytes, so the bound holds the worst a tiny file can ask to about 4.5 s and 13 MB.
A real configuration copies far less: a docker-compose file merging a 30-key anchor into 20 services copies about 600 positions, a CI file sharing 30-key anchors across 100 jobs about 3 000.

| Bound | Worst case from a few hundred bytes | Refuses |
|---|---|---|
| 10 000 | 0.5 s, 1.3 MB | 200 services merging a 50-key anchor |
| **100 000** | 4.5 s, 13 MB | 200 references to a 1 000-position template |
| 1 000 000 | 45 s, 130 MB | — |

It is fixed and not configurable, for the depth bound's reasons: whether a configuration loads depends on it alone, and a keyword would be carried through five front-ends.

## The refusal

The class follows the channel, as the depth bound's does: `InvalidConfigFileError` for a document, read or read again, `ConfargError` for a caller's data, `UnsafeExpressionError` for a reference, as BUG-146's refusals of a computed value are.
It names where the bound was crossed and the count there:

```text
Cannot read b.yaml: it copies more than 100000 positions, at 'd.l5.3' (100010 copied).
Cannot read c.yaml: it copies more than 100000 positions, at line 15 (100001 copied).
Cannot read f0.json again: it copies more than 100000 positions, at 'd.3.7.2' (100010 copied).
Cannot build Config: it copies more than 100000 positions, at 'd.svc-1043' (100050 copied).
Error in expression '${d.l3}': Cannot read 'd.l3': it copies more than 100000 positions (101180 copied).
```

Each is built by one factory, `ConfargError.too_many_copies`, which `Copies.charge` raises, of the channel's class, only when the bound is crossed.
A reference's refusal is the same text inside its expression, as every refusal of an expression is ([a refusal names its expression](../expressions/resolution.md#a-refusal-names-its-expression)), and names the path it read: a read is charged whole, so no position inside it crosses the bound.
The action is a string, formatted at every charge rather than when the refusal is raised: a reference read spells its path, about half a microsecond against the ten and more the read costs, which is not worth a second way of passing it (REF-96).

A merge key is named by its line: PyYAML merges while it builds the mapping, before any position is known.

## Rejected

- **Sharing walkers**, each walker reading a part once and handing the same object to each position.
  A later layer patches a position, so a shared part needs copy-on-write in every walker, and a typed read still walks what it reads; a bound is one count.
- **A ratio of copied to written positions, enforced past a threshold** (Go's yaml.v3, expat, serde_yaml).
  It lets a large document copy more, at the price of two numbers and a slope to explain; a fixed number is the depth bound's form.
- **A bound on every position, written or copied.**
  It refuses a large data file, 50 000 rows of a CSV, which copies nothing.
- **YAML aliases alone**, as BUG-259 was filed.
  A location read again and a reference make the same tree with no alias, from every channel.
- **A budget per source.**
  Ten sources each under the bound cost ten times it; one budget is what the configuration costs.
- **Trusting a caller's data.**
  An application reading YAML itself and handing it to `build()` met the stall again; the count is the one every entry point asks, as the depth bound and the cycle check are.
- **Counting in `dump()`.**
  Its output holds no copy and reads back without one; a shared part's cost there is the size of the file asked for.

## Precedents

- Go's yaml.v3 refuses "document contains excessive aliasing" once aliases make up more than 99 % of 400 000 decodes, a share falling to 10 % at 4 000 000 (Kubernetes' CVE-2019-11253); its comment puts 400 000 at "~100MB of allocations".
- SnakeYAML refuses more than 50 aliases to a collection (`maxAliasesForCollections`, CVE-2017-18640).
- serde_yaml refuses an alias expansion over 100 times the document's events, "repetition limit exceeded".
- expat refuses an entity expansion amplifying a document more than 100 times past its first 8 MiB, and .NET more than 10 000 000 characters of entity expansion (`MaxCharactersFromEntities`), the document itself unbounded: the "billion laughs" that names the shape.
- PyYAML, ruamel.yaml and OmegaConf bound nothing.
