# Callables

> [!TIP]
> Code for examples in this page can be found in [`examples/17_callables`](https://github.com/confarg/confarg/tree/master/examples/17_callables).

Callables are accepted as leaf types. They deserve their own tutorial as they are a bit more involved than your average leaf type.

Take this configuration, that takes a `Callable[[str], None]` function:

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

The callable can be set as a function, by specifying its fully-qualified name.

```console
$ uv run print_greetings.py --greet_fn greetings.print_greetings
Hello, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn greetings.print_greetings
Hello, world!
```
-->

An expanded dict version can also be used, where the FQN of the function is specified under the `fn` key.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.print_greetings
Hello, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.fn greetings.print_greetings
Hello, world!
```
-->


## Classes

To use an instance of a class as a callable, we need to use an expanded dict declaration, specifying the fully-qualified name of the class under the usual `class` directive.

```console
$ uv run print_greetings.py --greet_fn.class greetings.Print_greetings
Hello, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.class greetings.Print_greetings
Hello, world!
```
-->

Additional keys needed to instantiate the class are put along the `class` key as usual.

```console
$ uv run print_greetings.py --greet_fn.class greetings.Print_greetings --greet_fn.greetings Hi
Hi, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.class greetings.Print_greetings --greet_fn.greetings Hi
Hi, world!
```
 -->


## Class method

Similarly to functions, class methods can also be specified as callables. In the simplest of cases, when an object can be instantiated without argument, the path to the class method is passed, either directly under the key, or under the `fn` key in an expanded dict definition.

```console
$ # 1. Directly under the key
$ uv run print_greetings.py --greet_fn greetings.Greetings_printer.print
Hello, world!
$ # 2. In an expanded dict definition under the `fn` key
$ uv run print_greetings.py --greet_fn.fn greetings.Greetings_printer.print
Hello, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn greetings.Greetings_printer.print
Hello, world!
$ uv run print_greetings_argparse.py --greet_fn.fn greetings.Greetings_printer.print
Hello, world!
```
-->

When parameters need to be passed to initialize the object, they are put along with the `fn` key.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.greetings Hi
Hi, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.greetings Hi
Hi, world!
```
-->
