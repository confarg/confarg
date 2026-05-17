<p align="center">
  <img src="docs/assets/banner.svg" alt="confarg" />
</p>

# A tool to manage complex configurations

> Load and resolve complex configurations from files, environment variables and command line arguments. Keep your data structures and favorite CLI library.

`confarg` is a Python library that helps you load configurations in a modular fashion from multiple sources: files, environment variables, and command line arguments.

It can handle deeply nested configurations, type unions, derived classes, expressions and variable interpolation, configuration compositions and more, and can integrate with your favorite argument parser library such as `argparse`, `click` or `typer`.

`confarg` is not a framework. No decorator, base class or special annotation type required: none are provided. It is just a tool for the deserialization and serialization of complex configurations. Its footprint in your code is typically a few lines of code.

## Install

```bash
pip install confarg
```

`confarg` comes with no dependency, but installing additional libraries such as `pyyaml` unlocks the support of extra configuration file formats.

## TL;DR

This library lets you read configurations stored in classes like this

```python
@dataclass
class Config:
  value: float
  flag: bool
  subconfig: SubConfig1 | SubConfig2
```

with this kind of code

```python
config = confarg.load(Config)
```

which lets you build a configuration object from files,

```yaml
value: 1.0
flag: false
subconfig:
  foo: 42
```

but also and simultaneously from environment variables,

```properties
MYAPP_VALUE=0.0
```

and command line arguments,

```bash
myapp --subconfig.foo=33
```

Still here? Read along, we are just getting started.

## Getting started

> All the examples presented in this section (and more) are available in the `examples/` folder.

Imagine that you have an app that depends on some parameters that you have collected into a `dataclass` like so:

```python
@dataclass
class DBConfig:
    host: str
    port: int
    name: str
```

In your app, you use `confarg` to instantiate this configuration:

```python
db_config = confarg.load(DBConfig)
```

This allows you to construct a `DBConfig` object by collecting data from three possible sources.

1. From a configuration file. By passing `--config <config_file>` to your app, `confarg` will load the content of the file and fill the `DBConfig` object. For example, a config file could look like so:

   ```yaml
   # config.yaml
   host: example.com
   port: 1234
   name: mydb
   ```

   You would then call your application as

   ```console notest
   $ myapp.py --config config.yaml
   DBConfig(host='example.com', port=1234, name='mydb')
   ```

   Configuration files in TOML and JSON formats are also supported.

   > You can change the default `config` flag to something else using the `config_flag` parameter.

2. From environment variables. You can declare

   ```properties
   MYAPP_HOST=example.com
   MYAPP_PORT=1234
   MYAPP_NAME=mydb
   ```

   for the same effect.

   > Note that the environment variable prefix of your app should actually be passed to `confarg.load` like so:
   >
   > ```python
   > db_config = confarg.load(DBConfig, env_prefix="MYAPP_")
   > ```

3. From command line arguments.

   ```console notest
   $ my_app --host example.com --port 1234 --name mydb
   DBConfig(host='example.com', port=1234, name='mydb')
   ```

### Progressive build-up

The examples above presented different sources to feed your configuration. They are not mutually exclusive — in fact, they are intended to be used simultaneously.

Note that no one source needs to provide a complete configuration, as long as the configuration resulting from this progressive build-up is complete.

For example, taking our previous example, you could have a partial configuration file containing only host information,

```yaml
# partial_config.yaml
host: example.com
port: 1234
```

and provide the schema name from the command line:

```console notest
$ myapp.py --config partial_config.yaml --name mydb
DBConfig(host='example.com', port=1234, name='mydb')
```

### Source precedence

Configuration data is read in the following order, later read overwriting existing data:

1. configuration files are read first;
2. then environment variables;
3. finally, command line arguments.

This allows for surgical modifications of configuration files. For example, one could overwrite the schema configuration from our existing `full_config` from the command line like so:

```console notest
$ # Overwrite the schema name defined in the config file from the command line
$ myapp.py --config config.yaml --name otherdb
DBConfig(host='example.com', port=1234, name='otherdb')
```

### Unions

Let's say your app needs to support SQLite databases. You now have two different, incompatible DB configurations:

