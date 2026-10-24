# Generics

> [!TIP]
> Code for examples on this page can be found in [`examples/5_generics`](https://github.com/confarg/confarg/tree/master/examples/5_generics).

Confarg handles the following built-in generics.

## `Literal`

The `Literal` generic type allows you to limit inputs to a fixed set of options.
For example, this configuration

<!-- snippet: literal.py#Config -->
```python
@dataclass
class Config:
    input: Literal["hello", "world"]
```

limits the set of possible values of `input` to `"hello"` or `"world"`.

```console
$ uv run literal.py --input hello
Config(input='hello')
$ uv run literal.py --input bye  # Error: not in the set of allowed values
...
```

## `Annotated`

The `Annotated` generic type allows you to attach various metadata to a type.
Confarg can handle `Annotated` types but ignores any metadata attached to them.

```console
$ uv run annotated.py --input hello
Config(input='hello')
```

## `Final`

The `Final` generic type signals that the annotated value should not be changed.
However, it can be set to any value, even if it comes with a default value, which can be surprising.

Take this configuration:

<!-- snippet: final.py#Config -->
```python
@dataclass
class Config:
    final: Final[str] = "hello"
```

The `final` value can be set to a string that is not the default value:

```console
$ uv run final.py --final bye
Config(final='bye')
```

This is consistent with the fact that a `Final` value may not have a default value at all.

> [!TIP]
> A truly predefined and immutable value should probably not be part of the configuration.

## Your own generic classes

A class of your own may be generic too.
Each field reads its type with the class's type parameters bound, as a type checker reads it:

<!-- snippet: generic_class.py#Box -->
```python
@dataclass
class Box[T]:
    """A box holding one item of any type."""

    item: T
```

<!-- snippet: generic_class.py#Config -->
```python
@dataclass
class Config:
    """Configuration with two boxes, each holding its own type."""

    size: Box[int]
    label: Box[str]
```

`size.item` is an `int` and `label.item` a `str`, on the command line, in an environment variable and in a configuration file alike:

```console
$ uv run generic_class.py --size.item 3 --label.item 3
Config(size=Box(item=3), label=Box(item='3'))
$ uv run generic_class.py --size.item x --label.item 3  # Error: a Box[int] holds an int
...
```

<!--
```console
$ uv run generic_class_argparse.py --size.item 3 --label.item 3
Config(size=Box(item=3), label=Box(item='3'))
$ uv run generic_class_argparse.py --size.item x --label.item 3  # Error: a Box[int] holds an int
...
```
-->
<!--
```console
$ uv run generic_class_click.py --size.item 3 --label.item 3
Config(size=Box(item=3), label=Box(item='3'))
$ uv run generic_class_click.py --size.item x --label.item 3  # Error: a Box[int] holds an int
...
```
-->
<!--
```console
$ uv run generic_class_cyclopts.py --size.item 3 --label.item 3
Config(size=Box(item=3), label=Box(item='3'))
$ uv run generic_class_cyclopts.py --size.item x --label.item 3  # Error: a Box[int] holds an int
...
```
-->
<!--
```console
$ uv run generic_class_typer.py --size.item 3 --label.item 3
Config(size=Box(item=3), label=Box(item='3'))
$ uv run generic_class_typer.py --size.item x --label.item 3  # Error: a Box[int] holds an int
...
```
-->

A generic class annotated without its arguments, a bare `Box`, reads `T` as a type checker does: its default where it declares one (`class Box[T = int]`, Python 3.13 and later), else `Any`, which keeps a value as it is written.
A subclass that fixes the argument, `class IntBox(Box[int])`, reads its `item` as an `int` wherever it is used.
