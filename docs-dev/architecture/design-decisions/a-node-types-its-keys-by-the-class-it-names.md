# A node types its keys by the class it names

A node that names a class types the keys below it by that class, on the command line and in the environment as construction reads them (BUG-233, BUG-236, BUG-110, BUG-113).
The node names it by an opener (`class`, `classfn`, `bind`, `call`) on a Callable, an `Any` or a field a typed call fills, or by the union tag on a struct, a taggable leaf or a union of structs.
Before, the walk typed a path by the declared types alone: one `str` segment below a Callable, so `--f.class Wrap --f.inner.class Mul --f.inner.factor 4` was an unknown argument; one token below a class's list argument, so `--f.class Joiner --f.parts a b` refused `b`; every subclass's or variant's fields folded below a base-typed field, so `--item.class S1 --item.inner.a 1` was unknown wherever the subclasses type `inner` apart.
The merge already read what a node names (`TypedAt.child`); the walk now asks the same decision-maker, `_naming.named_child`, and `_naming.named_variant` for the variant of a union it narrows to.
Every choice below is the maintainer's.

What a key is, mirroring construction:

- below an object opener or a tag, a member of the class it names, `_struct_member_type` (a `**kwargs` is the field `kwargs`, as construction reads it); the tag's and the opener's own value is a dotted-path leaf, below which nothing lies (`--leaf.class.junk` is refused, BUG-110);
- below `bind` or `call`, the target spec one key below (a Callable target), and under `args` the target's parameters, any name when it takes `**kwargs`; a nested target spec's outer `args` are the parameters of the callable it yields (`_callable.yielded_callable_path`), and a `call` whose target is a spec yields none, so its outer `args` are untyped;
- a key the class does not declare is refused at parse, `UnknownArgumentError` naming the flag, as a typo below a struct is.
  The environment leaves it to construction, as it does below a struct.

## Which naming types a key

The class construction reads at a node comes from the key's own layer or a lower one: a higher layer's opener replaces the node (`reads_as_new_value`), so a lower key below it never reaches construction.
So:

- **On argv, the naming written before the key**, as the loop's data holds it (`_ParseCtx.naming`): `--f.class J --f.parts a b`.
  If argv names the node nowhere (`_parse_cli._argv_named_nodes`), the nearest lower layer's: `files=`, `env_config`, the `CONFIG__*` mounts and argv's own `--config` files (the config level), then the environment.
  If argv names it only after the key, the key is untyped: the opener comes first, so `--f.parts a b --f.class J` refuses `b`, and a lower layer's class does not type a key argv's later opener builds.
- **In the environment, a naming anywhere in it** (`_parse_env._env_namings`): the environment has no order, its loop sorts by depth and then by name, so `APP_F__ALPHA` is typed by `APP_F__CLASS` as a file's `alpha` is by the `class` beside it.
  Else the config level's.
- **A file types itself**, at construction.

So the pipeline reads the layers lowest first (`_pipeline._lower_layers`): the environment's `CONFIG__*` pointers and argv's `--config` pairs (`_parse_cli._config_pairs_in`, before any value is typed), the config level, the environment over it, then argv over both.
A write names a node by an opener or a tag key, a `{…}` value holding one at any depth, a bare string where the node takes the callable shorthand, and a whole-field delete, which cuts the lower layers off.

Rejected:

- **argv's own namings only**, or argv and its `--config` files, what registration read before.
  No pipeline change, but a class a `files=` file or the environment names leaves argv's keys untyped, where construction builds them by it.
- **The naming argv ends with**, order-free, which the adapters could follow without a recording pass.
  A key written for an opener argv later restates is typed by the next one, and the token count then differs from what the first opener's class declares.
- **The naming in force when written, else the next one written**.
  Reads left to right, but a framework registers one arity per flag, so it could not follow two typings of one flag.
- **The environment's own sort order.**
  A parameter's name would decide whether its variable is typed.
- **A lower layer fills the gap until argv's opener**.
  Simpler to state, but types a key by a class that never builds it.

## No naming known

No naming written, a `${…}` value, a class that does not import (the parse swallows the failure, construction raises it), a tag naming no subclass: the walk answers what the declared types answer.
Below a Callable that is an untyped token at any depth (`_parse_cli._unnamed_spec_step`), the rule before PR-11's per-segment walk, so a nested spec's flags parse before its opener; below an `Any`, an `Any` node; below a struct or a union, the fold over its subclasses or variants.
A node reached through a spec holds no `locals` namespace, on the command line as in a file.

