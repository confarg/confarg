# Binding arguments

> [!TIP]
> Code for examples in this page can be found in [`examples/18_bindings`](https://github.com/confarg/confarg/tree/master/examples/18_bindings).

When specifying a callable, we may want to bind some of its parameters to fixed values. This is done with the dedicated `bind` key.

## To functions

To bind a value to a function argument, we must use the expanded dict definition, where the FQN of the function is given under the `fn` key.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.print_greetings --greet_fn.bind.greetings Hi
Hi, world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.fn greetings.print_greetings --greet_fn.bind.greetings Hi
Hi, world!
```
-->

In configuration files, this translates as:

```yaml
# Use a function as-is (short form, leaf-type style)
greet_fn: greetings.print_greetings

# Use a function with bound arguments
greet_fn:
  fn: greetings.print_greetings
  bind:
    greetings: Hi
```

> [!NOTE]
> If the function has a `bind` argument that would conflict with the `bind` key, confarg accepts an alternative set of directives prefixed with `_`:
> ```console
> $ uv run print_greetings.py --greet_fn._fn greetings.print_greetings --greet_fn._bind.greetings Hi
> Hi, world!
> ```
> In that case, *all* directives of that callable must be drawn from the alternative set.

<!--
> ```console
> $ uv run print_greetings_argparse.py --greet_fn._fn greetings.print_greetings --greet_fn._bind.greetings Hi
> Hi, world!
> ```
-->

## To callable classes

As for functions, binding arguments to a callable class requires an expanded dict definition, where the FQN of the class is given under the `class` key.

```console
$ uv run print_greetings.py --greet_fn.class greetings.Print_greetings --greet_fn.bind.adjective beautiful
Hello, beautiful world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.class greetings.Print_greetings --greet_fn.bind.adjective beautiful
Hello, beautiful world!
```
-->

If the class needs initialization parameters, simply add them alongside the `class` key, as usual.

```console
$ uv run print_greetings.py --greet_fn.class greetings.Print_greetings --greet_fn.greetings Hi --greet_fn.bind.adjective beautiful
Hi, beautiful world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.class greetings.Print_greetings --greet_fn.greetings Hi --greet_fn.bind.adjective beautiful
Hi, beautiful world!
```
-->

In configuration files, this translates as:

```yaml
# Use a callable object as-is (short form, leaf-type style)
greet_fn: greetings.Print_greetings

# Use a callable object with parameter bindings (no initialization parameter)
greet_fn:
  class: greetings.Print_greetings
  bind:
    adjective: beautiful

# Use a callable object with initialization parameters and parameter bindings
greet_fn:
  class: greetings.Print_greetings
  greetings: Hi
  bind:
    adjective: beautiful
```

> [!NOTE]
> If the class has a `bind` argument in its `__init__` method that would conflict with the `bind` key, confarg accepts an alternative set of directives prefixed with `_`:
> ```console
> $ uv run print_greetings.py --greet_fn._class greetings.Print_greetings --greet_fn.greetings Hi --greet_fn._bind.adjective beautiful
> Hi, beautiful world!
> ```
> Again, *all* directives of that callable must be drawn from the alternative set.

<!--
> ```console
> $ uv run print_greetings_argparse.py --greet_fn._class greetings.Print_greetings --greet_fn.greetings Hi --greet_fn._bind.adjective beautiful
> Hi, beautiful world!
> ```
-->

## To class methods

When binding arguments to a class method, the expanded dict definition must once again be used, with the FQN of the method given under the `fn` key.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.bind.adjective beautiful
Hello, beautiful world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.bind.adjective beautiful
Hello, beautiful world!
```
-->

If the object needs initialization parameters, simply add them alongside the `fn` key, as usual.

```console
$ uv run print_greetings.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.greetings Hi --greet_fn.bind.adjective beautiful
Hi, beautiful world!
```
<!--
```console
$ uv run print_greetings_argparse.py --greet_fn.fn greetings.Greetings_printer.print --greet_fn.greetings Hi --greet_fn.bind.adjective beautiful
Hi, beautiful world!
```
-->

In configuration files, this translates as:

```yaml
# Use an object method as-is (short form, leaf-type style)
greet_fn: greetings.Greetings_printer.print

# Use an object method with parameter bindings (no initialization parameters)
greet_fn:
  fn: greetings.Greetings_printer.print
  bind:
    adjective: beautiful

# Use an object method with initialization parameters and parameter bindings
greet_fn:
  fn: greetings.Greetings_printer.print
  greetings: Hi
  bind:
    adjective: beautiful
```
