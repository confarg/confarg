# Three input sources

> [!TIP]
> Code for examples in this page can be found in [`examples/1_three_input_sources`](https://github.com/confarg/confarg/tree/master/examples/1_three_input_sources).

Let's dive in. Suppose we have an app that needs to connect to some database server. The app relies on the following configuration:

```python
@dataclass(kw_only=True)
class PostgreSQLConfig:
    host: str
    port: int = 5432
    schema_name: str
```

The application relies on confarg to load the configuration:

```python
confarg.load(PostgreSQLConfig, env_prefix="MYAPP_")
```

Let's take a first tour of the different ways the configuration can be loaded thanks to confarg.

## From the command line

We can provide the values of the configuration using command-line arguments:

```console
$ uv run myapp.py --host example.com --schema_name mydb
PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
```
<!--
```console
$ uv run myapp_argparse.py --host example.com --schema_name mydb
PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
```
 -->

> [!NOTE]
> Names are preserved in command-line arguments. They are *not* slugified (e.g. `schema_name` does not become `--schema-name`). This consistency avoids unnecessary complications of search-and-replace operations.

> [!NOTE]
> Fields with default values are optional.


## From environment variables

Values can also be provided by environment variables. The result of the following is identical to the run above:

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_HOST=example.com MYAPP_SCHEMA_NAME=mydb uv run myapp.py
PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
```
<!-- pytest-markdown-console: platform:linux -->
<!--
```console
$ MYAPP_HOST=example.com MYAPP_SCHEMA_NAME=mydb uv run myapp_argparse.py
PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
```
 -->

> [!NOTE]
> You need to explicitly set an environment variable prefix (`MYAPP_` in the example above) to unlock support for environment variables. This avoids having a default prefix (empty or otherwise) shared by all applications. You can still choose an empty prefix, but you need to be explicit about it.

## From files

Most complex configurations will generally be stored in one or several files. In the simplest case, such as here, the path to the configuration file can be passed via the `--config` command-line argument.

Confarg supports the following formats for configurations:

* **JSON**:

    ```console
    $ uv run myapp.py --config postgre.json
    PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
    ```
<!--  
    ```console
    $ uv run myapp_argparse.py --config postgre.json
    PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
    ```
-->

* **TOML**:

    ```console
    $ uv run myapp.py --config postgre.toml
    PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
    ```
<!--
    ```console
    $ uv run myapp_argparse.py --config postgre.toml
    PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
    ```
-->

* **YAML**, if the `pyyaml` package is installed:

    ```console
    $ uv run myapp.py --config postgre.yaml
    PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
    ```
<!--
    ```console
    $ uv run myapp_argparse.py --config postgre.yaml
    PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
    ```
-->


The configuration can also be specified from the environment:

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_CONFIG=postgre.yaml uv run myapp.py
PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
```
<!-- pytest-markdown-console: platform:linux -->
<!--
```console
$ MYAPP_CONFIG=postgre.yaml uv run myapp.py
PostgreSQLConfig(host='example.com', port=5432, schema_name='mydb')
```
-->

> [!NOTE] Integration with CLIs
> `confarg.load` consumes command-line arguments without generating inline help to expose them to the user. It is suited for simple tools and, as is the case here, for demonstrating the functionality of the library. The subject of integration with CLIs is an entire topic of its own and we cover it in a later tutorial.
