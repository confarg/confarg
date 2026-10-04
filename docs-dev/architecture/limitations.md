# Limitations

What confarg does **not** do, and why — the boundaries that follow from the design rather
than from work nobody has done yet. A user hitting one of these is not hitting a bug.

Anything open and actionable — defects, parity gaps, refactors, ideas, questions — belongs on
the boards in [`../todo/`](../todo/README.md), not here. When a ticket closes and the answer
turns out to be "we will not do that", the reason moves into
[design decisions](design-decisions/README.md); when it changes what the library cannot do,
the boundary moves here.

## Expressions

- The grammar cannot express collection literals, slices, comprehensions or lambdas. The whitelist is the safety model, not an unfinished parser
  ([expressions](expressions/safety-model.md#safety-model)).
- No attribute of a value is reachable, only keys and indices: `${d.year}` on a YAML date or
  `${n.real}` on a number is a missing field, and no whitelisted function reads it instead
  ([expressions](expressions/safety-model.md#a-dot-reads-a-key-never-an-attribute)).
- A malformed expression contributes no dependency edges: it is not parseable, so nothing can
  be derived from it. The error surfaces at validation instead, with the expression text.
- `--config.<path>+` fragments keep their **bare** references anchored at the merged root, not
  at the mount point; a node-relative `${.x}` works there, because it is resolved once the
  element has an index ([expressions](expressions/reference-anchoring.md#reference-anchoring)).
- A node-relative reference counts *path segments*, and a list index is one: from
  `dbs.0.url`, `${..host}` names the list rather than the mapping holding it
  ([expressions](expressions/reference-anchoring.md#reference-anchoring)).
- A merged dict is no longer uniformly root-anchored: `${.x}` is preserved through `merge()`
  and `dump_file()` on purpose, so a dumped fragment stays position-independent, and so is
  `${::['web-1']}`, which no plain path spells
  ([expressions](expressions/reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path)).
- A non-string key at the document root is not reachable: `${::[0]}` reads the root key `"0"`.
  Below the root the subscript's fallback indexes by the integer, but the root has no node to
  index ([expressions](expressions/reference-anchoring.md#implementation-constraints)).
- A reference to a whole node substitutes that node's *value*, so each referencing site is
  constructed separately: two fields referring to one struct hold equal, non-identical
  objects. There is no way to share one instance
  ([expressions](expressions/values-and-references.md#referencing-a-whole-subtree)).
- In a `resolve()`d dict those paths do alias one sub-dict, so mutating it in place reaches
  every site that referenced it. Inspect and dump the resolved dict; do not edit it.
- An expression may not read a node that holds it, even through a function that would not need
  its own value: inside `svc`, `${len(svc)}` and `${svc[k]}` are cycles. The dependency graph is
  built from syntax and cannot see what a function reads or which key `k` names
  ([expressions](expressions/resolution.md#a-reference-reads-everything-its-path-reaches)).

## Collections

- A whole value and a deeper key for the same field resolve last-write-wins, and the loser
  goes quietly. Only a `Callable` field's bare string survives the pair, being the shorthand
  for `{fn: …}`; at a union like `dict[str, str] | str`, where a scalar is legitimate but
  abbreviates nothing, `--d oops --d.c x` keeps only the subkey
  ([design decisions](design-decisions/whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides)).
- List deletion and negative indices need a base list to apply to: they are patches, and a
  patch has nothing to bite on in an empty document.
- Index-keyed lists must be gap-free, unless the element type is Optional — a gap would
  otherwise have to invent an element of an unknown type.
- A list is extended with the `+` suffix on argv and in config files, but not from the
  environment: an append never got an env spelling, though a delete did (FEAT-18).

## CLI front-ends

- A multi-token flag is spelled per framework: space-separated for vanilla/argparse/cyclopts,
  repeated for click/typer/cyclopts ([CLI adapters](cli-adapters/list-syntax-divergence.md#list-syntax-divergence)). The
  `--<config_flag>` flag is spelled the same way, so its multi-file run declines on click and
  typer and repetition is the spelling to use there
  ([CLI parsing](cli-parsing/config-file-flags.md#config-file-flags)). Only the
  spelling diverges: repeating such a flag accumulates in every front-end, and a bare
  `--<list>` clears the collection in every front-end
  ([CLI adapters](cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)).
- There is no end-of-options separator: a bare `--` is an ordinary token everywhere. A value
  that starts with `--` is written `--key=--value`, the form every front-end honors
  ([design decisions](design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value)).
- A fixed-arity flag (`tuple[X, Y]`, namedtuple) takes one whole-value token — `--pair
  '[13, 42]'`, `--pair '{"x": 13}'` — everywhere except click and typer, whose options cannot
  vary their token count at parse time. They keep `--pair 13 42`, which is the spelling a CLI
  user reaches for, and decline the JSON one
  ([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)). Use a config file, an environment variable or
  the per-field flags (`--pair.x 13`) to set it whole under those two.
- The adapters read the CLI channel off the `argv` passed to `merge_*` / `from_*`, so it must
  be the list the framework parsed: `parser.parse_args(custom)` or `CliRunner().invoke(cmd,
  custom)` needs `argv=custom` too, since the default is `sys.argv[1:]`. A confarg flag the
  parse result holds and that argv does not spell raises `ConfargError`; a mismatch the parse
  result cannot show (argv spelling *more* than the framework parsed) is read as typed
  ([CLI adapters](cli-adapters/model.md#argv-is-the-only-writer)).
- A flag the adapters register and vanilla refuses (BUG-112, BUG-113) passes the framework's
  parse and is refused at merge, with vanilla's error, rather than at parse time with the
  framework's ([CLI adapters](cli-adapters/model.md#argv-is-the-only-writer)).
- The typer adapter needs `typer>=0.27` and reads two of its private modules
  (`typer._types`, `typer._click`): the option, choice and context classes it must subclass
  have no public spelling since typer forked click, so a typer release that moves them breaks
  the adapter rather than degrading it ([CLI adapters](cli-adapters/clicklike-seam.md#the-clicklike-seam)).
- A registered leaf as the *root* has no whole-value CLI spelling: the bare
  `--<cli_prefix> VALUE` form is refused — it names no field, and the root `.json` cast
  requires a JSON object there ([CLI parsing](cli-parsing/cli-prefix.md#cli_prefix)). It is
  spelled through its tag instead (`--<cli_prefix>.class uuid.UUID --<cli_prefix>.hex …`),
  or supplied by the file and environment channels.

## Subclasses

- `--help` lists a subclass's flags only once something has imported it: naming the class is
  what makes it visible, and nothing names it on a bare `--help`
  ([design decisions](design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)). Import the
  plugin module, or name the class earlier on the same command line.
- A subclass-only field spelled exactly like `union_tag` turns subclass dispatch structural:
  the tag's class-path route is unreachable at that position, so the subclass is selected by
  its fields, several matches are an error, and a subclass needing more fields than provided
  is refused — a build-time `ConfargWarning` names the substitution when the spelling is used
  ([CLI parsing](cli-parsing/casts-and-reserved-words.md#real-field-wins)).

## Callables and serialization

- Owning-class detection for `fn: Class.method` fails for lambdas and for functions defined in
  nested scopes; a callable confarg did not build may not be serializable at all
  ([callables](callables.md#round-trip)).
- Plain (non-dataclass) classes cannot be dumped by `dump()`. To serialize as fields, a class
  must store its `__init__` parameters as same-named attributes — confarg reads attributes, it
  does not replay constructor calls.
- Attribute docstrings used as `--help` text require the class source, which is unavailable for
  dynamically created classes ([CLI adapters](cli-adapters/flag-model.md#framework-neutral-flag-model)).
- A union leaf `__cast__` cannot name does not round-trip: an unregistered `Enum` beside a
  `str` variant, a `Literal` holding `Enum` members, a collection variant a fixed-arity sibling
  takes back. `dump()` writes the bare value and warns with the field path
  ([design decisions](design-decisions/a-stolen-leaf-dumps-with-its-cast.md#a-stolen-leaf-dumps-with-its-cast)).

## Remote sources

- **Nothing is cached.** A root `--config` location is read twice per run — once by the union-tag
  pre-scan in `_tags.py`, once by the pipeline — as local files already are (REF-26). Over the
  network that is two fetches. A caching handler is three lines through
  `register_scheme`, which is why no cache is built in.
- **No retries, no timeouts you can configure, no authentication.** The built-in `http`/`https`
  reader is `urlopen` with a fixed timeout; anything more — a proxy, a bearer token, a retry
  policy — is a handler the application registers over the built-in one.
- **Writing stays local.** `dump_file()` takes a filesystem path; there is no scheme registry for
  output.
- **No content sniffing.** The format comes from the location's suffix only, so an extension-less
  endpoint (`https://h/api/config?env=prod`) cannot be loaded even when it answers with a
  `Content-Type`.
- **A URL in `files=` must be a `str`.** `Path("https://h/x.yaml")` collapses the `//`, so
  passing a `Path` there cannot work.
- **A relative filename whose first segment holds a colon** (`weird:name.yaml`) reads as a
  scheme and must be written `./weird:name.yaml`
  ([config files](config-files/locations-and-schemes.md#locations-and-schemes)).
- **`file://` path translation is platform-dependent**, as `urllib.request.url2pathname` is: on
  Windows `file:/home/bob/c.yaml` names `\home\bob\c.yaml` on the current drive. A `file://` URL
  with a host other than `localhost` is refused rather than silently reinterpreted.
