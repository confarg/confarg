# Variable scopes

> [!TIP]
> Code for examples in this page can be found in [`examples/22_variable_scopes`](https://github.com/confarg/confarg/tree/master/examples/22_variable_scopes).

## Local scope by default

In [Tutorial #21](https://confarg.github.io/confarg/examples/21_expressions/) we wrote expressions that refer to other values by their path. In [Tutorial #11](https://confarg.github.io/confarg/examples/11_include/) we saw that a configuration file can be loaded at any key, with the `__include__` keyword in config files or `--config.path.to.key` command line parameters.

To make those two behavior compatible, the variable path used in expressions in configuration paths are local paths.

To illustrate this, let's reuse our examples of [Tutorial #21](https://confarg.github.io/confarg/examples/21_expressions/) and nest the two-float configuration within a deeper configuration.


```python
@dataclass
class SubConfig:  # Our earlier configuration...
  value1: float
  value2: float

@dataclass
class Config:
  value: float
  values: SubConfig  # ... is now under the `values` key
```

Our [`config1.yaml`](https://github.com/confarg/confarg/tree/master/examples/21_expressions/config1.yaml) configuration used an expression to deduce `value2` from `value1` like so:

```yaml
# config1.yaml
value1: 3.0
value2: ${value1 * 1.5}
```

Say we have a root configuration like so:

```yaml
# top_value.yaml
value: 5.0
```

Bringing our old `config1.yaml` under its new `values` key worth without thinking about it.

```console
$ uv run nested_floats.py --config top_value.yaml --config.values config1.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=4.5))
```

However, this has a deep meaning: variable path in expressions are relative to their current file, *not* to the global configuration.

Consider for example that to use the same value in an expression from the top config file, the full path to the value must be used:

```yaml
# top_value_expression.yaml
value: ${values.value1 + 2}
```

```console
$ uv run nested_floats.py --config top_value_expression.yaml --config.values config1.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=4.5))
```

> [!NOTE]
> The exact same behavior would be obtained with `__include__` in configuration files instead of `--config.<key-path>` command-line arguments.


Expressions provided by the environment or command line parameters sit at the top level and must use the full path of variables, even when they refer to nested keys.

```console
$ # Error: value1 is not found from the CLI, even for expressions on value2
$ uv run nested_floats.py --config nested_floats1.yaml --values.value2 '${value1 * 2.0}'
...
$ # OK: the full path of value1 is used.
$ uv run nested_floats.py --config nested_floats1.yaml --values.value2 '${values.value1 * 2.0}'
Config(value=5.0, values=SubConfig(value1=3.0, value2=6.0))
```

## Referring to the whole configuration

While preserving perfect encapsulation is a desirable goal, in practice a configuration file could need to refer to values defined outside of its scope. This allows big interdependent configurations to be split into manageable components.

To allow for this use case, confarg relies on dot-paths, paths with a dot prefix, to denote global path that are defined down from the top configuration.

In our example, the nested configuration can reach for the top `value` using a dot-path. Note that dot-paths and standard (local) paths can be mixed within the same expression.

```yaml
# config2.yaml
value1: 3.0
value2: ${.value + value1 * 1.5}
```

```console
$ uv run nested_floats.py --config top_value.yaml --config.values config2.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=9.5))
```


Note that this file is no longer standalone: it knows of context that lies outside of its scope. Reusability of such configuration files is affected.

## Saving a configuration

When saving the configuration, expressions are resolved against the assembled configuration, as local path to that global configuration:

```console
$ uv run nested_floats.py --config top_value_expression.yaml --config.values config2.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=9.5))
```

```yaml
# saved_config_uninterpolated.yaml
value: ${values.value1 + 2}
values:
  value1: 3.0
  value2: ${value + values.value1 * 1.5}
```

Saving the constructed object instead writes the resolved values, with no expressions left at all:

```yaml
# saved_config_interpolated.yaml
value: 5.0
values:
  value1: 3.0
  value2: 9.5
```