Rejected: **untyped at any depth everywhere below a Callable, with no class read**.
It fixes BUG-233 alone, and leaves a list argument to an index or a `.json` cast.

## The adapters

A framework splits argv into tokens by the arity registration gives each flag, before confarg's merge runs, so registration reads the layers vanilla's loop types argv by.
`populate_*` and `make_parser` take the option set `merge_*` takes (`**opts: Unpack[MergeOptions]`, [one option set](../pipeline/api-seams.md#one-option-set)), read the layers below argv (`_pipeline.below_argv`, best effort and silent: the merge raises and warns), and record what they read with the flags they registered to bind a run (`cli._sources.Registration`): on the argparse `Namespace` (`__confarg_registration__`, on every one, so a host spreading `**vars(ns)` drops it, as it drops the prefix key), on the click and typer options and command, in the cyclopts app's metadata.

- `merge_*` / `from_*` reuse a recorded option they are not given, and refuse one that differs from what registration read, its default included (`cli._sources.reconcile`): the framework split argv by those sources.
  `argv` is each step's own, and an option registration read nothing by differs from nothing (the environment where no prefix and no `env_config` read it).
  The environment is read again at the merge.
- Registration runs vanilla's own loop over argv (`cli._build._collect_loop_typed_specs`) and registers each flag the naming typed apart from the declared types in the shape of its widest occurrence: argv restating a naming can type one flag twice, and the framework must bind at least what vanilla takes.
  Vanilla's loop then asks what registration registered, not the type it consumes for, whether the framework bound the token after its run (`cli._collect._host_binds_run`), so a token it bound and vanilla did not take is the stray vanilla refuses.

Rejected:

- **Lenient registration**: every key below a spec of a class registration cannot see registered greedily, vanilla deciding the arity.
  No API change, but argparse swallows a host positional after such a flag and `--help` shows a wrong arity.
- **The merge's options win silently.**
  The framework already split argv by registration's sources, so an override types the flags by one class and builds them by another.
- **The sources move to registration alone**, `merge_*` taking none.
  No mismatch is possible, but `merge_*` stops taking the one option set.
- **Recording only a registration that read something besides the defaults.**
  The Namespace stays clean, but a merge-only option on it, today's usage, cannot be told from a foreign parser's, and types argv without that source silently.
- **A snapshot of the environment taken at registration.**
  Registration and merge always agree, but a variable set after the parser is built is never read, unlike `load()`.

## Sides earlier fixes chose, reversed

Five fixes made the front-ends agree by letting the class judge at `build()`; their bugs stay fixed, all five front-ends agreeing, and the side is now the parse's:

- BUG-28: an argument a target's signature does not declare merged and `build()` refused it; it is refused at parse.
- BUG-69: a sibling subclass's flag under a valid tag merged and `build()` refused it; it is refused at parse.
- BUG-84: with a tag, a field the variants type apart stayed the raw token; the tagged variant coerces it.
- BUG-86: with a tag naming a subclass that overrides a field's annotation, the base's typed it, and `load()` then refused the base's value in the subclass's field; the subclass's types it.
- BUG-214: a cast the tagged variant does not hold was refused by construction; `int` is no cast of that variant, so the flag is an unknown field.

## Cost

- A list argument written before its opener takes one token: `--f.parts a b --f.class J` refuses `b`.
- `populate_*` reads `files=` and the environment when the parser is built, and every adapter call that passed the sources to `merge_*` / `from_*` alone passes them to `populate_*` now (confarg has not shipped: no deprecation period).
- `merge()` holds a key below a named class coerced as a file holds it (`{'x': 4}`), where it held the token.
- A nested spec's arguments are listed in `--help` only once argv spells its opener.

## Precedents

jsonargparse puts every source on the parser (`default_config_files`, `default_env`, `env_prefix`), so its typing of `--model.init_args.*` reads a `class_path` a default config file gives; LightningCLI types `init_args` by the class `class_path` names, and refuses an unknown one at parse.
Click puts the environment at registration too (`auto_envvar_prefix`, an option's `envvar`).
Hydra types no override on the command line: `parts=[a,b]` is its own grammar, checked against a structured config at composition.
