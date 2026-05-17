# Amending configurations

> [!TIP]
> Code for examples in this page can be found in [`examples/2_input_precedence`](https://github.com/confarg/confarg/tree/master/examples/2_input_precedence).

In the [previous tutorial](../1_three_input_sources/README.md), we saw that a configuration can be read from files, environment variables, and command line arguments. Those sources can be mixed — this is actually the intended way of working, as we will now see.

## Input precedence

It is not an error to have the same configuration element defined several times across the different inputs. When confarg reads a new value for an existing entry, the value is updated. This enables to update a configuration in a variety of ways.

Therefore, it is important to know the order in which configurations are read, knowing that later reads overwrite existing values.

* Configuration files are read first;
* then, values are read from environment variables;
* and finally, values are read from command line arguments.

It is a bit more subtle than what it might appear at first glance, but this is good enough for now.

### Overwriting the configuration from the command line

Taking the same example as before, we can change the value of the configuration from the command line:

```console
$ # change the schema name defined in `config.yaml` to `otherdb`
$ uv run myapp.py --config config.yaml --schema_name otherdb
DBConfig(host='example.com', port=1234, schema_name='otherdb')
```

### Overwriting the configuration from the environment

We could use environment variables for the same effect:

<!-- pytest-markdown-console: platform:linux -->
```console
$ # change the schema name defined in `config.yaml` to `otherdb`
$ MYAPP_SCHEMA_NAME=otherdb uv run myapp.py --config config.yaml
DBConfig(host='example.com', port=1234, schema_name='otherdb')
```

As mentioned above, command line arguments have the final word:

<!-- pytest-markdown-console: platform:linux -->
```console
$ # change the schema name defined in `config.yaml` to `otherdb`
$ MYAPP_SCHEMA_NAME=otherdb uv run myapp.py --config config.yaml --schema_name=yetanotherdb
DBConfig(host='example.com', port=1234, schema_name='yetanotherdb')
```


## Partial configurations

The configuration is progressively built up from the various input sources. At no time during this process does the configuration need to be complete: it only matters that the configuration is complete after all input sources have been parsed.

For example, you could have a partial configuration purposely omitting the schema name,

```yaml
# config_no_schema.yaml
host: example.com
port: 5678
```

and specify the schema name from the command line like so:

```console
$ uv run myapp.py --config config_no_schema.yaml --schema_name mydb
DBConfig(host='example.com', port=5678, schema_name='mydb')
```

## Multiple configuration files

The `--config` option can be repeated. The resulting configuration files are read from left to right, the latter completing or amending existing data. This can be used to either amend part of an existing configuration, or to build a full configuration from various parts.

In the example below, the data from `config_no_schema` overwrites `config` — note the port number. The `schema_name` from `config` is kept as it is missing from `config_no_schema`.

```console
$ uv run myapp.py --config config.yaml --config config_no_schema.yaml
DBConfig(host='example.com', port=5678, schema_name='mydb')
```

The order matters since the resolution is from left to right. If we invert the order of the arguments, `config_no_schema` gets entirely overwritten by the complete `config`.

```console
$ uv run myapp.py --config config_no_schema.yaml --config config.yaml
DBConfig(host='example.com', port=1234, schema_name='mydb')
```

Note that command line arguments always have priority over configuration files, no matter what the relative order of configuration files and other command line arguments is.

```console
$ # The port specified on the command line overwrites that of the config even if
$ # the config is specified after
$ uv run myapp.py --port 6006 --config config.yaml
DBConfig(host='example.com', port=6006, schema_name='mydb')
```

The configuration file specified by the environment has a lower priority than configuration files specified from the command line:

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_CONFIG=./config.yaml uv run myapp.py --config config_no_schema.yaml
DBConfig(host='example.com', port=5678, schema_name='mydb')
```

Only a single configuration file can be specified from the environment (via `<ENVPREFIX>CONFIG`), so there is nothing to be said about precedence here.
