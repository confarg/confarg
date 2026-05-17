# Binding arguments

> [!TIP]
> Code for examples on this page can be found in [`examples/19_bindings`](https://github.com/confarg/confarg/tree/master/examples/19_bindings).

When specifying a callable, we may want to bind some of its parameters to fixed values. This is done with the dedicated `bind` key: it names the callable, and every other key beside it is an argument bound to it.

## To functions

To bind a value to a function argument, we use the expanded dict definition, where the FQN of the function is given under the `bind` key and the arguments alongside it.

```console
$ uv run print_greetings.py --greet_fn.bind greetings.print_greetings --greet_fn.greetings Hi
Hi, world!
```

In configuration files, this translates as — a function used as-is, in the short form:

<!-- snippet: greet_fn.yaml -->
```yaml title="greet_fn.yaml"
greet_fn: greetings.print_greetings
```

> [!NOTE]
> If the function has an argument named `bind` (or `class`, or `call`) that would conflict with the directive, confarg accepts an alternative set of directives prefixed with `_`:
>
> ```console
> $ uv run print_greetings.py --greet_fn._bind greetings.print_greetings --greet_fn.greetings Hi
> Hi, world!
> ```
>
> In that case, the `bind` argument is spelled plainly, and _all_ directives of that spec must be drawn from the alternative set.


## To callable classes

To bind arguments to a callable class, `bind` names the instance to bind them to: a nested spec, where the FQN of the class is given under the usual `class` key. The arguments of the call sit beside `bind`, as for a function.

```console
$ uv run print_greetings.py --greet_fn.bind.class greetings.Print_greetings --greet_fn.adjective beautiful
Hello, beautiful world!
```

If the class needs initialization parameters, simply add them alongside the `class` key, inside the nested spec.

```console
$ uv run print_greetings.py --greet_fn.bind.class greetings.Print_greetings --greet_fn.bind.greetings Hi --greet_fn.adjective beautiful
Hi, beautiful world!
```

In configuration files, this translates as — a callable class used as-is:

<!-- snippet: greet_fn_class.yaml -->
```yaml title="greet_fn_class.yaml"
greet_fn:
  class: greetings.Print_greetings
```

> [!NOTE]
> If the class has a `bind` argument in its `__init__` method that would conflict with the directive, the nested spec can use the alternative set of directives prefixed with `_`:
>
> ```console
> $ uv run print_greetings.py --greet_fn.bind._class greetings.Print_greetings --greet_fn.bind.greetings Hi --greet_fn.adjective beautiful
> Hi, beautiful world!
> ```
>
> Each spec picks its own set: here only the nested `class` spec, whose keys are the constructor's, is spelled with `_`.
