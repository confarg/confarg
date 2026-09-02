# Dictionaries

> [!TIP]
> Code for examples in this page can be found in [`examples/14_dictionaries`](https://github.com/confarg/confarg/tree/master/examples/14_dictionaries).


Configurations can contain dictionaries, whose keys can be dynamically assigned. Take the following configuration:

```python
@dataclass
class Config:
    input: dict[str, int]
```

The dictionary can be filled with the same syntax used so far.

```console
$ uv run dict_of_ints.py --input.foo 42 --input.bar -13
Config(input={'foo': 42, 'bar': -13})
```


In dictionaries, keys are not limited to strings. They can be of any hashable type.

```console
$ uv run dict_of_strs_int_index.py --input.42 hello --input.-0xF world
Config(input={42: 'hello', -15: 'world'})
```

Just like lists, dictionaries allow for configurations with dynamic sizes, but they allow for more natural indexing. Let's take the example from [Tutorial #13](https://github.com/confarg/confarg/tree/master/examples/13_collection_items) featuring a dynamic number of database backends, and rewrite the configuration using dictionaries.

```python
@dataclass
class Config:
    dbs: dict[str, DBBaseConfig]
```

Now, each DB backend is indexed by a hand-picked key. This makes it easier to reference any particular item in order to modify it.

```console
$ # Each configuration is added under a hand-picked key
$ uv run myapp.py --config config.yaml
Config(dbs={'postgres': PostgreSQLConfigChild(host='example.com',
                                              port=5432,
                                              schema_name='mydb'),
            'sqlite': SQLiteConfigChild(dbpath='db.sqlite')})
$ # Pointing to the correct configuration is more readable and more robust to change
$ uv run myapp.py --config config.yaml --dbs.postgres.schema_name otherdb
Config(dbs={'postgres': PostgreSQLConfigChild(host='example.com',
                                              port=5432,
                                              schema_name='otherdb'),
            'sqlite': SQLiteConfigChild(dbpath='db.sqlite')})
```

The main drawback of dictionaries in this context is that keys are not checked, and typos are happily considered as new keys.

```console
$ uv run dict_of_ints.py --config dict_of_ints.yaml
Config(input={'foo': 42, 'bar': -13})
$ # Oops, typo silently added to dict
$ uv run dict_of_ints.py --config dict_of_ints.yaml --input.fooo 0
Config(input={'foo': 42, 'bar': -13, 'fooo': 0})
```