```python
@dataclass
class DBServerConfig:
    host: str
    port: int
    name: str

@dataclass
class SQLiteConfig:
    dbpath: str
```

The DB configuration needs to be either one or the other, which we declare like so:

```python
type DBConfig = SQLiteConfig | DBServerConfig
```

`confarg` can handle this new union type and figure out which configuration is desired based on the arguments it got:

```console notest
$ # Pass DBServerConfig parameters, and you get a DBServerConfig
$ myapp.py --host example.com --port 1234 --name mydb
DBServerConfig(host='example.com', port=1234, name='mydb')
$ # Pass SQLiteConfig parameters, and you get a SQLiteConfig
$ myapp.py --dbpath db.sqlite
SQLiteConfig(dbpath='db.sqlite')
```

### Disambiguation tags

For simple configurations, the above automatic disambiguation is enough and convenient.

In more complex configuration scenarios, this automatic disambiguation may not be not possible. For example, different configurations may share the exact same fields.

Even when disambiguation is possible, it may not be obvious to the human eye which object class should be return from the provided parameters.

Therefore, by necessity or for the sake of clarity, you can provide the class path of the required configuration by using the `class` tag, like so

```console notest
$ # Explicitly ask for a SQLiteConfig
$ myapp.py --class myapp.SQLiteConfig --dbpath db.sqlite
SQLiteConfig(dbpath='db.sqlite')
```

One example where it is necessary to provide the `class` path is to overwrite the configuration with a new class. Without it, command line arguments are added to the configuration, resulting in an invalid input.

```console notest
$ # Config file contains a DBServerConfig
$ myapp.py --config db_server.yaml
DBServerConfig(host='example.com', port=1234, name='mydb')
$ # Fails:  dbpath is not a DBServerConfig key
$ myapp.py --config db_server.yaml --dbpath db.sqlite
...
$ # OK: using class signals overwrite existing DB config
$ myapp.py --config db_server.yaml --class myapp.SQLiteConfig --dbpath db.sqlite
SQLiteConfig(dbpath='db.sqlite')
```

### Inheritance

Another way to provide a flexible configuration is to derive akin configuration classes from a common base class.

```python
@dataclass
class DBConfig:
    pass

@dataclass
class DBServerConfig(DBConfig):
    host: str
    port: int
    name: str

@dataclass
class SQLiteConfig(DBConfig):
    dbpath: str
```

This allows configurations to be easily extensible. Contrast with unions, where a class must be explicitly listed to be supported.

The downside is that the concrete class must be tagged, as `confarg` cannot discover classes derived from a given class.

```console notest
$ # Fails:  derived class not specified
$ uv run myapp.py --dbpath db.sqlite
...
$ # OK: explicit class path provided
$ uv run myapp.py --dbpath db.sqlite --class myapp.SQLiteConfig
SQLiteConfig(dbpath='db.sqlite')
```

### Configuration hierarchies

The configurations discussed so far has been rather simple, composed of values grouped together in a `dataclass`. However, it needs not be. Configurations are generally deeply nested hierarchies, which `confarg` supports.

Let's say you want to add a log level to your application. You place it at the root level of a new `Config` object, along with the DB configuration, that is now one level down under the `db` key.

```python
@dataclass
class Config:
    db: DBConfig
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

You now parse your new top-level `Config` instead of `DBConfig`.

```python
config = confarg.load(Config)
```

Our DB configuration, which used to be the root configuration, is now located under the `db` key. This has the following impact.

For command line arguments, we follow the common convention of using dot-separated paths to address nested fields. Previous command line arguments for `DBConfig` are now prefixed by `db.`, like so:

```console notest
$ myapp.py --db.class myapp.SQLiteConfig --db.dbpath db.sqlite
Config(db=SQLiteConfig(dbpath='db.sqlite'), log_level='INFO')
```

The configuration file is also modified accordingly,

```yaml
# config.yaml
db:
  class: myapp.DBServerConfig
  host: example.com
  name: mydb
  port: 1234
```

and is used just like before:

```console notest
$ myapp.py --config config.yaml
Config(db=DBServerConfig(host='example.com', port=1234, name='mydb'),
       log_level='DEBUG')
