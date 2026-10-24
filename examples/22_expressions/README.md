# Expressions and variable interpolation

> [!TIP]
> Code for examples on this page can be found in [`examples/22_expressions`](https://github.com/confarg/confarg/tree/master/examples/22_expressions).

confarg can process expressions, which are declared within `${...}`.
These expressions allow you to deduce configuration values from other parts of the configuration.

Suppose we have a configuration composed of two floating point values:

<!-- snippet: two_floats.py#Config -->
```python
@dataclass
class Config:
    value1: float
    value2: float
```

You can set the value of `value2` based on an expression relying on `value1`, for example.

<!-- snippet: derived_value2.yaml -->
```yaml title="derived_value2.yaml"
value1: 3.0
value2: ${value1 * 1.5}
```

```console
$ uv run two_floats.py --config derived_value2.yaml
Config(value1=3.0, value2=4.5)
```

The expression does not need to come after the variable it references.
Having `value1` referring to `value2` works too.

<!-- snippet: derived_value1.yaml -->
```yaml title="derived_value1.yaml"
value1: ${value2 * 1.5}
value2: 3.0
```

```console
$ uv run two_floats.py --config derived_value1.yaml
Config(value1=4.5, value2=3.0)
```

It's OK to have expressions relying on variables that are themselves expressions.
For example, if we now have three input float values, the following configuration is valid.

<!-- snippet: chained_expressions.yaml -->
```yaml title="chained_expressions.yaml"
value1: ${value2 * 1.5}
value2: ${value3 * 1.5}
value3: 2.0
```

```console
$ uv run three_floats.py --config chained_expressions.yaml
Config(value1=4.5, value2=3.0, value3=2.0)
```

If your chain of expressions contains a loop, confarg will complain.

<!-- snippet: config_with_loop.yaml -->
```yaml title="config_with_loop.yaml"
value1: ${value2 * 1.5}
value2: ${value3 * 1.5}
value3: ${value1 * 1.5}
```

```console
$ # Error: circular reference
$ uv run three_floats.py --config config_with_loop.yaml
...
```

The expressions can reach across definition boundaries.
For example, a configuration file can define `value1`, and we can define `value2` based on an expression over `value1` from the command line.

<!-- snippet: cli_expression.yaml -->
```yaml title="cli_expression.yaml"
value1: 3.0
```

```console
$ uv run two_floats.py --config cli_expression.yaml --value2 '${value1 * 1.5}'
Config(value1=3.0, value2=4.5)
```

The opposite also works: we can define `value1` as an expression of `value2`, which is defined late on the command line.

<!-- snippet: cli_value.yaml -->
```yaml title="cli_value.yaml"
value1: ${value2 * 1.5}
```

```console
$ uv run two_floats.py --config cli_value.yaml --value2 3.0
Config(value1=4.5, value2=3.0)
```

Even if `value2` is already defined in the configuration file, the final value of `value2` is taken into account in the expression.

```console
$ uv run two_floats.py --config derived_value1.yaml
Config(value1=4.5, value2=3.0)
$ uv run two_floats.py --config derived_value1.yaml --value2 6
Config(value1=9.0, value2=6.0)
```

## Referencing a whole section

An expression references a _path_, and that path does not have to point at a single value.
`${database}` substitutes the whole section.

<!-- snippet: struct_ref.py#Database -->
```python
@dataclass
class Database:
    host: str
    port: int
```

<!-- snippet: struct_ref.py#Service -->
```python
@dataclass
class Service:
    database: Database
```

<!-- snippet: struct_ref.py#Config -->
```python
@dataclass
class Config:
    database: Database
    service: Service
```

<!-- snippet: section_reference.yaml -->
```yaml title="section_reference.yaml"
database:
  host: localhost
  port: 5432
service:
  database: ${database}
```

```console
$ uv run struct_ref.py --config section_reference.yaml
Config(database=Database(host='localhost', port=5432),
       service=Service(database=Database(host='localhost', port=5432)))
same object: False
```

Note the last line.
`service.database` is a **new** `Database` built from the same data — it is not `database` itself.
Expressions are resolved over the configuration data, before any object is constructed, so each place that references a section gets its own object.
Changing one afterwards does not change the other, and confarg offers no way to share a single instance between two fields.

Referencing a whole section is a starting point, not a verbatim copy: you can override parts of it by naming the fields you want to keep.

<!-- snippet: section_override.yaml -->
```yaml title="section_override.yaml"
database:
  host: localhost
  port: 5432
service:
  database:
    host: ${database.host}
    port: 5433
```

```console
$ uv run struct_ref.py --config section_override.yaml
Config(database=Database(host='localhost', port=5432),
       service=Service(database=Database(host='localhost', port=5433)))
same object: False
```
