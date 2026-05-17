# Three input sources

> [!TIP]
> Code for examples in this page can be found in [`examples/10_three_input_sources`](https://github.com/confarg/confarg/tree/master/examples/10_three_input_sources).

Let's dive in. Suppose we have an app that need to connect to some database server. The app relies on the following configuration:

```python
@dataclass
class DBConfig:
    host: str
    port: int
    schema_name: str
```

The application relies on confarg to load the configuration:

```python
confarg.load(DBConfig)
```

Let's have a first tour at the different ways the configuration can be loaded thanks to confarg.

## From the command line

We can provide the values of the configuration using command line arguments:

```console
$ uv run myapp.py --host example.com --port 1234 --schema_name mydb
DBConfig(host='example.com', port=1234, schema_name='mydb')
```

> [!NOTE]
> Names are preserved in command line arguments. They are *not* slugified (e.g. `schema_name` does not become `--schema-name`). This consistency avoids unnecessary complications of search-and-replace operations.

## From environment variables

Values can also be provided by environment variables. The result of the following is identical to the run above:

```console platform:linux
$ MYAPP_HOST=example.com MYAPP_PORT=1234 MYAPP_SCHEMA_NAME=mydb uv run myapp.py
DBConfig(host='example.com', port=1234, schema_name='mydb')
```

> [!NOTE]
> You need to explicitly choose an environment variable prefix for your application (`MYAPP_` in the example above) to unlock support for environment variables, which is off by default. You can explicitly choose not to use a prefix — but you still need to be explicit about it.

## From files

Most complex configurations will generally be stored in one or several files. In the simplest case, such as here, the path to the configuration file can be passed via the `--config` command line argument.

Confarg supports the following formats for configurations:

* JSON:

   ```console
   $ uv run myapp.py --config config.json
   DBConfig(host='example.com', port=1234, schema_name='mydb')
   ```

* TOML:

   ```console
   $ uv run myapp.py --config config.toml
   DBConfig(host='example.com', port=1234, schema_name='mydb')
   ```

* YAML, if the `pyyaml` package is installed:

  ```console
  $ uv run myapp.py --config config.yaml
  DBConfig(host='example.com', port=1234, schema_name='mydb')
  ```
