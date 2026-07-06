# JSON inputs

> [!TIP]
> Code for examples in this page can be found in [`examples/14_json`](https://github.com/confarg/confarg/tree/master/examples/14_json).


JSON strings can be used in environment variables and from the command line where either a sequence or a structured input is expected.

<!-- pytest-markdown-console: platform:!win32 -->
```console
$ # Passing individual leaf values
$ uv run myapp.py --db.class configs.SQLiteConfigChild --db.dbpath db.sqlite
Config(db=SQLiteConfigChild(dbpath='db.sqlite'))
$ # Passing the entire db dictionary as inline JSON
$ uv run myapp.py --db '{"class": "configs.SQLiteConfigChild", "dbpath": "db.sqlite"}'
Config(db=SQLiteConfigChild(dbpath='db.sqlite'))
```

The JSON syntax can feel clunky to type manually on the command line, and standard command-line arguments are generally preferred. However, JSON can be generated easily, so the ability to apply JSON patches can be handy.

Also, while more verbose, JSON has the merit of being unambiguous about its argument types, which lets us fill in values that cannot be filled in natively.

Consider the following configuration:

```python
@dataclass
class Config:
    input: list[str | bool]
```

As per the stealing rule, explained in [Tutorial #7](https://confarg.github.io/confarg/examples/7_stealing_rule/), any string that can be coerced into a boolean will be.

```console
$ uv run list_of_str_or_bools.py --input hello yes well
Config(input=['hello', True, 'well'])
```

We can override the stealing rule, as seen in this tutorial, but this can be awkward in sequences as we need to address the individual item.

```console
$ uv run list_of_str_or_bools.py --input.0 hello --input.1.str yes --input.2 well
Config(input=['hello', 'yes', 'well'])
```

Using a JSON input allows us to provide the desired types.

```console
$ uv run list_of_str_or_bools.py --input '["hello", "yes", "well"]'
Config(input=['hello', 'yes', 'well'])
```


## Forcing JSON coercion

Whether a value is read as JSON is normally decided implicitly, from the field's type: a `{...}` or `[...]` value is only decoded when the target field can hold a structured or sequence value. To make the intent explicit, or to reach a field the implicit rule does not cover, such as an `Any`-typed one, append a `json` suffix to the key, mirroring the `.str`/`.int`/`.float`/`.bool` scalar casts from [Tutorial #7](https://confarg.github.io/confarg/examples/7_stealing_rule/).

<!-- pytest-markdown-console: platform:!win32 -->
```console
$ # Force the whole db field to be read as JSON
$ uv run myapp.py --db.json '{"class": "configs.SQLiteConfigChild", "dbpath": "db.sqlite"}'
Config(db=SQLiteConfigChild(dbpath='db.sqlite'))
```

The same suffix works on environment variables, appended as the last path segment:

<!-- pytest-markdown-console: platform:!win32 -->
```console
$ MYAPP_DB__json='{"class": "configs.SQLiteConfigChild", "dbpath": "env.sqlite"}' uv run myapp.py
Config(db=SQLiteConfigChild(dbpath='env.sqlite'))
```

## On Windows

Typing JSON arguments on Windows is particularly clunky. The command prompt (`cmd.exe`) does not treat single quotes as a quoting character; double quotes must be used. Consequently, all double quotes needed inside the JSON argument must be escaped:

<!-- pytest-markdown-console: notest -->
```
$ # In the command prompt
$ uv run .\list_of_strs.py --input "[\"a\", \"b\"]"
```

In PowerShell, single quotes can be used as a quoting character but double quotes still must be escaped.

<!-- pytest-markdown-console: notest -->
```
$ # In PowerShell
$ uv run .\list_of_strs.py --input '[\"a\", \"b\"]'
```
