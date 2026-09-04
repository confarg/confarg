# Expressions and variable interpolation

> [!TIP]
> Code for examples in this page can be found in [`examples/20_factories`](https://github.com/confarg/confarg/tree/master/examples/expressions).

confarg can process expressions, which are declared within `${...}`. Those expressions allow to deduce configuration values from other parts of the configuration.

Suppose we have a configuration compose of two floating point values:

```python
@dataclass
class Config:
  value1: float
  value2: float
```

You can set the value of `value2` based on an expression relying on `value1`, for eaxmple

```yaml
# config1.yaml
value1: 3.0
value2: ${value1 * 1.5}
```

```console
$ uv run two_floats.py --config config1.yaml
Config(value1=3.0, value2=4.5)
```

The expression does not need to come after the variable it references. Having `value1` referring to `value2`works too.

```yaml
# config2.yaml
value1: ${value2 * 1.5}
value2: 3.0
```

```console
$ uv run two_floats.py --config config2.yaml
Config(value1=4.5, value2=3.0)
```

It's ok to have expressions relying on variables that are themselves expressions. For example, if we now have three input float values, the following configuration is valid.

```yaml
# config3.yaml
value1: ${value2 * 1.5}
value2: ${value3 * 1.5}
value3: 2.0
```

```console
$ uv run three_floats.py --config config3.yaml
Config(value1=4.5, value2=3.0, value3=2.0)
```

If your chain of expression contains a loop, confarg will complain.

```yaml
# config_with_loop.yaml
value1: ${value2 * 1.5}
value2: ${value3 * 1.5}
value3: ${value1 * 1.5}
```

```console
$ # Error: circular reference
$ uv run three_floats.py --config config_with_loop.yaml
...
```

The expressions can reach across definition boundaries. For example, a configuration file can define `value1`, and we can define `value2` based on a expression over `value1` from the command line.

```yaml
# config4.yaml
value1: 3.0
```

```console
$ uv run two_floats.py --config config4.yaml --value2 '${value1 * 1.5}'
Config(value1=3.0, value2=4.5)
```

The opposite also works: we can define `value1` as an expression of `value2`, which is defined late on the command line.

```yaml
# config5.yaml
value1: ${value2 * 1.5}
```

```console
$ uv run two_floats.py --config config5.yaml --value2 3.0
Config(value1=4.5, value2=3.0)
```

Even if `value2` is already defined in the configuration file, the final value of `value2` is taken into account in the expression.

```console
$ uv run two_floats.py --config config2.yaml
Config(value1=4.5, value2=3.0)
$ uv run two_floats.py --config config2.yaml --value2 6
Config(value1=9.0, value2=6.0)
```
