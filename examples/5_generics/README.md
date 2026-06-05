# Generics

> [!TIP]
> Code for examples in this page can be found in [`examples/5_generics`](https://github.com/confarg/confarg/tree/master/examples/5_generics).


Confarg handles the following built-in generics.

## `Literal`

The `Literal` generic type allows you to limit inputs to a fixed set of options. For example, this configuration

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

The `Annotated` generic type allows you to attach various metadata to a type. Confarg can handle `Annotated` types but ignores any metadata attached to it.

```console
$ uv run annotated.py --input hello
Config(input='hello')
```

## `Final`

The `Final` generic type signals that the annotated value should not be changed. However, it can be set to any value, even if it comes with a default value, which can be surprising.

Take this configuration:

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
