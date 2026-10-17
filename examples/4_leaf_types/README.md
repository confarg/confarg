# Leaf types

> [!TIP]
> Code for examples on this page can be found in [`examples/4_leaf_types`](https://github.com/confarg/confarg/tree/master/examples/4_leaf_types).

Leaf types are concrete types that can be defined by a single dictionary or collection entry of the configuration.
They include scalar types, but they are not limited to them.

## `Enum`

You can pass either the key or the value of the desired entry to define an enum argument.

```console
$ uv run enum_value.py --value FOO
Config(value=<Value.FOO: 1>)
$ uv run enum_value.py --value 2
Config(value=<Value.BAR: 2>)
```

> [!NOTE] _Nitpicker's corner_
> The argument is first matched against the key, then the value.
> You don't need to know this unless you are dealing with an enum whose keys and values are inconsistent — let's hope you don't.

## `Path`

The `Path` class is treated as a leaf type in confarg.
A value of type `Path` is directly constructed from a string.

<!-- pytest-markdown-console: notest -->
```console
$ uv run path_value.py --value /foo/bar.txt
Config(value=Path('/foo/bar.txt'))
```

## `Decimal` and `UUID`

`Decimal` and `UUID` are leaf types too, each constructed from its text.

<!-- snippet: decimal_value.py#Config -->
```python
@dataclass
class Config:
    price: Decimal
    id: UUID
```

```console
$ uv run decimal_value.py --price 1.10 --id 12345678-1234-5678-1234-567812345678
Config(price=Decimal('1.10'), id=UUID('12345678-1234-5678-1234-567812345678'))
```

A number in a configuration file is read as it is written, so `price: 1.1` is `Decimal('1.1')`, not the binary expansion of the float the file's parser produced.

## Dates, times and durations

`date`, `datetime`, `time`, `timedelta` and `timezone` are leaf types too, each written as ISO 8601 text.

<!-- snippet: dates.py#Config -->
```python
@dataclass
class Config:
    day: date
    start: datetime
    every: timedelta
```

```console
$ uv run dates.py --day 2021-02-03 --start 2021-02-03T10:00+02:00 --every PT1H30M
Config(day=datetime.date(2021, 2, 3), start=datetime.datetime(2021, 2, 3, 10, 0, tzinfo=datetime.timezone(datetime.timedelta(seconds=7200))), every=datetime.timedelta(seconds=5400))
{'day': '2021-02-03', 'start': '2021-02-03T10:00:00+02:00', 'every': 'PT1H30M'}
```

A date, a datetime and a time read whatever their `fromisoformat` reads, and an offset is kept as written.
A duration is an ISO 8601 duration in days, hours, minutes and seconds (`PT1H30M`, `P1DT12H`, `-PT30S`, weeks too); a bare number is refused, since it carries no unit.
A timezone is a UTC offset, `+02:00` or `Z`.

YAML and TOML files hold dates natively, and a date there is read as its text would be: `start: 2021-02-03` is that day's midnight for a `datetime`, and a `datetime` is refused for a `date`, as on the command line.
Quote a time of day in YAML: YAML reads an unquoted `10:20` as the number 620, which the error points out.

`dump()` writes each as its ISO text, as above, so its output suits any file format.
`dump_file()` writes dates and datetimes as the native dates of a YAML or TOML file, and `confarg.dump(config, native_types=confarg.YAML_NATIVE_TYPES)` does the same for a YAML writer of your own.

## Types

Types can be specified as leaf types.
Take this configuration:

<!-- snippet: type.py#Config -->
```python
@dataclass
class Config:
    value: type
```

You can pass a built-in type, or any other type by its fully-qualified dotted path.

```console
$ uv run type.py --value int
Config(value=<class 'int'>)
$ uv run type.py --value __main__.Config
Config(value=<class '__main__.Config'>)
```

When a class is specified, this class or any class that derives from it can be passed.

Let's modify our configuration:

<!-- snippet: base_class.py#Config -->
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

Callables are also accepted as a special kind of leaf type.
However, they are more involved than other leaf types, and we will spend four tutorials to go in depth into them in [Tutorial #18](https://confarg.github.io/confarg/examples/18_callables/), [Tutorial #19](https://confarg.github.io/confarg/examples/19_bindings/), [Tutorial #20](https://confarg.github.io/confarg/examples/20_factories/), and [Tutorial #21](https://confarg.github.io/confarg/examples/21_calls/).

## Custom leaf types

Confarg allows you to register custom leaf types via the [`confarg.register_leaf_type`](https://confarg.github.io/confarg/reference/#confarg.register_leaf_type) function.
This can help make configurations simpler to read and write.

Say we have a custom `Int` class that supports `NaN` values and that we want to treat as a leaf type.
We write a custom coercion function:

<!-- snippet: custom_leaf_type.py#coerce_int -->
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

Without leaf type registration, initializing a custom `Int` would require an init dict (`--input.value 42`) that would make its initialization different from that of plain integers.

### Writing the value back

Registration makes `Int` a leaf in both directions: [`confarg.dump`](https://confarg.github.io/confarg/reference/#confarg.dump) and [`confarg.dump_file`](https://confarg.github.io/confarg/reference/#confarg.dump_file) write it as a single scalar rather than as an init dict.
How that scalar is spelled is decided by the `serialize` argument, the inverse of `coerce`:

<!-- snippet: custom_leaf_type.py#serialize_int -->
```python
def serialize_int(value: Int) -> str | int:
    return "NaN" if value.value is None else value.value
```

Registration then takes the coercion and the serializer together:

```python
confarg.register_leaf_type(Int, coerce_int, serialize=serialize_int)
```

`serialize` defaults to `str`, which is the wire form of types like `IPv4Address`.
Our `Int` is not one of them — `str(Int(42))` is the debugging form `Int(value=42)`, which `coerce_int` would refuse on the way back in — so we pass an explicit serializer, and a dumped configuration loads again unchanged.
