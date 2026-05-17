# Nested configurations

> [!TIP]
> Code for examples in this page can be found in [`examples/10_nested_configurations`](https://github.com/confarg/confarg/tree/master/examples/10_nested_configurations).

So far, our configurations consisted of a single, flat dataclass — just a set of keys. However, they need not be. Complex configurations typically consist of a hierarchy of nested, often independent, subconfigurations.

Let's extend our app by adding a log level. The log level is orthogonal to the database backend, and therefore sits next to it. We translate this into this new configuration:

```python
@dataclass
class Config:
    db: DBBaseConfig
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

Our former root-level database configuration is now found at the `db` field of our new configuration, next to the `log_level`.

## In configuration files

As you might expect, this nesting is mirrored in configuration files. Our former database configuration is now under the `db` key instead of being at the root level.

```yaml
# config.yaml
db:
  class: configs.PostgreSQLConfigChild
  host: example.com
  schema_name: mydb
log_level: DEBUG
```

```console
$ uv run myapp.py --config config.yaml
Config(db=PostgreSQLConfigChild(host='example.com',
                                port=5432,
                                schema_name='mydb'),
       log_level='DEBUG')
```

## In command line arguments

Command line arguments represent deep entries by their path, which consists of joining parent keys with `.`. In our example, to choose an SQLite backend, we now need to pass the `--db.class` and `--db.dbpath` arguments instead of `--class` and `--dbpath`.

```console
$ # DB configuration arguments are now prefixed with `db.`
$ uv run myapp.py --db.class configs.SQLiteConfigChild --db.dbpath /path/to/db.sqlite
Config(db=SQLiteConfigChild(dbpath='/path/to/db.sqlite'), log_level='INFO')
```

## In environment variables

In environment variables, paths use the double underscore `__` as the default separator. Using environment variables, the example from above would become

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_DB__CLASS=configs.SQLiteConfigChild MYAPP_DB__DBPATH=/path/to/db.sqlite uv run myapp.py
Config(db=SQLiteConfigChild(dbpath='/path/to/db.sqlite'), log_level='INFO')
```

> [!NOTE]
> A double underscore is used as the default separator to minimize the risk of name collisions, underscore being commonly used in python keys as per PEP8. You can change the separator if needed.


## Sub-configurations

A nice feature of confarg is its ability to load a sub-configuration at any key of the configuration. This enables splitting configurations into smaller, independent parts. Also, subconfiguration files can be easily reused in different contexts. This is achieved by postfixing the `--config` flag with the path to the key where to load the configuration file provided as argument.

Let's take a concrete example. When we updated our application at the beginning of this tutorial, the database configuration became nested under the `db` key, and we wrote a new configuration file `config.yaml`. Instead, we can keep our original database configuration and load it under the `db` key by using a `--config.db` flag:

```console
$ # Load a sub-configuration under the `db` key
$ uv run myapp.py --config.db sqlite.yaml
Config(db=SQLiteConfigChild(dbpath='/path/to/db.sqlite'), log_level='INFO')
```

As before, we can overwrite a configuration with another configuration, as long as the latter appears after the former in the argument list.

```console
$ # Overwriting the db config with a sub-config
$ uv run myapp.py --config config.yaml --config.db sqlite.yaml
Config(db=SQLiteConfigChild(dbpath='/path/to/db.sqlite'), log_level='DEBUG')
```

The same left-to-right reading order applies with subconfiguration files. Here, the full `config.yaml` overwrites the data imported from the `sqlite.yaml` subconfig.

```console
$ uv run myapp.py --config.db sqlite.yaml --config config.yaml
Config(db=PostgreSQLConfigChild(host='example.com',
                                port=5432,
                                schema_name='mydb'),
       log_level='DEBUG')
```


Same thing for command line arguments, nothing changes except the key path.

```console
$ # Overwriting the db config with command line arguments
$ uv run myapp.py --config config.yaml --db.class configs.SQLiteConfigChild --db.dbpath /path/to/db.sqlite
Config(db=SQLiteConfigChild(dbpath='/path/to/db.sqlite'), log_level='DEBUG')
```
