# A node already on the path is not entered

The registration walks enter no node already on their path. A node is a struct or a namedtuple, the two shapes a walk enters by their members' names, and it is on the path when every struct and namedtuple the field's type is walked as (`Optional` aside, a union spread into its variants) was entered above it. The node keeps its own flags, and its members get none: a type that holds itself (`child: Node | None`) registers `--a` and `--child` (the whole value), and neither `--child.a` nor `--child.child.a` (BUG-224). The deeper flags are registered when argv types them, at the depth vanilla reads them, in the shape the walk would give them there ([static and dynamic flags](../cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)).

One decision-maker answers for both walks that recurse through the type: `cli._build._Descent.into`, asked by the flag walk (`_specs_for_field`, `_collect_namedtuple_specs`) and by the mount-point listing (`_collect_subconfig_specs`). The listing stopped at a repeated struct before the flag walk did ([every mount point has a help entry](every-mount-point-has-a-help-entry.md#every-mount-point-has-a-help-entry)), but it counted only structs, so a namedtuple that holds itself sent it into the same `RecursionError`. Since a node counts a namedtuple too, `--help` lists `--config.child` once, as it lists `--child` once.

The dynamic half is the same walk again with the stop lifted along each typed path (`_Descent.typed`): below a node already on the path, the walk continues wherever argv types a flag deeper still, and stops everywhere else, so it is bounded by the deepest typed flag. Of what it registers, only the typed names the static walk did not reach are kept (`_collect_unentered_argv_specs`). They carry no group, as every argv-scanned flag does. It runs before the other argv scans, since the static flags it stands in for are loaded before every dynamic one, and a static spec wins over a dynamic one of the same name.

A subclass stands at its base's path, so the subclass walk passes the base's descent on unchanged. A cycle through a subclass (`Sub(Base)` holding `kid: Base | None`) stops at `kid`, since `Base` is on the path.

- Cost: `--help` shows the recursive field's whole-value flag and not its members, so a reader learns `--child.a` exists from `--a`, one level up. Registration walks the type twice more when argv types any flag.
- Precedent: jsonargparse (4.52) lists `Optional[Node]` as `--n.child CHILD` with a `--n.child.help` and no member flags, and still parses `--n.child.child.a 5`.

Rejected: **unroll one level** (`--child.a` static, `--child.child.a` typed). The cut lands one level deeper, the walk costs a level more per recursive field, and the mount-point listing would have to move with it or disagree with the flags.

Rejected: **a depth knob**. It is the [depth gate](every-mount-point-has-a-help-entry.md#every-mount-point-has-a-help-entry) the mount-point listing already turned down: a reader of a gated `--help` cannot tell a flag below the gate from one that does not exist.
