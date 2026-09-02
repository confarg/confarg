# Callables

> [!TIP]
> Code for examples in this page can be found in [`examples/18_callables`](https://github.com/confarg/confarg/tree/master/examples/18_callables).

Callables are accepted as leaf types. They deserve their own tutorial as they are a bit more involved than the average leaf type.

Take this configuration, which holds a `Callable[[str], None]` function:

```python
@dataclass
class Config:
    greet_fn: Callable[[str], None]
```

This callable is used to display a greeting message like so:

```python
config.greet_fn("world")
```

The callable can be specified in the following ways.

## Functions

The callable can be set to a function by specifying its fully-qualified name (FQN).

```console
$ uv run print_greetings.py --greet_fn greetings.print_greetings
Hello, world!
```

An expanded dict form can also be used, where the FQN of the function is given under the `fn` key.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.print_greetings
Hello, world!
```

## Classes

To use an instance of a class as a callable, we must use an expanded dict declaration, giving the FQN of the class under the usual `class` key.

```console
$ uv run print_greetings.py --greet_fn.class greetings.Print_greetings
Hello, world!
```

Additional keys needed to instantiate the class are given alongside the `class` key, as usual.

```console
$ uv run print_greetings.py --greet_fn.class greetings.Print_greetings --greet_fn.greetings Hi
Hi, world!
```

> [!NOTE]
> In case you wonder why we explicitly use the `class` key here to specify the class FQN as such, we will see in [Tutorial #20](https://confarg.github.io/confarg/examples/20_factories/) what happens when we use the class as a callable.

## Class methods

Like functions, class methods can be specified as callables. In the simplest case, when the object can be instantiated without arguments, the FQN of the method is passed either directly under the field key or under the `fn` key of an expanded dict definition.

```console
$ # 1. Directly under the key
$ uv run print_greetings.py --greet_fn greetings.Greetings_printer.print
Hello, world!
$ # 2. In an expanded dict definition under the `fn` key
$ uv run print_greetings.py --greet_fn.fn greetings.Greetings_printer.print
Hello, world!
```

When parameters are needed to initialize the object, they are given alongside the `fn` key.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.greetings Hi
Hi, world!
```
