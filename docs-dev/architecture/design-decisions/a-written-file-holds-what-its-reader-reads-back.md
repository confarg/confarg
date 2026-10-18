# A written file holds what its reader reads back

`dump_file()` writes what the file's format holds and nothing else: `_files._writable` walks the dict `dump()` (or `_serialize_untyped`) returned against the format's `_Format`, and refuses a value or a key the format's reader would not read back as itself, with a `ConfargError` naming its path (BUG-251).
A format holds what confarg's own reader of it reads back: a scalar, a list (a tuple is written as one), a dict, `None` everywhere but in TOML, and the dates its writer holds natively — a YAML or a TOML `date` and `datetime`, a TOML local `time`.

That is the round-trip promise and nothing stricter.
A JSON file writes `Infinity` and `NaN` as Python's `json` writes them, and a TOML file an integer past 64 bits, which `json.loads` and `tomllib` read back, though RFC 8259 has no such number and TOML 1.0 asks a parser to refuse such an integer ([limitations](../limitations.md#callables-and-serialization)).
Refusing them would have made a value confarg reads back undumpable to the format; pydantic and orjson write a non-finite float as `null` instead, which does not read back at all.

The text is rendered in memory and the file opened only once it is (`_files._dump_file`), so a refused dump leaves the file as it was.
Before BUG-251 the writers streamed into a file already opened for writing, and their refusal came after the truncation: a YAML file was left empty, a JSON one cut mid-value, a TOML one valid but short of the value it refused.
OmegaConf's `save` likewise renders `to_yaml` before it opens the file; `json.dump`, which confarg used, streams.

An object no configuration spells is still written untyped by `dump()`, with its warning ([serialization](../types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)): `dump()` returns a dict to Python code that may never write it, and FEAT-42 chose to warn there.
`dump_file()` is where it is refused.
Wrapping the writers' own exceptions instead was rejected: none names a path, and each writer refuses with its own type (PyYAML's `RepresenterError`, `json`'s and `tomli_w`'s `TypeError`, `tomli_w`'s `ValueError` for a time with an offset).
The rules belong to `dump_file()` alone: `dump()` takes no parameter applying them to a dict a caller hands their own writer.

TOML has no null, so a `None` is refused there, naming the formats that hold it.
Omitting the key, as the Rust `toml` crate does for a `None` field and Python's `toml` does for every `None` value, was not taken: the key then reads back as the field's default, which is `None` only sometimes, and in a `merge()` overlay a `null` sets the field where an omitted key leaves the base as it was.
`tomli_w` and `tomlkit` refuse it too.

## A key is written as the text it is met by

A TOML or a JSON key is text.
A key that is no string is written as the text the other channels meet it by ([which keys are one key](../pipeline/deep-merge.md#which-keys-are-one-key)): its leaf serialization, then JSON's spelling (`_merge._key_spelling`), so `1` is written `"1"`, `True` `"true"`, `None` `"null"`, a date its ISO text (`_files._written_key`).
Each reads back as the key it was through a typed dict's key coercion; under an `Any` it reads back as the text, which the merge already reads as the same key.
JSON's writer did this itself for a scalar key, while `tomli_w` refused every key that is no string, so a `dict[int, int]` could not be dumped to TOML at all (BUG-245).
Refusing such a key with a confarg error was weighed: TOML would still hold no `dict[int, int]`, and JSON would spell what TOML refused.
Precedents: `json`, pydantic's `model_dump_json`, serde_json and msgspec write an integer key as text; `tomli_w` and the Rust `toml` crate refuse it; PyYAML keeps it.

Two keys of one dict spelled alike, `1` and `'1'` under an `Any`, are refused, naming both: JSON wrote the two and its reader kept the second, and TOML would write a file `tomllib` refuses.
A YAML file holds both as they are.
A key with no text at all, a tuple, is refused by every format, YAML's included: PyYAML writes it as a complex key, which `yaml.safe_load` refuses.
A typed dict whose key type construction reads no key as, `dict[tuple[int, int], V]`, is refused earlier, by `dump()` ([an unsupported leaf is refused both ways](../types/serialization.md#an-unsupported-leaf-is-refused-both-ways)).
