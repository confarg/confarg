# A YAML key is its text

PyYAML's `safe_load` reads YAML 1.1, whose resolver types a plain scalar wherever it stands, keys included: `off`, `on`, `yes`, `no`, `true`, `false` are booleans, `null` and `~` are `None`, `1` an integer, `1:30` the base-60 integer 90, `2001-01-01` a date.
So a field named `off` could not be set by an unquoted key: `off: 5` reached confarg as the key `False`, and the refusal named a field nobody wrote, `Unknown field(s) ['False']` (BUG-254).
The same reading refused `s: {1: 5}` for a `dict[str, int]` (`Cannot coerce int 1 to str`), and a field named `true` or `null` was unreachable from YAML at all, while TOML and JSON, whose keys are always text, set every one of them.

**A plain YAML mapping key reaches confarg as the text it is written as, and the target types it, as it types a TOML or a JSON key.**
A field name is matched as text; a dict key is coerced by the key coercion every channel's text goes through ([which keys are one key](../pipeline/deep-merge.md#which-keys-are-one-key)), so `i: {0x1f: 5}` is `{31: 5}` for a `dict[int, int]` and `b: {yes: 5}` is `{True: 5}` for a `dict[bool, int]`, exactly as `"0x1f"` and `"yes"` are in TOML, or `--i.0x1f` and `--b.yes` on the command line.
Values are untouched: `debug: yes` is still `True`, and [the token model](../types/token-model.md#token-model) keeps a file's value as the file typed it.

`_files._yaml_loader` is the one place this is decided, a `yaml.SafeLoader` whose resolver answers `str` for a scalar composed in key position.

- **A key the author tagged keeps its tag's type.**
  The resolver is asked only about an untagged scalar, so `!!int 1: 5` is the integer key `1`, refused under a `dict[str, int]` as before.
  Implicit resolution is what YAML 1.1 and 1.2 disagree on; an explicit tag is the author typing the key on purpose, as a tagged value is.
- **`<<` stays YAML's merge key**, the one plain key whose resolution is structure rather than a type.
- **Every plain key is text, the null words and the empty key included**: `~: 5` is `{'~': 5}`, `? : 5` is `{'': 5}`.
- **A scalar is read where it is written.**
  An anchored key aliased as a value (`{? &k 1 : x, v: *k}`) is the text `'1'` at both positions, since the alias is the node the key composed.

## What it costs

- An `int` key YAML 1.1 read in a way no other channel does is refused: the leading-zero octal `017` (15 in YAML 1.1) and `01`, and the base-60 `1:30`, are `Cannot coerce str '017' to int`, as `--i.017` is.
  `0o17`, `0x1f` and `1_000` read as before, and a `bool` key takes `1` and `0`, which YAML read as integers and refused.
- Under an `Any`, a bare `dict` or a `dict[Any, V]`, a plain key is text: `a: {1: 5}` builds `{'1': 5}` where it built `{1: 5}`, which is what TOML and JSON build.
  The merge already met the two spellings as one key there.
- A non-string key reaches the merge from YAML only through a tag, or from a caller's data.

## Writing

`dump_file()` writes a YAML key as text, as it writes a TOML or a JSON one ([a key is written as the text it is met by](a-written-file-holds-what-its-reader-reads-back.md#a-key-is-written-as-the-text-it-is-met-by)), since the reader reads a plain key back as text whatever it was written as.
PyYAML quotes a text another reader would type, so `{1: 6, None: 7}` is written `'1': 6` and `'null': 7`, and any YAML reader agrees with confarg about the key.
Writing the keys bare (`1: 6`) reads the same in confarg, and was rejected because another YAML reader would then type them.
YAML had held its own scalars as keys until then, and `_files._written_key` returned `None` both for a key with no spelling and for the key `None`, so a `None` key was refused for YAML with a message saying no YAML key read back as it.

## Rejected

- **Only YAML 1.1's extra boolean words as text** (`yes`, `no`, `on`, `off`, in each case PyYAML reads; PyYAML does not read `y` and `n` as booleans, though YAML 1.1 lists them).
  It fixes the reproduction, and leaves a field named `true` or `null` unreachable and `s: {1: 5}` refused.
- **YAML 1.2's core schema everywhere**, keys and values (ruamel.yaml's reading).
  `true` and `null` are still a boolean and a null in YAML 1.2, so those fields stay unreachable; and `debug: yes` becomes the text `'yes'`, which a `bool` field refuses, since a file's string is no token.
- **Keeping the reading and naming the quirk in the refusal**, as the time and duration refusals name YAML's base-60 numbers.
  The configuration stays unwritable without quotes, and a `dict[str, V]` keyed by numbers stays refused.
- **Every scalar key as text, tags included.**
  It drops a type the author wrote on purpose, which nothing else in a file is denied.

## Precedents

Go's yaml.v3 and serde_yaml decode a scalar by the type it lands in, and into a string yaml.v3 gives the scalar's text.
GitHub Actions reads a workflow's `on:` key as the string `on`, where a PyYAML reader gets `True`: the best-known instance of this bug.
StrictYAML types every scalar by its schema, and the text alone otherwise.
