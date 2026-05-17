# Amending configurations

> [!TIP]
> Code for examples in this page can be found in [`examples/2_input_precedence`](https://github.com/confarg/confarg/tree/master/examples/2_input_precedence).

In the [previous tutorial](../1_three_input_sources/README.md), we saw that a configuration can be read from files, environment variables, and command line arguments. Those sources can be mixed — this is actually the intended way of working, as we will now see.

## Input precedence

It is not an error to have the same configuration element defined several times across the different inputs. When confarg reads a new value for an existing entry, the new value overwrites the old one. This enables to update a configuration in a variety of ways.

Therefore, it is important to know the order in which inputs are read, knowing that later reads overwrite existing values:

* configuration files are read first;
* then, values are read from environment variables;
* and finally, values are read from command line arguments.

It is actually a bit more subtle than that, but this is the correct mental model.

### Overwriting the configuration from the command line

Taking the same example as before, we can change values defined in the configuration file from the command line:

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
$ MYAPP_SCHEMA_NAME=otherdb uv run myapp.py --config config.yaml --schema_name=finaldb
DBConfig(host='example.com', port=1234, schema_name='finaldb')
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

## Using multiple configuration files

The `--config` option can take multiple arguments. The provided configuration files are read from left to right. This can be used to either amend part of an existing configuration, or build a full configuration from various parts.

In the example below, the data from `config_no_schema.yaml` overwrites the data in `config.yaml` — note the port number. The `schema_name` from `config.yaml` is kept as it is missing from `config_no_schema.yaml`.

```console
$ uv run myapp.py --config config.yaml config_no_schema.yaml
DBConfig(host='example.com', port=5678, schema_name='mydb')
```

The order matters since the resolution is from left to right. If we invert the order of the arguments, `config_no_schema.yaml` gets entirely overwritten by the complete `config.yaml`.

```console
$ uv run myapp.py --config config_no_schema.yaml config.yaml
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
