# Variable scopes

> [!TIP]
> Code for examples on this page can be found in [`examples/23_variable_scopes`](https://github.com/confarg/confarg/tree/master/examples/23_variable_scopes).

## Local scope by default

In [Tutorial #22](https://confarg.github.io/confarg/examples/22_expressions/) we wrote expressions that refer to other values by their path.
In [Tutorial #11](https://confarg.github.io/confarg/examples/11_include/) we saw that a configuration file can be loaded at any key, with the `__include__` keyword in config files or `--config.path.to.key` command line parameters.

To make those two behaviors compatible, the variable paths used in expressions in configuration files are local paths.

To illustrate this, let's reuse our examples of [Tutorial #22](https://confarg.github.io/confarg/examples/22_expressions/) and nest the two-float configuration within a deeper configuration.

<!-- snippet: nested_floats.py#SubConfig -->
```python
@dataclass
class SubConfig:
    value1: float
    value2: float
```

<!-- snippet: nested_floats.py#Config -->
```python
@dataclass
class Config:
    value: float
    values: SubConfig
```

Our [`derived_value2.yaml`](https://github.com/confarg/confarg/tree/master/examples/22_expressions/derived_value2.yaml) configuration used an expression to deduce `value2` from `value1` like so:

<!-- snippet: derived_value2.yaml -->
```yaml title="derived_value2.yaml"
value1: 3.0
value2: ${value1 * 1.5}
```

Say we have a root configuration like so:

<!-- snippet: top_value.yaml -->
```yaml title="top_value.yaml"
value: 5.0
```

Bringing our old `derived_value2.yaml` under its new `values` key works without a second thought.

```console
$ uv run nested_floats.py --config top_value.yaml --config.values derived_value2.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=4.5))
```

However, this has a deep meaning: variable paths in expressions are relative to their current file, _not_ to the global configuration.

Consider for example that to use the same value in an expression from the top config file, the full path to the value must be used:

<!-- snippet: top_value_expression.yaml -->
```yaml title="top_value_expression.yaml"
value: ${values.value1 + 2}
```

```console
$ uv run nested_floats.py --config top_value_expression.yaml --config.values derived_value2.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=4.5))
```

> [!NOTE]
> The exact same behavior would be obtained with `__include__` in configuration files instead of `--config.<key-path>` command-line arguments.

Expressions provided by the environment or command line parameters sit at the top level and must use the full path of variables, even when they refer to nested keys.

```console
$ # Error: value1 is not found from the CLI, even for expressions on value2
$ uv run nested_floats.py --config included_values.yaml --values.value2 '${value1 * 2.0}'
...
$ # OK: the full path of value1 is used.
$ uv run nested_floats.py --config included_values.yaml --values.value2 '${values.value1 * 2.0}'
Config(value=5.0, values=SubConfig(value1=3.0, value2=6.0))
```

## Referring to the whole configuration

While preserving perfect encapsulation is a desirable goal, in practice a configuration file could need to refer to values defined outside of its scope.
This allows big interdependent configurations to be split into manageable components.

To allow for this use case, confarg relies on root-paths — paths with a `::` prefix — to denote global paths that are defined down from the top configuration.

In our example, the nested configuration can reach for the top `value` using a root-path.
Note that root-paths and standard (local) paths can be mixed within the same expression.

<!-- snippet: root_path.yaml -->
```yaml title="root_path.yaml"
value1: 3.0
value2: ${::value + value1 * 1.5}
```

```console
$ uv run nested_floats.py --config top_value.yaml --config.values root_path.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=9.5))
```

Note that this file is no longer standalone: it knows of context that lies outside of its scope.
Reusability of such configuration files is affected.

## Referring to a neighboring value

A path that starts with a dot is relative to the value being written, one level up per dot: `${.other}` is a key beside it, and `${..other}` a key in the block above.
Unlike a root-path it never names a position, so the block it sits in can be renamed, moved or reordered without the expression being touched.

<!-- snippet: relative_paths.yaml -->
```yaml title="relative_paths.yaml"
value: 5.0
values:
  value1: ${..value}
  value2: ${.value1 * 1.5}
```

```console
$ uv run nested_floats.py --config relative_paths.yaml
Config(value=5.0, values=SubConfig(value1=5.0, value2=7.5))
```

`value1` climbs two levels — out of its own key, then out of `values` — to reach the top-level `value`, while `value2` climbs one and finds `value1` beside it.

This is what lets an element of a list describe itself without knowing its index, the one case no other spelling covers:

<!-- snippet: servers.yaml -->
```yaml title="servers.yaml"
servers:
- name: web
  host: web.example.com
  url: https://${.host}/   # this element's own host, wherever it ends up
```

Two rules keep this predictable.
Dots may not climb out of the file that wrote them, so a configuration part stays reusable however deeply it is mounted — reaching outside it is what `::` is for.
And a relative path is saved exactly as written rather than resolved to `${values.value1}`, so a saved configuration is still safe to reorder and re-edit.

## Naming a value after its key

A relative path reads the value at a position.
`key(...)` reads the key that position is filed under instead, which lets an entry of a dictionary take its name from its key rather than writing it twice:

<!-- snippet: named_hosts.py#Host -->
```python
@dataclass
class Host:
    name: str
    port: int
```

<!-- snippet: named_hosts.py#Config -->
```python
@dataclass
class Config:
    hosts: dict[str, Host]
```

<!-- snippet: hosts.yaml -->
```yaml title="hosts.yaml"
hosts:
  web:
    name: ${key(.)}   # the key this entry is filed under
    port: 80
  db:
    name: ${key(.)}
    port: 5432
```

`.` is the entry the expression sits in, so `key(.)` is `web` in the first entry and `db` in the second; `key(..)` would be `hosts`.
Inside a list, the key of an element is its index.

```console
$ uv run named_hosts.py --config hosts.yaml --hosts.cache.name '${key(.)}' --hosts.cache.port 6379
Config(hosts={'cache': Host(name='cache', port=6379),
              'db': Host(name='db', port=5432),
              'web': Host(name='web', port=80)})
```

An entry that writes its own `name` keeps it: `key(.)` is a value like any other, written only where you want it.

## Saving a configuration

When saving the configuration, expressions are resolved against the assembled configuration, as local paths to that global configuration:

```console
$ uv run nested_floats.py --config top_value_expression.yaml --config.values root_path.yaml
Config(value=5.0, values=SubConfig(value1=3.0, value2=9.5))
```

```yaml title="saved_config_uninterpolated.yaml"
value: ${values.value1 + 2}
values:
  value1: 3.0
  value2: ${value + values.value1 * 1.5}
```

Saving the constructed object instead writes the resolved values, with no expressions left at all:

```yaml title="saved_config_interpolated.yaml"
value: 5.0
values:
  value1: 3.0
  value2: 9.5
```
