# Calls

> [!TIP]
> Code for examples on this page can be found in [`examples/21_calls`](https://github.com/confarg/confarg/tree/master/examples/21_calls).

In the last three tutorials, the configuration named a callable and the program called it.
Sometimes we want the configuration itself to make the call, and keep what it returns: a value computed from a file, or a callable that a factory prepares once.
This is what the `call` key does: it names a function, the `args` key beside it holds the function's arguments, and the field takes the function's return value.

Take this configuration for a text classifier:

<!-- snippet: classifier.py#Config -->
```python
@dataclass
class Config:
    num_labels: int = 2
    tokenize: Callable[[str], list[str]] = str.split
```

The program prints the number of labels, then tokenizes a sentence:

```python
print(f"{config.num_labels} labels")
print(config.tokenize("the dog and the cat"))
```

## Computing a value

The number of labels is not a choice: it follows from the file that lists them.
Rather than typing it, and risking a mismatch, we let a function count them:

<!-- snippet: labels.py#count_labels -->
```python
def count_labels(path: str) -> int:
    with open(path) as file:
        return sum(1 for line in file if line.strip())
```

`call` names the function, and `path` is given under `args`, as its argument.

```console
$ uv run classifier.py --num_labels.call labels.count_labels --num_labels.args.path labels.txt
3 labels
['the', 'dog', 'and', 'the', 'cat']
```

The field is still an `int`.
A plain value sets it as before, and what the function returns is checked against the annotation like any other value.

```console
$ uv run classifier.py --num_labels 7
7 labels
['the', 'dog', 'and', 'the', 'cat']
```

> [!NOTE]
> `--num_labels.args.path` is accepted whatever opens the call: the `--num_labels.call` flag, a configuration file (see [below](#in-configuration-files)), or an environment variable.
> Without `args`, `--num_labels.path` names nothing an `int` has, and is rejected as an unknown argument, as a misspelled flag would be.

## Calling a method of an object

Say the labels come from an annotation file instead, which gives the label of each sample, one per line.
The same label appears several times, and a class reads the file:

<!-- snippet: labels.py#Annotations -->
```python
class Annotations:
    def __init__(self, path: str) -> None:
        with open(path) as file:
            self.labels = [line.strip() for line in file if line.strip()]

    def count(self, *, unique: bool = False) -> int:
        return len(set(self.labels)) if unique else len(self.labels)
```

We want `Annotations(path="annotations.txt").count(unique=True)`.
In [Tutorial #18](https://confarg.github.io/confarg/examples/18_callables/), the `classfn` key named such a method, the keys beside it building its object.
Here, `call` names that `classfn` spec, and the method's arguments go under `args`, so the arguments of the object and of the method stay apart:

- `--num_labels.call.classfn` and `--num_labels.call.path` build the object;
- `--num_labels.args.unique` is an argument of the method.

```console
$ uv run classifier.py --num_labels.call.classfn labels.Annotations.count --num_labels.call.path annotations.txt --num_labels.args.unique true
3 labels
['the', 'dog', 'and', 'the', 'cat']
```

Without `unique`, the method counts every sample:

```console
$ uv run classifier.py --num_labels.call.classfn labels.Annotations.count --num_labels.call.path annotations.txt
5 labels
['the', 'dog', 'and', 'the', 'cat']
```

## Computing a callable

`call` works the same on a `Callable` field: the function it names is called once, when the configuration is loaded, and what it returns is the callable.
This is the place for a factory that has work to do before the callable can be used, such as reading a list of words the tokenizer must drop:

<!-- snippet: labels.py#make_tokenizer -->
```python
def make_tokenizer(stopwords: str) -> Callable[[str], list[str]]:
    with open(stopwords) as file:
        ignored = set(file.read().split())

    def tokenize(text: str) -> list[str]:
        return [word for word in text.split() if word not in ignored]

    return tokenize
```

```console
$ uv run classifier.py --tokenize.call labels.make_tokenizer --tokenize.args.stopwords stopwords.txt
2 labels
['dog', 'cat']
```

Compare with `bind`, from [Tutorial #19](https://confarg.github.io/confarg/examples/19_bindings/): `--tokenize.bind labels.make_tokenizer` would make the field the factory itself, its `stopwords` argument bound, so that calling `config.tokenize(...)` would build a new tokenizer rather than split the sentence.
`bind` defers the call to the program; `call` makes it now.

## In configuration files

In configuration files, `call` is a key like the others, its arguments under `args` beside it:

<!-- snippet: classifier.yaml -->
```yaml title="classifier.yaml"
num_labels:
  call: labels.count_labels
  args:
    path: labels.txt
tokenize:
  call: labels.make_tokenizer
  args:
    stopwords: stopwords.txt
```

```console
$ uv run classifier.py --config classifier.yaml
3 labels
['dog', 'cat']
```

Since the file opens the call, the command line can change one of its arguments:

```console
$ uv run classifier.py --config classifier.yaml --num_labels.args.path annotations.txt
5 labels
['dog', 'cat']
```

Environment variables spell it the same way:

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_NUM_LABELS__CALL=labels.count_labels MYAPP_NUM_LABELS__ARGS__PATH=labels.txt uv run classifier.py
3 labels
['the', 'dog', 'and', 'the', 'cat']
```

## Where `call` is data

A `call` key opens a call only where the field could not hold it as data.
A `dict` field and a dataclass with a field named `call` keep the key as written.
An `Any` field reads every opener, `class` included, so it can hold any object a configuration spells.
A function parameter named `call` needs no special spelling: it sits under `args`, as every argument does.

On a typed field, `class` keeps the meaning it has had since [Tutorial #9](https://confarg.github.io/confarg/examples/9_child_configurations/): it picks the type to build, which must be the field's type or a subclass of it.
`class` says which type the field holds; `call` says how its value is computed.

## Saving the configuration

Saving the loaded object with `confarg.dump(config)` writes the value the call returned, `num_labels: 3`, not the call: it records what the program ran with.
To save how the value is produced instead, save the merged dictionary with `confarg.dump_file(confarg.merge(Config), "saved.yaml")`, which keeps every `call` as written.
