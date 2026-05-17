---
icon: lucide/sigma
---

# Derive a value the configuration does not contain

Some values are not choices. They are consequences of other choices, and writing them by hand is
an invitation to write them inconsistently.

The running example on this page: a dataset reads its labels from somewhere, and the model needs
to know **how many labels there are**. Nobody wants to type that number — it is already implied by
the labels — but the model configuration cannot be built without it.

Which recipe applies depends on one question only: *where does the value live?*

## The value is elsewhere in the configuration

Reference it. An expression is resolved after all sources are merged, so overriding the input on
the command line recomputes the output.

```yaml
data:
  batch_size: 32
model:
  batch_size: ${data.batch_size}
```

See [Tutorial 21](https://confarg.github.io/confarg/examples/21_expressions/) for expressions, and
[Tutorial 22](https://confarg.github.io/confarg/examples/22_variable_scopes/) for what a bare
reference means in a file that is mounted somewhere.

## The value is in a file `confarg` can read

If the labels sit in a JSON, YAML, TOML or CSV file, the dataset object does not have to be the one
that reads them. Let the configuration read them, and the count is an expression: `len` is part of
the expression whitelist.

```yaml
data:
  labels: { __include__: labels.json } # ["dog", "cat", ...]
model:
  num_labels: ${len(data.labels)}
```

`__include__` contributes *any* top-level value, not only a mapping, so a JSON list or a CSV column
is a legitimate thing to include. The dataset now receives the labels themselves rather than a path
to them, and `num_labels` is derived wherever the labels come from.

Two caveats that are easy to trip over:

* **An include path cannot be an expression.** Includes are resolved while files are being loaded,
  before anything is merged, so `__include__: ${labels_file}` can never work. To keep the file
  selectable per run, mount it from outside instead — `--config.data.labels+ labels.json` on the
  command line, or `MYAPP_CONFIG__DATA__LABELS` in the environment. Note the trailing `+`: the
  plain `--config.<path>` form loads a configuration layer and requires a mapping at the root,
  while the `+` form contributes an item and accepts a list.
* **A CSV must land on a real field**, never in the `locals:` namespace. CSV carries no types, so
  its cells would have nothing to be coerced against.

See [Tutorial 11](https://confarg.github.io/confarg/examples/11_include/) for includes and
[Tutorial 10](https://confarg.github.io/confarg/examples/10_nested_configurations/) for mounting a
file at a key.

## Two sub-configurations must share one value

When you compose two stand-alone configurations, they often duplicate a field — one `project_id`
across two pipeline steps, one `batch_size` in the data pipeline and in the model. You know they are
one knob; neither of the reused types does.

Declaring a local variable is the reader's tool, in the reader's file. To express it from the
*application* instead, ship a configuration fragment with your package and pass it first, so that
every other source still overrides it:

```yaml
# defaults.yaml, shipped with your application
data:
  batch_size: ${batch_size}
model:
  batch_size: ${batch_size}
```

```python
config = confarg.load(Config, files=[package_defaults, *user_files])
```

`--batch_size 64` now sets both, and `--model.batch_size 64` still overrides just the one — the
fragment is the lowest layer, not a rule.

## The value only exists at runtime

Sometimes nothing can read the labels but your own code: a format `confarg` does not parse, a
directory to scan, a database to query. Resolution finishes *before* construction begins, so no
value produced by a constructed object can flow back into an expression. The pipeline will not do
this for you — but it stops in the middle on purpose, and you can do it in three lines.

Take the hardest version: the labels come from a query, and the credentials for that query are
themselves configuration.

```python
@dataclass
class Config:
    db: DbConfig
    model: ModelConfig # needs num_labels
```

```python
raw = confarg.merge(Config, argv=argv)                 # every source merged, ${...} still literal
db = connect(confarg.build(DbConfig, raw["db"]))       # resolve and build the db subtree only
raw.setdefault("model", {}).setdefault("num_labels", db.count_labels())
config = confarg.build(Config, raw)                    # resolve again, now with num_labels present
```

The credentials are fully merged and resolved by the time you connect, so they can come from a
file, the environment or the command line like anything else — and you keep the connection, which
you were going to open anyway.

What each step assumes:

* `confarg.build(DbConfig, raw["db"])` is the cheap route, and it is valid as long as the
  expressions *inside* `db` do not reach outside it. References in a merged configuration are
  anchored at its root, so a subtree lifted out of it can no longer resolve `${elsewhere.value}`.
  If it must, resolve the whole document instead with `confarg.resolve(raw)` and build `DbConfig`
  from `resolved["db"]` — which in turn requires that nothing *else* in the configuration
  references the value you have not computed yet.
* Inject into the **merged** dict, not the resolved one, and build from it. Re-resolving is what
  makes the injected value visible to other expressions, so `${model.num_labels * 4}` elsewhere
  works. (A resolved dict also aliases the nodes that were referenced in it, so it is meant to be
  inspected and dumped rather than edited.)
* `setdefault` keeps every source winning: a user who passes `--model.num_labels 3` gets 3.
  Assign instead if the derived value must win, or compare and raise if a disagreement is a
  configuration that cannot run.

## Or keep it out of the configuration

Before reaching for any of the above, consider whether the value is configuration at all.
`num_labels` is a fact about the data, not a knob: nobody chooses it, and offering `--model.num_labels`
in `--help` advertises a flag whose only correct value is computed.

A `Callable` field lets you configure everything that *is* a choice and supply the rest at the call
site:

```python
@dataclass
class Config:
    model: Callable[..., Model]
```

```yaml
model:
  fn: myapp.models.Transformer
  bind:
    hidden: 512
    dropout: 0.1
```

```python
config = confarg.load(Config)
model = config.model(num_labels=len(dataset.labels))
```

Bound arguments are checked against the real signature and built through the same machinery as any
other configuration value, so `--model.bind.hidden 1024` still works. See
[Tutorial 20](https://confarg.github.io/confarg/examples/20_factories/).

## Which one

| Where the value lives | Recipe |
|---|---|
| Elsewhere in the configuration | `${...}` |
| In a file `confarg` reads | `__include__` (or `--config.<path>+`) and derive with `${len(...)}` |
| In the application's knowledge of the composition | a fragment shipped with the package, passed first in `files=` |
| In your code, at runtime | stage it: `merge()`, build the part you need, inject, `build()` |
| In your code, and it is not a choice | do not configure it — bind the rest and pass it at the call site |

`confarg` has no way to call your own function from inside an expression, so a derivation only your
code can compute is staged by the application or not expressed in the configuration at all.
