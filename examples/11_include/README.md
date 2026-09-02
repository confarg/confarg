# Referencing other configuration files

> [!TIP]
> Code for examples in this page can be found in [`examples/11_include`](https://github.com/confarg/confarg/tree/master/examples/11_include).

In [Tutorial #10](https://confarg.github.io/confarg/examples/10_nested_configurations/), we saw that we can refer to different configuration files from the command line by repeating the `--config` argument, that those configuration files can be partial, and that sub-configuration files can be loaded at a specific key by using the `--config.path.to.key` syntax.

A similar machinery exists within configuration files, and relies on the `__include__` keyword. This instructs confarg to load another configuration file, either globally or at a given key. `__include__` is followed by the relative path of the config to load; the path is relative to the configuration file.

Let's get back to our earlier example for illustration. We have an app-level configuration that relies on a database configuration, and a log level, and we want to reuse existing standalone database configuration files.

```python
@dataclass
class Config:
    db: DBBaseConfig
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

Rather than stitching the configuration files from the command line as in [Tutorial #10](https://confarg.github.io/confarg/examples/10_nested_configurations/), we now `__include__` our database configuration within our global, app-level configuration file.

```yaml
db:
  __include__: ./postgres.json
log_level: DEBUG
```

Note that the included configuration file may be of any type accepted by confarg. Here, we included a JSON database configuration file within our YAML global configuration file.

## Ordering

In [Tutorial #10](https://confarg.github.io/confarg/examples/10_nested_configurations/), we saw how the order of the configuration files on the command line matters, the later taking precedence over the former.

However, key ordering does not matter in the standard file formats (JSON, TOML, YAML). Therefore, the position of the `__include__` entry relative to the other keys does not matter, and it always have a lower priority.

For example, if a configuration file contains the value `1`, and a new configuration file contains the value `42`, it does not matter whether the former configuration file is included before or after the declaration of the new value: the result is always 42

```console
$ uv run int_value.py --config value.yaml
Config(value=1)
$ uv run int_value.py --config insert_before.yaml
Config(value=42)
$ uv run int_value.py --config insert_after.yaml
Config(value=42)
```

However, an `__include__` may specify a list of configurations, in which case the usual precedence takes place.

```yaml
# include_list1.yaml
__include__: [./value.yaml, ./other_value.yaml]

# include_list2.yaml
__include__: [./other_value.yaml, ./value.yaml]
```

```console
$ uv run int_value.py --config include_list1.yaml
Config(value=2)
$ uv run int_value.py --config include_list2.yaml
Config(value=1)
```
