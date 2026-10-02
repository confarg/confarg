# BUG-51 — A bare `--config.<subpath>+` is an error in vanilla and a no-op in two front-ends

**Where:** `src/confarg/cli/_build.py` (`_collect_config_argv_specs`), `src/confarg/_parse_cli.py`
(`_consume_config_paths`) · **Filed:** 2026-09-28
**Effort:** S · **Risk:** low · **Impact:** behavior

A config-file flag demands a path: vanilla answers `Missing file path after --config` when
`--config.users+` stands with nothing after it, and click and typer reject it too (`Option
'--config.users+' requires an argument.`). argparse and cyclopts accept it silently and mount
nothing, so the same command line is an error on three front-ends and a no-op on two — an
unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

Deciding which answer is right settles it either way: a bare config append could mount no file
the way a bare `--<list>+` appends no item, in which case the flag's specs take
`FlagSpec.stands_bare` and vanilla stops raising; or the error is right, and the two lenient
front-ends have to report it
([04-cli-adapters.md#a-bare-append](../../architecture/04-cli-adapters.md#a-bare-append) explains
why the append flags alone carry the marker today). With a file *and* a bare occurrence
(`--config.users+ extra.yaml --config.users+`), cyclopts additionally hits the implicit-token
assertion described there.

```python
from dataclasses import dataclass, field

import confarg
from confarg.cli.argparse import from_namespace, make_parser


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


ARGV = ["--config.users+"]

parser = make_parser(Config, argv=ARGV)
print("argparse:", from_namespace(Config, parser.parse_args(ARGV), argv=ARGV, env={}, env_prefix=None))
print("vanilla: ", confarg.load(Config, argv=ARGV, env={}, env_prefix=None))
# expected: both front-ends agree
# actual:   argparse: Config(users=[])
#           vanilla:  confarg.exceptions.ConfargError: Missing file path after --config.
#                     Usage: --config /path/to/config.yaml
```
