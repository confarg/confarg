# Every mount point has a help entry

`build_static_flags` registers `--config.<path>` for every mount point of the target, at any depth: a struct, a dict, or a union whose variants are all structs, wherever the type walk reaches one.
`config_subkeys=False` turns all of them off at once, leaving the root `--config` alone (BUG-88).

`--config.<path>` is a projection of the configuration tree onto filenames ([mount keyword](mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)), and the parse already accepts a mount at any depth (`_parse_cli._check_mount_subpath`).
A projection that stopped at the root's own fields made every deeper mount point work but stay invisible, the same gap BUG-50 and BUG-70 closed for a dict field and a union field one level up.

The listing is read off the walk that checks a mount, never off a traversal of its own (`cli._build._collect_subconfig_specs`): the names a node declares are `_parse_cli._member_names` — a union's variants' and a subclass's included — and each name is typed by every branch `_parse_cli._field_types` takes to it, from the same `_walk_target` the mount check resolves against.
So `--help` lists no mount point the parse refuses: below a field the subclasses type differently the walk answers `str` and the listing stops, as vanilla does.
A union root's variant fields, a field only a subclass declares, a struct held by a namedtuple field and a `**kwargs: Struct` parameter (a dict to the walk) are all listed for that reason, not by special cases.
The walk descends below every node that declares names, listed or not, because a namedtuple or a `str | Struct` holds no fragment while its struct member does.

A node already on the path — every struct and namedtuple it is walked as entered above it — is listed but not entered, so a type that holds itself (`child: Node | None`) lists `--config.child` and not `--config.child.child`; the flag walk stops at the same node ([a node already on the path is not entered](a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered)).
The deeper mount still works; it is only absent from `--help`, as an index or dict-key mount is, which argv registers when typed ([static and dynamic flags](../cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)).

- Cost: one more `--help` line per mount point below the root.
  The field flags already list every field of every nested struct, so the entries grow with the tree the reader is already shown.
- Precedent: jsonargparse gives each nested dataclass group its own `--<group> CONFIG` entry, "Path to a configuration file".
  Before PR-13, confarg's own argparse integration registered the entries recursively too (`_register_subconfig_flags`); PR-13 kept only the root's fields to keep `--help` short.

Rejected: **the root's own fields only**, as PR-13 left it.
The mount point is accepted and undiscoverable, the one combination a `--help` exists to prevent.

Rejected: **a depth gate** (`config_subkeys` taking a depth).
It is a knob for a noise level no other channel has, and a reader of a gated `--help` still cannot tell a mount point below the gate from one that does not exist.
