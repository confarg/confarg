# The mount keyword is spelled per channel

Mounting a configuration file at a path of the merged document is one operation
([config files](../config-files/mounting.md#mounting)) with three spellings, and the keyword differs in each:
`--config[.<path>]` on argv, `<PREFIX>CONFIG[__<PATH>]` in the environment, and `__include__` at
the node in a file. The path differs too — a dotted suffix on the flag, structural nesting in a
file. Both divergences are approved ([invariants](../invariants.md#cross-channel-parity)).

Each keyword is its own channel's idiom, which is the tie-break
[a divergence leans towards the affected backend's own idiom](divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom)
already sets:
`--config FILE` is the near-universal flag name, and `include` is what file formats call this.
Consistency of vocabulary *across* channels competes here with consistency *with each channel's own
ecosystem*, and for a name the user types the ecosystem wins. One vocabulary was never quite
available either: `config_flag` is a user keyword, so a file sentinel could not track it and stay
portable — a shared fragment that uses includes would spell them differently per application.

Rejected: **renaming the file key to `__config__`**. It puts one word in the documentation, but it
names the operation less honestly — the key splices a fragment in, it is not "the config" — and an
application passing `config_flag='conf'` still writes `__config__`, so the unification fails
exactly where it was supposed to pay.

Rejected: **renaming the flag to `--include`**. Genuinely one word, at the cost of the most
conventional flag name there is; `--include` already means "match this pattern" in grep, rsync, tar
and find, so it misleads rather than clarifies.

Rejected: **the suffix form, `--db.host.config FILE`**, which would read in the same order as the
file form — path first, keyword last. Its attractions are real: it would end confarg's only
*leading* operator, since everything else a user says about a node is said after the path
(`--db.json`, `--db.class`, `--items.1-`, `--tags+`); `--help` and completion would group by node,
where today each node's story splits between `--db.*` and `--config.db`; it continues the path the
user was already typing; and deciding it needs the parent's type, so a misspelled subpath would
fail at parse time instead of mounting silently and surfacing much later in `build()`.

Four costs decide it against:

- It collides where the feature matters most. `_segment_names_real_field` counts every segment
  under a dict as a real key ([real field wins over reserved words](real-field-wins.md#real-field-wins-over-reserved-words)),
  so `--plugins.config f.yaml` would set `plugins["config"]`, and a dict node could not be mounted
  without an escape spelling (`--plugins._config`, on the `_fn` precedent). The same holds for the
  locals namespace, whose member names are declared in files and therefore open — and
  `--config.locals FILE` is the documented CLI route to a local
  ([locals](../locals.md#declare-in-files-modify-anywhere)). Exempting this one word from
  real-field-wins instead would make `{"config": …}` writable in a file but not on argv: a new
  cross-channel gap, opened by a change meant to close one.
- The canonical decision spreads. Today it is `_parse_cli._addresses_key`: a string test that needs
  no type, read at two sites, running *before* field lookup. A suffix needs `detect_force_cast`'s
  shape — resolve the parent, then ask real-field-wins — and five readers would have to agree on
  it: vanilla, env, `cli/_collect.py`, the lenient `_collect_config_file_pairs`, and completion.
- Two new precedence rules with nothing to copy: `.config` against a trailing `.json` cast, and
  where `+` attaches. `--servers.config+` reads as "append at `servers.config`", which is not what
  it means, and no combined cast-plus-append spelling exists to follow.
- The tag pre-scan becomes a permanent heuristic. `_tags._partial_config_from_argv` reads
  `--config` files *before* the type walk, because a `class:` tag decides which subclasses exist
  ([a named tag is imported before registration](a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)).
  Under a suffix there is no way to tell which argv tokens name files without the type tree that
  reading them would change.

And the payoff would be ordering parity, not lexical parity: `--db.config` still asks a reader to
learn two words unless `__include__` is renamed too, and a file author indents rather than typing a
path, so the mental operation differs whichever way the flag reads. Its one real attraction —
deciding needs the parent's type, so a misspelled subpath would fail at parse time — no longer
distinguishes the two either: the prefix form runs the same walk *after* its interception
(`_parse_cli._check_mount_subpath`, one walk for vanilla, the adapters' rescan and the
environment's handler), so an invented mount key is refused at parse time rather than surfacing
much later as an unknown-field error from `build()` (BUG-50, closed). A union-of-structs mount
point gets a `--help` entry too, whose text says the fragment must name its variant with the tag
(BUG-70, closed).

What makes the prefix form principled rather than merely incumbent is that `--config.<path>` is not
a namespace with members of its own but a **projection of the configuration tree onto filenames**:
the same path you would write for a value, with a file as the value. Read that way it is as
coherent as `--db.host`, and it sits beside `--locals.*` as the second addressable pseudo-root.

- Cost: the mount stays the one leading operator, so the flag grammar is not uniform, and `--help`
  splits each node between `--db.*` and `--config.db`. A top-level field named `config` still
  forces a `config_flag=` rename (`_parse_cli._check_config_flag_conflict`): the root spelling
  collides under either convention, so flipping would not have bought that back.
- Precedents: `--config FILE` as a flag name and `include` as the file-side keyword are both
  widespread across configuration tooling. *(inferred — from the conventions of the formats and
  tools confarg's channels imitate; no systematic survey was made.)*

This decision settles the **spelling** only. What each route may mount — which fragment shapes,
which format options, and what splices — is one rule across the three, because all three go
through one resolver ([config files](../config-files/include-semantics.md#include-semantics)).
