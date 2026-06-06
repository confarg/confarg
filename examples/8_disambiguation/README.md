# Disambiguation

> [!TIP]
> Code for examples in this page can be found in [`examples/8_disambiguation`](https://github.com/confarg/confarg/tree/master/examples/8_disambiguation).


Let's see how to achieve that in confarg.

## The discriminator field pattern

Our first option is to still rely on automatic disambiguation, and making sure it always succeeds by adding a discriminator field that can furthermore explicitly convey the variant that is chosen.

Let's go back again to our database example. Say we have two configurations to connect to either a PostgreSQL or a MariaDB backend. Both configurations are identical in our example, and therefore cannot be discriminated. Even if they were, we would still like it to be obvious which backend is chosen in our configuration file, rather than having to guess.

We apply the discriminator-field pattern by introducing a `Literal` field that identifies the configurations with a clear, explicit label.

```python
@dataclass(kw_only=True)
class PostgreConfig:
    tag: Literal["postgre"] = "postgre"
    host: str
    port: int
    name: str


@dataclass(kw_only=True)
class MariaDBConfig:
    tag: Literal["mariadb"] = "mariadb"
    host: str
    port: int
    name: str
```

Now we rely on the tag to select a variant.

```console
$ uv run dbhosts_tag.py --tag postgre --host example.com --port 5432 --name mydb
PostgreConfig(tag='postgre', host='example.com', port=5432, name='mydb')
```

This works similarly with configuration files.

```console
$ uv run dbhosts_tag.py --config postgre_tagged.yaml
PostgreConfig(tag='postgre', host='example.com', port=1234, name='mydb')
$ uv run dbhosts_tag.py --config mariadb_tagged.yaml
MariaDBConfig(tag='mariadb', host='example.com', port=5678, name='mydb')
```

This pattern relies on the automatic disambiguation of confarg based on compatibilities of the provided input — here, a `Literal` field, that doesn't need to be explicitly flagged to confarg as such. It is a reasonable pattern if you own the classes and are willing to add a field for the sole purpose of deserialization.

## Providing a fully qualified name

The alternative is to provide the fully qualified name (FQN) of the target type. This works universally for any class, and is therefore the preferred way, as it can be used consistently.

In confarg, the FQN of the type of an input is provided under the `class` key.

> [!NOTE]
> The `class` key cannot collide with a valid field name or initializer argument, as it is a reserved keyword in python.

Going back to our database example, the configurations don't need a discriminator field anymore.


```python
@dataclass(kw_only=True)
class PostgreConfig:
    host: str
    port: int
    name: str


@dataclass(kw_only=True)
class MariaDBConfig:
    host: str
    port: int
    name: str
```

To properly select one variant, we provide its class with the `class` key.

```console
$ uv run dbhosts.py --class __main__.PostgreConfig --host example.com --port 5432 --name mydb
PostgreConfig(tag='postgre', host='example.com', port=5432, name='mydb')
$ uv run dbhosts.py --class __main__.MariaDBConfig --host example.com --port 3306 --name mydb
MariaDBConfig(tag='mariadb', host='example.com', port=3306, name='mydb')
```

## Overriding a variant

We saw in [Tutorial #6](https://confarg.github.io/confarg/examples/6_unions/) how confarg can guess which variant to use based on the input arguments. However, overriding a variant may not work as you might expect.

```console
$ # Loading a PostgreSQL configuration from file
$ uv run myapp.py --config postgre.yaml
DBServerConfig(host='example.com', port=1234, name='mydb')
$ # Setting a SQLite configuration from the command line
$ uv run myapp.py --dbpath /path/to/db.sqlite
SQLiteConfig(dbpath='/path/to/db.sqlite')
$ # Can we overwrite the config from the command line like so?
$ uv run myapp.py --config postgre.yaml --dbpath /path/to/db.sqlite  # Error
...
```

This last command fail, and it is important to understand why.

As mentioned in [Tutorial #2](https://confarg.github.io/confarg/examples/2_input_precedence/), the configuration is built progressively, and collected arguments are checked against the configuration type at the very end only. Here, the `dbpath` key from the command line is added to the keys defined in `postgre.yaml`, and since no configuration accepts all of those keys, the configuration fails to load.

In confarg, to discard any existing input for a given entry, you can provide the `.class` key — the same one that is used for disambiguation. By using this key, you signal to confarg that you are creating a new object of this type, and that any existing input under that entry is to be discarded.

```console
$ # OK: explicitely discard previous keys and start fresh
$ uv run myapp.py --config postgre.yaml --class __main__.SQLiteConfig --dbpath /path/to/db.sqlite
SQLiteConfig(dbpath='/path/to/db.sqlite')
```

> [!IMPORTANT]
> Keys are always added to keys previously read. When overwriting an existing object, always specify its class if you intend to discard any preexisting entry and create a new object. Use keys alone if you know the object you are amending.
