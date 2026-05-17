# Unions

> [!TIP]
> Code for examples in this page can be found in [`examples/6_unions`](https://github.com/confarg/confarg/tree/master/examples/6_unions).


One of the powerful features of confarg, which lies at the heart of complex configurations, is the ability to handle union types.

Let's go back to our database example introduced in [Tutorial #1](https://confarg.github.io/confarg/examples/1_three_input_sources/), where our app relies on this configuration to connect to a DB server:

```python
@dataclass
class DBServerConfig:
    host: str
    port: int
    name: str
```

Say our app now needs to also support an SQLite backend. We introduce a new configuration:

```python
@dataclass
class SQLiteConfig:
    dbpath: str
```

The two backends are mutually exclusive. In confarg, we translate this in our configuration in the most pythonic way, using a union type. We declare our configuration to be of type

```python
type Config = SQLiteConfig | DBServerConfig
```

We can now dynamically select among union variants. To select an SQLite backend, we simply need to provide the elements required by its configuration:

```console
$ uv run myapp.py --dbpath /path/to.db.sqlite
SQLiteConfig(dbpath='/path/to.db.sqlite')
```
<!--
```console
$ uv run myapp_argparse.py --dbpath /path/to.db.sqlite
SQLiteConfig(dbpath='/path/to.db.sqlite')
```
-->

Choosing a DB server backend instead works similarly:

```console
$ uv run myapp.py --host example.com --port 5432 --name schema
DBServerConfig(host='example.com', port=5432, name='schema')
```
<!--
```console
$ uv run myapp_argparse.py --host example.com --port 5432 --name schema
DBServerConfig(host='example.com', port=5432, name='schema')
```
-->

This works as well with configuration files, which could contain a configuration of either sort:

* a DBServerConfig configuration file:
    ```console
    $ uv run myapp.py --config postgre.yaml
    DBServerConfig(host='example.com', port=5432, name='mydb')
    ```
<!--  
    ```console
    $ uv run myapp_argparse.py --config postgre.yaml
    DBServerConfig(host='example.com', port=5432, name='mydb')
    ```
-->

* or, a SQLiteConfig configuration file:
    ```console
    $ uv run myapp.py --config sqlite.yaml
    SQLiteConfig(dbpath='/path/to/db.sqlite')
    ```
<!--
    ```console
    $ uv run myapp_argparse.py --config sqlite.yaml
    SQLiteConfig(dbpath='/path/to/db.sqlite')
    ```
-->


> [!NOTE]
> Confarg is smart enough to know which type in the union is targeted from the provided input types. However, such implicit disambiguation is not always possible, or even desirable. We will see in [Tutorial #8](https://confarg.github.io/confarg/examples/8_disambiguation/) how to set the target type explicitely.
