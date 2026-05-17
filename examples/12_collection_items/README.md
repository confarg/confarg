# Collection items

> [!TIP]
> Code for examples in this page can be found in [`examples/12_collection_items`](https://github.com/confarg/confarg/tree/master/examples/12_collection_items).

You can reference an individual item in a collection by its index, which lets you modify its value.

## From the command line

Individual items of a collection are referenced using their positional index in their path.

For example, returning to the examples introduced in [Tutorial #11](https://github.com/confarg/confarg/tree/master/examples/11_collections), we can modify the first item of the input using the `--input.0` flag.

```console
$ uv run list_of_ints.py --config pair_of_ints.yaml --input.0 -4
Config(input=[-4, 2])
```

Note that types specified as `tuple` are not immutable during the configuration build-up: here, the tuple initialized by the configuration file is modified from the command line.

```console
$ uv run pair_of_ints.py --config pair_of_ints.yaml --input.0 -4
Config(input=(-4, 2))
```

Negative indices also work, allowing to index counting from the end of the sequence. For example, here we modify the last element of the input:

```console
$ uv run pair_of_ints.py --config pair_of_ints.yaml --input.-1 -4
Config(input=(1, -4))
```

Indices work at any level of the key path, not just for the leaf type.

```console
$ # A collection of database configurations
$ uv run myapp.py --config config.yaml
Config(dbs=[SQLiteConfigChild(dbpath='db.sqlite'),
            PostgreSQLConfigChild(host='example.com',
                                  port=5432,
                                  schema_name='mydb')])
$ # Change the schema_name of the last configuration
$ uv run myapp.py --config config.yaml --dbs.-1.schema_name other_db
Config(dbs=[SQLiteConfigChild(dbpath='db.sqlite'),
            PostgreSQLConfigChild(host='example.com',
                                  port=5432,
                                  schema_name='other_db')])
```

Indices compose at every level of nesting. When an item is itself a collection, a deeper index patches that inner item in place rather than replacing the whole inner collection.

```console
$ uv run list_of_list_of_ints.py --config list_of_list_of_ints.yaml
Config(input=[[1, 2, 3], [4, 5]])
$ # Let's modify the first element of the last list
$ uv run list_of_list_of_ints.py --config list_of_list_of_ints.yaml --input.-1.0 42
Config(input=[[1, 2, 3], [42, 5]])
```

## From environment variables

## From configuration files

Indexing also works from within configuration files. The same behavior as above is obtained with this configuration file:

```yaml
# partial_config.yaml
dbs:
  -1:
    schema_name: other_db
```

```console
$ uv run myapp.py --config config.yaml partial_config.yaml
Config(dbs=[SQLiteConfigChild(dbpath='db.sqlite'),
            PostgreSQLConfigChild(host='example.com',
                                  port=5432,
                                  schema_name='other_db')])
```

And finally, indexing also works for partial configuration files. The same behavior can be obtained with a partial PostgreSQL configuration containing only the schema name:

```yaml
# schema_name.yaml
schema_name: other_db
```

This partial PostgreSQL configuration is then used to update the existing configuration by loading it at the end of the `dbs` collection:

```console
$ uv run myapp.py --config config.yaml --config.dbs.-1 schema_name.yaml
Config(dbs=[SQLiteConfigChild(dbpath='db.sqlite'),
            PostgreSQLConfigChild(host='example.com',
                                  port=5432,
                                  schema_name='other_db')])
```

## Building a collection from its elements

A collection can be built element by element, in any order.

Its fixed length is known from the type, so negative indices count from the end here too.

```console
$ uv run pair_of_ints.py --input.0 42 --input.1 -0xF
Config(input=(42, -15))
$ uv run list_of_ints.py --input.1 42 --input.0 -0xF
Config(input=[-15, 42])
```

In the case of a tuple, negative indices work because its length is known. This is not the case for lists.

```console
$ uv run pair_of_ints.py --input.0 42 --input.-1 -0xF
Config(input=(42, -15))
$ uv run list_of_ints.py --input.0 42 --input.-1 -0xF  # Error
...
```

Note that this behavior is for building a collection that does not yet exist. When the collection already exists, the behavior is different for lists, as indices can only modify existing elements.

```console
$ uv run list_of_ints.py --config pair_of_ints.yaml
Config(input=[1, 2])
$ # Error: `2` is not a valid positional index
$ uv run list_of_ints.py --config pair_of_ints.yaml --input.2 3
...
...
```

Tuples don't have this problem and can be constructed part by part. Because the length is
known from the type, an index past the end of a shorter base completes the tuple rather than
being rejected.

```console
$ uv run triplet_of_ints.py --config pair_of_ints.yaml --input.2 3
Config(input=(1, 2, 3))
```
