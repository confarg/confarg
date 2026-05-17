# Leaf types

> [!TIP]
> Code for examples in this page can be found in [`examples/4_leaf_types`](https://github.com/confarg/confarg/tree/master/examples/4_leaf_types).


Leaf types are concrete types that can be defined by a single dictionary or collection entry of the configuration. They include scalar types, but they are not limited to them.


## `Enum`

You can either pass the key or the value of the desired entry to define an enum argument.

```console
$ uv run enum_value.py --value FOO
Config(value=<Value.FOO: 1>)
$ uv run enum_value.py --value 2
Config(value=<Value.BAR: 2>)
```


## `Path`

The `Path` class is treated as a leaf type in confarg. A value of type `Path` is directly constructed from a string.

<!-- pytest-markdown-console: notest -->
```console
$ uv run path_value.py --value /foo/bar.txt
Config(value=Path('/foo/bar.txt'))
```


## Custom leaf types

Confarg allows you to register custom leaf types via the [`confarg.register_leaf_type`](https://confarg.github.io/confarg/reference/#confarg.register_leaf_type) function. This can help making configurations simpler to read and write.

Say we have a custom `Int` class that supports `NaN` values and that we want to treat as a leaf type. We write a custom coercion function:

```python
def coerce_int(value: str) -> Int:
    return Int(None if value == "NaN" else int(value))
```

and register this coercion with confarg:

```python
confarg.register_leaf_type(Int, coerce_int)
```

The `Int` type can now be used as a leaf type, just like the regular `int` type.

```console
$ uv run custom_leaf_type.py --input 42
Config(input=Int(value=42))
$ uv run custom_leaf_type.py --input NaN
Config(input=Int(value=None))
```

Without leaf type registration, initializing a custom `Int` would require an init dict (`--input.value 42`) that would make their initialization different from plain integers.
