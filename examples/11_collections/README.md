# Collections

> [!TIP]
> Code for examples in this page can be found in [`examples/11_collections`](https://github.com/confarg/confarg/tree/master/examples/11_collections).

Configuration may contain collections of items in the form of lists or tuples.

## From the command line

From the command line, items of a collection are separated by space.

Take the following configuration:

```python
@dataclass
class Config:
    input: list[int]
```

Input can be provided from the command line like so:

```console
$ uv run list_of_ints.py --input 1 0b10
Config(input=[1, 2])
```

An empty list is obtained when no input is provided at all

```console
$ uv run list_of_ints.py --input
Config(input=[])
```

Tuples work similarly. Take this configuration:

```python
@dataclass
class Config:
    input: tuple[int, int]
```

Arguments can be provided like so:

```console
$ uv run pair_of_ints.py --input 1 2
Config(input=(1, 2))
```

With tuples, however, the number of elements has to match the target type.

```console
$ uv run pair_of_ints.py --input 1 # Error: too few elements
...
$ uv run pair_of_ints.py --input 1 2 3 # Error: too many elements
...
$ uv run pair_of_ints.py --input # Error: cannot be empty
...
```

Unless the tuple is unbounded:

```python
@dataclass
class Config:
    input: tuple[int, ...]
```

In that case, the initialization behavior is essentially the same as for lists:

```console
$ uv run unbound_tuple_of_ints.py --input 1
Config(input=(1,))
$ uv run unbound_tuple_of_ints.py --input 1 2 3
Config(input=(1, 2, 3))
$ uv run unbound_tuple_of_ints.py --input
Config(input=())
```


## From configuration files

Configuration file formats handle collections natively. For example,

```yaml
# pair_of_ints.yaml
inputs: [1, 2]
```

```console
$ uv run list_of_ints.py --config pair_of_ints.yaml
Config(input=[1, 2])
```

## From environment variables

Contrary to command line arguments and configuration file formats, environment variables do not have a standard way to represent collections. Their input is always passed as a single string.

We defer the discussion on how to populate collections from environment variables to the more general mechanism of specifying arguments as JSON in Tutorial XX.

## Precedence with a leaf type in a union

In case of a union with a leaf type, the leaf type coercion is always preferred if successful.

Take this configuration:

```python
@dataclass
class Config:
    input: int | list[int]
```

Providing a single integer always yields the `int` type:

```console
$ uv run int_or_list_of_ints.py --input
Config(input=[])
$ uv run int_or_list_of_ints.py --input 1
Config(input=1)
$ uv run int_or_list_of_ints.py --input 1 2
Config(input=[1, 2])
```

This can be surprising, especially when it seems to go against the [stealing rule](https://github.com/confarg/confarg/tree/master/examples/7_stealing_rule).

Take this configuration:

```python
@dataclass
class Config:
    input: str | list[bool]
```

A single string will always remain a single string, even if it could be cast to a bool.

```console
$ uv run str_or_list_of_bools.py --input
Config(input=[])
$ uv run str_or_list_of_bools.py --input on
Config(input='on')
$ uv run str_or_list_of_bools.py --input on off
Config(input=[True, False])
```

Of course, a list with a single item can be produced if the input doesn't coerce to the leaf type.

```console
$ uv run bool_or_list_of_strs.py --input hello
Config(input=['hello'])
```
