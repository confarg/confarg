# Object factories

> [!TIP]
> Code for examples in this page can be found in [`examples/20_factories`](https://github.com/confarg/confarg/tree/master/examples/20_factories).

To close our tour of callables, let us look at a special but frequent case: configuring a factory — a callable that produces objects. Factories are useful when the objects to build require parameters that are only known at runtime, yet still need to be configured.

For example, say you write a configuration file for a deep-learning trainer. The trainer relies on an optimizer that you need to choose and configure. However, the optimizer of the deep-learning library you are using requires the model parameters to be passed at initialization. This means you cannot build the optimizer object at configuration time — you need to defer its instantiation until after the model is created. At the same time, you cannot simply pass the optimizer type, since you also want to specify other initialization parameters, such as the learning rate.

In short, you need some sort of object factory that can instantiate an object of the desired type with the right parameters.

Say our optimizers derive from a `BaseOptimizer` that takes model parameters and a learning rate as initialization arguments.

```python
class BaseOptimizer:
    def __init__(self, params: Iterable, lr: float) -> None:
        ...
```

Our configuration cannot declare a `BaseOptimizer` field, since it could not be instantiated. It can, however, declare a `BaseOptimizer` factory, like so:

```python
@dataclass
class Config:
    optimizer: Callable[[Iterable], BaseOptimizer]
```

You could write a factory yourself and configure it the usual way, as for any other callable. But confarg offers a simpler route: give the fully-qualified name of the class directly as the callable. A class is, after all, a callable that produces objects of its own type.

```console
$ uv run trainer.py --optimizer optimizer.Optimizer
Optimizer(lr=0.1, momentum=0.99)
```

Should we need to specify initialization arguments, we resort to the expanded dict definition. Note that the FQN of the class goes under the `fn` key, not `class` — we are not instantiating the class here, but pointing to the type itself as a callable factory — and that the extra arguments are bound to it with `bind`.

```console
$ uv run trainer.py --optimizer.fn optimizer.Optimizer --optimizer.bind.lr 0.25
Optimizer(lr=0.25, momentum=0.99)
```
