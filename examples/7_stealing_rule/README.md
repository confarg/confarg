# Leaf type unions and the stealing rule

> [!TIP]

Now that we have learned in [Tutorial #6](https://confarg.github.io/confarg/examples/6_unions/) how confarg can handle unions, we need to go back to leaf types and talk about the stealing rule, that is, the precedence of leaf types in unions. It matters most for inputs provided as CLI arguments or environment variables, which are plain text, but it applies to configuration files too, as we will see [at the end of this page](#values-from-configuration-files).

For plain leaf types, we saw how confarg relies on the target type to understand how to coerce input strings provided from the command line or the environment. However, type unions make the whole process ambiguous, in particular when one of the union variants is `str`.

Confarg relies on the following priority order to resolve leaf type arguments, called the stealing rule:

```
Custom leaf type > Enum > [type, Literal] > [float, int, bool, None] > str
```

That is, in case of a union between those types, the coercion is done in this order, and the first successful coercion wins. This means for example that the scalar coercions we saw in [Tutorial #6](https://confarg.github.io/confarg/examples/6_unions/) work in unions and have a higher priority over keeping the input as a string.

```console
$ # "none" gets coerced into `None` for target type `str | None`
$ uv run str_or_none.py --input none
Config(input=None)
$ # "inf" gets coerced into `inf` for target type `str | float`
$ uv run str_or_float.py --input inf
Config(input=inf)
$ # "no" gets coerced into `False` for target type `str | bool`
$ uv run str_or_bool.py --input no
Config(input=False)
$ # "int" gets coerced into type `int` for target type `str | type`
$ uv run str_or_type.py --value int
Config(value=<class 'int'>)
```

> [!NOTE]
> This last example is not an instance of the [Norway problem](https://hitchdev.com/strictyaml/why/implicit-typing-removed/), as this coercion happens only if `bool` is one of the expected types.


## Overriding the stealing rule

For the cases where you need to override coercion precedence, for example, to set the `"null"` string to a `str | None` entry, you can force the coercion to `str` by appending `.str` to the key path.

```console
$ # Stealing rule applies: `"yes"` is converted to True
$ uv run str_or_bool.py --input yes
Config(input=True)
$ # Override the stealing rule and force coercion to `str`: `"yes"` string is preserved
$ uv run str_or_bool.py --input.str yes
Config(input='yes')
```

The override also works in case of a union with an enumeration. As we saw in [Tutorial #4](https://confarg.github.io/confarg/examples/6_unions/), an enumeration can be specified by either its key or its value, both of which may steal the value from a scalar type in a union. Take this enumeration again:

```python
class Value(Enum):
    FOO = 1
    BAR = 2
```

In a union with a string, the key takes precedence:

```console
$ uv run enum_or_str.py --input FOO
Config(input=<Value.FOO: 1>)
```

Using the `.str` type suffix on the CLI argument forces the coercion to string.

```console
$ uv run enum_or_str.py --input.str FOO
Config(input='FOO')
```

This works similarly on the enumeration value, using an `.int` suffix to force the coercion of the input to `int`.

```console
$ # Enum has higher precedence than `int`
$ uv run enum_or_int.py --input 2
Config(input=<Value.BAR: 2>)
$ # input is explicitly coerced to `int`
$ uv run enum_or_int.py --input.int 2
Config(input=2)
```

## Values from configuration files

A configuration file is self-describing: its values already have a type, so confarg never converts a string from a file into a number, a boolean or `None`. A file's `inf` stays a string for `str | float`, where the same text on the command line is the float infinity:

<!-- snippet: str_or_float.yaml -->
```yaml title="str_or_float.yaml"
input: inf
```

```console
$ uv run str_or_float.py --config str_or_float.yaml
Config(input='inf')
```

A file's value is still *recognized* by the variants that name it, in the same priority order: an enumeration's key or value, a class path for a `type`, a `Literal` member, a custom leaf type. The order the union is written in does not matter, for a file no more than for the command line:

<!-- snippet: enum_or_str.yaml -->
```yaml title="enum_or_str.yaml"
input: FOO
```

```console
$ uv run enum_or_str.py --config enum_or_str.yaml
Config(input=<Value.FOO: 1>)
```

The file's way to override the stealing rule is a `__cast__`, the counterpart of the `.str` suffix:

<!-- snippet: enum_or_str_cast.yaml -->
```yaml title="enum_or_str_cast.yaml"
input:
  __cast__: str
  __value__: FOO
```

```console
$ uv run enum_or_str.py --config enum_or_str_cast.yaml
Config(input='FOO')
```

`confarg.dump()` writes that `__cast__` on its own wherever the plain value would be recognized as another variant, so a dumped configuration always loads back as the same object.
