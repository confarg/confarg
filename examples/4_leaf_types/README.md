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

> [!NOTE] *Nitpicker's corner*
> The argument is first matched against the key, then the value. You don't need to know this unless you are dealing with an enum whose keys and values are inconsistent — let's hope your don't.


## `Path`

The `Path` class is treated as a leaf type in confarg. A value of type `Path` is directly constructed from a string.

<!-- pytest-markdown-console: notest -->
```console
$ uv run path_value.py --value /foo/bar.txt
Config(value=Path('/foo/bar.txt'))
```

## Types

Types can be specified as leaf types. Take this configuration:

```python
@dataclass
class Config:
    value: type
```

You can pass a builtin type, or any other type by its fully-qualified dotted path.

```console
$ uv run type.py --value int
Config(value=<class 'int'>)
$ uv run type.py --value __main__.Config
Config(value=<class '__main__.Config'>)
```

When a class is specified, this class or any class that derives from it can be passed.

Let modify our configuration:

```python
@dataclass
class Config:
    value: type[BaseClass]
```

```console
$ # BaseClass can be passed
$ uv run base_class.py --value __main__.BaseClass
Config(value=<class '__main__.BaseClass'>)
$ # A derived class can also be passed
$ uv run base_class.py --value __main__.DerivedClass
Config(value=<class '__main__.DerivedClass'>)
$ # Error: a type that is not derived from BaseClass gets rejected
$ uv run base_class.py --value __main__.UnrelatedClass
...
```

## Callables

Callables are also accepted as a special kind of leaf type. However, there are more involved than other leaf types, and we will spend three tutorials to go in depth into them in [Tutorial #18](https://confarg.github.io/confarg/examples/18_callables/), [Tutorial #19](https://confarg.github.io/confarg/examples/19_bindings/) and [Tutorial #20](https://confarg.github.io/confarg/examples/20_factories/).

## Custom leaf types

Confarg allows you to register custom leaf types via the [`confarg.register_leaf_type`](https://confarg.github.io/confarg/reference/#confarg.register_leaf_type) function. This can help make configurations simpler to read and write.

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

Without leaf type registration, initializing a custom `Int` would require an init dict (`--input.value 42`) that would make its initialization different from plain integers.
