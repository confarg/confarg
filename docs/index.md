---
icon: lucide/rocket
---

# A tool to manage complex configurations

> Load and resolve complex configurations from files, environment variables, and command line arguments. Keep your data structures and favorite CLI library.

`confarg` is a Python library that helps you load configurations in a modular fashion from multiple sources: files, environment variables, and command line arguments.

It can handle deeply nested configurations, type unions, derived classes, expressions and variable interpolation, configuration compositions, and more, and can integrate with your favorite argument parser library such as `argparse`, `click`, `typer` or `cyclopts`.


!!! note "`confarg` is not a framework"
    No decorator, base class, or special annotation type required: none are provided. It is just a tool for the deserialization and serialization of complex configurations. Its footprint in your code is typically a few lines of code.

## Install

=== "uv"

    ```bash
    uv add confarg
    ```

=== "pip"

    ```bash
    pip install confarg
    ```

`confarg` comes with no dependency, but installing additional libraries such as `pyyaml` enables support for extra configuration file formats.


## Configuration deserialization

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

!!! note
    Although we assume throughout the documentation that the deserialized object represent some sort of configuration, its actual purpose is in the hand of the application.

## Complex configuration

`confarg` offers a lot of flexibility in the configuration and its deserialization, to manage complex scenarios. It can handle, among other things:

* unions,
* derived classes,
* expressions and variable interpolation,
* building from parts,
* and much more.

## Integration into existing CLI libraries

`confarg` relies on command-line arguments to assign values to the configuration. However, there are already a rich offer of great CLI libraries out there, and `confarg` takes the approach of integrating with them, including providing tab-completion when possible.