```

### Leaf data type and type coercion

You may have noticed that the previous section introduced a `log_level` parameter that has two interesting features: first, it is not of a simple type (`str`, `int`, `float`, `bool` or `None`); second, it comes with a default value.

Default values are honored, and you may have noticed that we did not provide any value to `log_level`. You can of course override a default value.

As for leaf node data type, `confarg` coerces `Enum` and `Path` types as special exceptions to simple types. Other types are treated as classes and must follow the same rules.

### Expressions and variable interpolation

Your application is becoming more complex by the day, and is now requiring a resources configuration.

```python
@dataclass
class Resources:
    cpu_count: int
    memory_gb: int
    max_heap_size_mb: int
```

It is added to the global configuration under the `resources` key:

```python
@dataclass
class Config:
    db: DBConfig
    resources: Resources
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

Your configuration file has become,

```yaml
# config.yaml
db:
  class: myapp.DBServerConfig
  host: example.com
  name: mydb
  port: 1234

resources:
  cpu_count: 4
  memory_gb: 16
  max_heap_size_mb: 131072
```

This works fine. However, you want to better express the fact that `max_heap_size_mb` is chosen to be 80% of the host memory by default. To achieve this, you can write expressions relying on variable interpolation using the `${...}` syntax, like so:

```yaml
# expression_config.yaml
db:
  class: myapp.DBServerConfig
  host: example.com
  name: mydb
  port: 1234

resources:
  cpu_count: 4
  memory_gb: 16
  max_heap_size_mb: ${int(resources.memory_gb * 1024 * 0.8)}
```

```console notest
$ myapp.py --config expression_config.yaml
Config(db=SQLiteConfig(dbpath='db.sqlite'),
       resources=Resources(cpu_count=4, memory_gb=16, max_heap_size_mb=13107),
       log_level='INFO')
```

Note that variable interpolation occurs after all configuration data is read. This means here that you can override `memory_gb` from the command line, and `max_heap_size_mb` will be adjusted accordingly, even though the expression is defined in the configuration file.

```console notest
$ # Max heap is recomputed according to the expression in the config file
$ myapp.py --config expression_config.yaml --resources.memory_gb 8
Config(db=SQLiteConfig(dbpath='db.sqlite'),
       resources=Resources(cpu_count=4, memory_gb=8, max_heap_size_mb=6553),
       log_level='INFO')
```

### Building large configurations from parts

Large configurations are often made up of independent components, and as such, you may want to split them accordingly. It is easier to navigate, but it also makes it possible to reuse configuration parts and to build multiple complex configurations from the same set of atomic configuration components.

Some configuration components may even be generated automatically, in which case being able to isolate those parts from the rest is a must.

`confarg` lets you do this in different ways.

From the command line, the `--config` flag can be suffixed with a key path to load configurations there. For example,

```console notest
# Load a config file specific to the `db` key
$ myapp.py --config.db db_config.yaml
Config(db=DBServerConfig(host='example.com', port=1234, name='mydb'), log_level='INFO')
```

A similar pattern applies to environment variables:

```console notest
$ MYAPP_CONFIG_DB=db_config.py myapp.py
Config(db=DBServerConfig(host='example.com', port=1234, name='mydb'), log_level='INFO')
```

> Note that `db_config.yaml` does *not* contain the `db` key. It does not need to know the path it is loaded to.

In config files, you can load a configuration by specifying the special `__include__` key, followed by the path to the sub-configuration to load, like so:

```yaml
# set everything under the `db` key from another file
db:
  __include__: ./db_config.yaml
```

The `__include__` keyword can also be used at the top-level, to create a new config that amends an existing config.

```yaml
# start from this base configuration
__include__: base_config.yaml

# set or overwrite everything under the `db` key
db:
  __include__: ./db_config.yaml
```

## Next steps

We have more than scratched the surface, and you should have enough knowledge to cover most of your needs.

Again, all of the examples above and more are in the `examples/` folder, which is a great way to discover and experiment with the library features.

A documentation is also currently being written at https://confarg.github.io/confarg/.
