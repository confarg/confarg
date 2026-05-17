# Child configurations

> [!TIP]
> Code for examples in this page can be found in [`examples/9_child_configurations`](https://github.com/confarg/confarg/tree/master/examples/9_child_configurations).

We saw in [Tutorial #6](https://confarg.github.io/confarg/examples/6_unions/) that unions bring flexibility by allowing alternative configurations. This is helpful when you can list all of the available options explicitly. However, if you want configurations to be extensible, we can turn to inheritance. In confarg, whenever a class is specified in a configuration, it allows you to build a configuration with a derived class.

Contrary to unions, where the correct variant type can be deduced implicitly from the provided arguments, the fully-qualified name (FQN) of the desired subclass must be provided explicitly via the `class` field, as confarg cannot discover undeclared derived classes.

Going back once again to our database example, this time let's make `DBConfig` the base class of our SQLite and PostgreSQL configurations.

```python
@dataclass
class DBBaseConfig:
    """Base database configuration."""

@dataclass(kw_only=True)
class PostgreSQLConfigChild(DBBaseConfig):
    host: str
    port: int = 5432
    schema_name: str

@dataclass
class SQLiteConfigChild(DBBaseConfig):
    dbpath: str
```

If we try to select the SQLite configuration by relying on the uniqueness of its arguments as in [Tutorial #6](https://confarg.github.io/confarg/examples/6_unions/), it fails.

```console
$ # Error: no class discriminator selecting a DBConfig subclass
$ uv run myapp.py --dbpath /path/to/db.sqlite  # Error: DBBaseConfig has no dbpath field
...
```

We now need to pass the FQN of the desired child configuration explicitly using the `--class` flag.

```console
$ uv run myapp.py --class configs.SQLiteConfigChild --dbpath /path/to/db.sqlite
SQLiteConfigChild(dbpath='/path/to/db.sqlite')
```

This works similarly in configuration files. Our previous configuration,

```yaml
# postgres.yaml
host: example.com
schema_name: mydb
```

doesn't work anymore:

```console
$ uv run myapp.py --config postgres.yaml  # Error
...
```

We fix the issue by adding the FQN of the desired configuration under the `class` key.

```yaml
# postgres_fqn.yaml
class: configs.PostgreSQLConfigChild
host: example.com
schema_name: mydb
```

```console
$ uv run myapp.py --config postgres_fqn.yaml  # OK
PostgreSQLConfigChild(host='example.com', port=5432, schema_name='mydb')
```


## Unions and inheritance combinations

You can mix union and inheritance scenarios. Here, we add to the previous example, by combining the base `DBConfig` class with a new `APIConfig` class in a union.

```python
@dataclass
class APIConfig:
    url: str
    token: str

type Config = APIConfig | DBBaseConfig
```

We can now choose either the DB backend or the API backend.

```console
$ # Choosing the SQLite backend
$ uv run db_or_api.py --class configs.SQLiteConfigChild --dbpath db.sqlite
SQLiteConfigChild(dbpath='db.sqlite')
$ # Choosing the API backend
$ uv run db_or_api.py --class configs.APIConfig --url https://example.com/api --token ABCD
APIConfig(url='https://example.com/api', token='ABCD')
```

Note that providing the FQN of the API configuration is not strictly necessary, as it is an explicit variant of the union.

```console
$ # Works without the `class` key
$ uv run db_or_api.py --url https://example.com/api --token ABCD
APIConfig(url='https://example.com/api', token='ABCD')
```

Though, this is discouraged. By always providing the FQN, you ensure that your configuration is explicit and future-proof, should you later refactor `APIConfig` as a derived class of a more general base config class. It is also less surprising: otherwise, users wonder why the FQN is needed in some cases but not in others.

> [!TIP]
> In confarg, just like in python, where a config class is declared, any derived class is accepted. For this, the fully-qualified name of the class must be passed under the `class` key.
