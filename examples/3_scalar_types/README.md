# Scalar types

> [!TIP]
> Code for examples in this page can be found in [`examples/3_scalar_types`](https://github.com/confarg/confarg/tree/master/examples/3_scalar_types).


Scalar types are the well-known type quintuplet (`int`, `float`, `bool`, `str`, `None`) that are the building blocks of any configuration. However, arguments in configuration files, environment variables, or command-line arguments are all strings by nature.

In configuration files, the coercion into scalar types is handled by the file format. Typically, strings are quoted, while other scalar types are not, which enables to distinguish easily the string `"1"` from the number `1`. Refer to the specification of your favorite configuration file format for more details.

For environment variables and command-line arguments however, for practical reasons and out of habit, the convention is to rely on knowledge of the target type. Look at how the same string argument `"1"` is interpreted depending on the target type.

```console
$ uv run str_value.py --value 1
Config(value='1')
$ uv run int_value.py --value 1
Config(value=1)
$ uv run float_value.py --value 1
Config(value=1.0)
$ uv run bool_value.py --value1 1 --value2 0
Config(value1=True, value2=False)
```

This should not be too surprising to anyone used to CLIs. Let's review in more detail some specific coercion rules for scalar types in confarg.

## Coercion to `float`

Floats can be declared in an array of standard representations.

```console
$ # Decimal representation
$ uv run float_value.py --value 1.5
Config(value=1.5)
$ # Note that the leading 0 can be omitted
$ uv run float_value.py --value .5
Config(value=0.5)
$ # Scientific notation is also fine
$ uv run float_value.py --value -1.5e-2
Config(value=-0.015)
```

Integer strings are coerced into floats.

```console
$ uv run float_value.py --value 1
Config(value=1.0)
```

Finally, `inf` and `nan` are also handled.

```console
$ uv run float_value.py --value nan
Config(value=nan)
$ uv run float_value.py --value -inf
Config(value=-inf)
```

## Coercion to `int`

Integers are also coerced in a standard fashion, handling a variety of non-decimal representations.

```console
$ # Decimal representation
$ uv run int_value.py --value 42
Config(value=42)
$ # Hexadecimal representation
$ uv run int_value.py --value 0xFF
Config(value=255)
$ # Octal representation
$ uv run int_value.py --value -0o20
Config(value=-16)
$ # Binary representation
$ uv run int_value.py --value 0b110
Config(value=6)
```

## Coercion to `bool`

The coercion of booleans is consistent between environment variables, command-line arguments, and configuration files.

```console
$ uv run bool_value.py --value1 true --value2 false
Config(value1=True, value2=False)
$ uv run bool_value.py --value1 on --value2 off
Config(value1=True, value2=False)
$ uv run bool_value.py --value1 yes --value2 no
Config(value1=True, value2=False)
$ uv run bool_value.py --value1 1 --value2 0
Config(value1=True, value2=False)
```

So in some sense, there is nothing special about them, yet the way confarg specifies them on the command line departs from the convention used by `argparse` and most CLI libraries.

```console
$ # Error: The `--flag` syntax does not work, confarg is expecting a value
$ uv run bool_value.py --value1
...
confarg.exceptions.ConfargError: Missing value for '--value1'. Usage: --value1 <value>
$ # Error: The `--no-flag` syntax does not work either, this parameter is unknown to confarg.
$ uv run bool_value.py --no-value1
...
confarg.exceptions.UnknownArgumentError: Unknown argument: --no-value1 (field 'no-value1' not found)
```


> [!IMPORTANT]
> Boolean flags on the command line are explicitly set to a boolean value as in the examples above, for example by using `--flag true` or `--flag false`. Using `--flag` or `--no-flag`, as seen in other libraries, will raise an error.

On top of being consistent with environment variables and configuration files, we will see later why this helps us in disambiguation scenarios.

## Coercion to `None`

The value can be set to `None` using the string `none` or `null`. As for booleans, the value must be explicitly set.

```console
$ uv run none_value.py --value none
Config(value=None)
$ uv run none_value.py --value null
Config(value=None)
```

## Coercion of `str`

When the target type is a string, no coercion is done at all.

```console
$ uv run str_value.py --value foo
Config(value='foo')
$ uv run str_value.py --value 1
Config(value='1')
$ uv run str_value.py --value inf
Config(value='inf')
$ uv run str_value.py --value none
Config(value='none')
```
