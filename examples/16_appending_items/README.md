# Appending items to lists

> [!TIP]
> Code for examples in this page can be found in [`examples/16_appending_items`](https://github.com/confarg/confarg/tree/master/examples/16_appending_items).

New elements can be appended to lists by postfixing the list key with a `+`.

## From the CLI

From the CLI, a leaf element can be added like so:

```console
$ uv run list_of_ints.py --config pair_of_ints.yaml
Config(input=[1, 2])
$ # Append a single element
$ uv run list_of_ints.py --config pair_of_ints.yaml --input+ 42
Config(input=[1, 2, 42])
$ # Append several elements
$ uv run list_of_ints.py --config pair_of_ints.yaml --input+ 42 -0o10
Config(input=[1, 2, 42, -8])
$ # Append an empty list (no effet)
$ uv run list_of_ints.py --config pair_of_ints.yaml --input+
Config(input=[1, 2])
```

When the items to be appended is more elaborate than a simple leaf node, inputs can be provided as JSON strings, as we just saw in [Tutorial 15](https://confarg.github.io/confarg/examples/15_json_inputs/).

<!-- pytest-markdown-console: platform:!win32 -->
```console
$ # Appending a new SQLite configuration
$ uv run myapp.py --dbs+ '{"class": "configs.SQLiteConfigChild", "dbpath": "otherdb.sqlite"}'
Config(dbs=[SQLiteConfigChild(dbpath='otherdb.sqlite')])
```

Note that you can append more than one element. You can either append several JSON objects, or extend with a list of JSON objects.

<!-- pytest-markdown-console: platform:!win32 -->
```console
$ # Two ways to reach the same goal:
$ # 1. Append several JSON objects
$ uv run simple.py --dbs+ '{"dbpath": "db1.sqlite"}' '{"dbpath": "db2.sqlite"}'
Config(dbs=[SQLiteConfig(dbpath='db1.sqlite'),
            SQLiteConfig(dbpath='db2.sqlite')])
$ # 2. Extend with a JSON list of objects
$ uv run simple.py --dbs+ '[{"dbpath": "db1.sqlite"},{"dbpath": "db2.sqlite"}]'
Config(dbs=[SQLiteConfig(dbpath='db1.sqlite'),
            SQLiteConfig(dbpath='db2.sqlite')])
```

An alternative to using JSON to add objects is to first append an empty dictionary, and then fill it with standard arguments. This is easier to write manually and can benefit from tab-completion.

```console
$ uv run simple.py --dbs+ "{}" --dbs.-1.dbpath db1.sqlite --dbs+ "{}" --dbs.-1.dbpath db2.sqlite
Config(dbs=[SQLiteConfig(dbpath='db1.sqlite'),
            SQLiteConfig(dbpath='db2.sqlite')])
```

## In configuration files

The same `+` suffix works on keys config files. A derived config can append to a list from a base config without touching the rest of the structure. For example, take this configuration file:

```yaml
# more_ints.yaml
input+: [42]
```

It can be used to append ints to an existing configuration.

```console
$ uv run list_of_ints.py --config pair_of_ints.yaml
Config(input=[1, 2])
$ # Apply the appending config
$ uv run list_of_ints.py --config pair_of_ints.yaml more_ints.yaml
Config(input=[1, 2, 42])
```

Sub-configuration files can also be appended:

```console
$ uv run myapp.py --config config.yaml
Config(dbs=[PostgreSQLConfigChild(host='example.com',
                                  port=5432,
                                  schema_name='mydb')])
$ uv run myapp.py --config config.yaml --config.dbs+ other_sqlite.yaml
Config(dbs=[PostgreSQLConfigChild(host='example.com',
                                  port=5432,
                                  schema_name='mydb'),
            SQLiteConfigChild(dbpath='db.sqlite')])
```

> [!NOTE]
> TOML bare keys are restricted to `A-Za-z0-9_-`, so the `+` suffix requires a quoted key:
>
> ```toml
> # more_ints.toml
> "inputs+" = [42]
> ```
