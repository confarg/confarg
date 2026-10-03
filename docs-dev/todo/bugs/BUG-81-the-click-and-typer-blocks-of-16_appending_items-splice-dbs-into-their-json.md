# BUG-81 — The click and typer blocks of `16_appending_items` splice `--dbs+` into their JSON

**Where:** `examples/16_appending_items/README.md` (the six click/typer console blocks: lines 95, 109, 146, 149, 168, 171) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** low · **Impact:** none

Six console blocks spell their JSON argument with `--dbs+ ` grafted into it
(`'{"dbpath": --dbs+ "db1.sqlite"}'`), where the vanilla/argparse/cyclopts twins spell
`'{"dbpath": "db1.sqlite"}'` — the shape of a find-and-replace that matched the quotes
inside the JSON. The token is no longer JSON, so the append stores it as a string and
`build()` refuses it: the commands fail instead of printing the `Config(dbs=[...])` the
blocks show, so all six replay as failures on any non-win32 platform — CI included, once
the local `wip` revision that introduced them is pushed. Restore the JSON the expected
output already shows (the argparse spelling).

```console
$ cd examples/16_appending_items
$ uv run simple_click.py --dbs+ '{"dbpath": --dbs+ "db1.sqlite"}' --dbs+ '{"dbpath": --dbs+ "db2.sqlite"}'
confarg.exceptions.TypeCoercionError: Cannot construct SQLiteConfig at 'dbs[0]': expected dict, got str '{"dbpath": --dbs+ "db1.sqlite"}'
# expected — the block's own output, which the clean spelling produces:
$ uv run simple_click.py --dbs+ '{"dbpath": "db1.sqlite"}' --dbs+ '{"dbpath": "db2.sqlite"}'
Config(dbs=[SQLiteConfig(dbpath='db1.sqlite'),
            SQLiteConfig(dbpath='db2.sqlite')])
```
