# Deleting items

> [!TIP]
> Code for examples in this page can be found in [`examples/17_removing_items`](https://github.com/confarg/confarg/tree/master/examples/17_removing_items).


An element of a collection can be removed by adding a `-` at the end of its key path.

## From the CLI

An element is removed by adding `-` at the end of its command line argument.

```console
$ uv run users.py --config users.yaml
Config(users=['alice', 'bob', 'claire'])
$ # Remove the first user
$ uv run users.py --config users.yaml --users.0-
Config(users=['bob', 'claire'])
$ # Remove the second last user
$ uv run users.py --config users.yaml --users.-2-
Config(users=['alice', 'claire'])
```

This works for any type of elements, not just leaf types.

```console
$ uv run transforms.py --config transforms.yaml
Config(transforms=[RandomNoise(p=0.5, mean=0.0, std=1.0),
                   RandomGamma(p=0.5, range=(0.8, 1.2))])
$ # Removing the first transform
$ uv run transforms.py --config transforms.yaml --transforms.0-
Config(transforms=[RandomGamma(p=0.5, range=(0.8, 1.2))])
```


As we saw in [Tutorial 14](https://confarg.github.io/confarg/examples/14_dictionaries/), referring to a particular elements by its index can be fragile, and dictionaries may be a helpful alternative. Hopefully, removing dictionaries items is possible too.

```console
$ uv run transforms_v2.py --config transforms_v2.yaml
Config(transforms={'random_gamma': RandomGamma(p=0.5, range=(0.8, 1.2)),
                   'random_noise': RandomNoise(p=0.5, mean=0.0, std=1.0)})
$ # Removing transform by name
$ uv run transforms_v2.py --config transforms_v2.yaml --transforms.random_gamma-
Config(transforms={'random_noise': RandomNoise(p=0.5, mean=0.0, std=1.0)})
```
