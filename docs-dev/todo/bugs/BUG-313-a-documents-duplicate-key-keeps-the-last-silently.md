---
filed: 2026-11-08
where:
  - src/confarg/_files.py::_yaml_loader  # SafeLoader builds a mapping's own pairs into a dict, the last of a key winning
  - src/confarg/_files.py::_load_json_item  # json.loads keeps the last of a name
  - src/confarg/_cast.py::decode_json  # a JSON value on argv or in the environment, decoded the same way
effort: M
risk: medium  # the file channel and the JSON values of the other two; no test holds a duplicate key
impact: config  # a document that loads today with a duplicate key is refused
severity: critical  # a configured value is dropped with no error
introduced_by: [PR-5]  # the initial version read YAML by yaml.safe_load and JSON by json.load
---

# BUG-313 — A document's duplicate key keeps the last, silently

A YAML or JSON mapping spelling one key twice loads with the earlier value dropped: `s: a` then `s: b` builds `s='b'`, and so does `{"s": "a", "s": "b"}`, in a file or as a JSON value on argv or in the environment.
TOML already refuses it (`tomllib`), and CSV refuses a duplicate column.
It is the parsers' half of [one value holds each key once](../../architecture/pipeline/deep-merge.md#one-value-holds-each-key-once): BUG-312 refused two spellings the type reads as one key, but a key spelled twice alike never reaches construction twice, the parser having kept one.

Fix direction: refuse a mapping's own duplicate key at parse time, naming the key and the location, as tomllib, ruamel.yaml and OmegaConf's YAML loader do (YAML 1.2 calls it an error; RFC 8259 says names SHOULD be unique): a `construct_mapping` override on the YAML loader, an `object_pairs_hook` on every JSON decode.
A pair YAML's `<<` merges in is no duplicate: `_yaml_loader`'s `flatten_mapping` already keeps one per key, the mapping's own winning, as YAML's merge says.

Origin: latent since PR-5, the initial version, which read YAML by `yaml.safe_load` and JSON by `json.load`; both keep the last of a key, and no later revision checked a mapping's own keys.

```python
import tempfile
from dataclasses import dataclass
from pathlib import Path

import confarg


@dataclass
class C:
    s: str = ""


d = Path(tempfile.mkdtemp())
(d / "c.yaml").write_text("s: a\ns: b\n")
(d / "c.json").write_text('{"s": "a", "s": "b"}')
for name in ("c.yaml", "c.json"):
    print(confarg.load(C, argv=["--config", str(d / name)], env={}))
# expected: an InvalidConfigFileError naming the key 's' spelled twice in each file
# actual:   C(s='b')
#           C(s='b')
```
