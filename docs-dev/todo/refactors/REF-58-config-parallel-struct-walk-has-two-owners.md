# REF-58 — The config-parallel struct walk has two owners

**Where:** `src/confarg/_tags.py` (`_tags_from_config`), `src/confarg/cli/_build.py`
(`_collect_fn_paths_from_config`) · **Filed:** 2026-09-25
**Effort:** S · **Risk:** medium · **Impact:** none

Both functions walk a struct type in lockstep with a config dict, and it is the skeleton that is
spelled twice: the `_resolve_type` / `_is_struct` guard, `_struct_fields` inside the same
`except (ValueError, TypeError, NameError, AttributeError)`, the
`f"{prefix}.{name}" if prefix else name` join, and the recursion into struct-typed fields
through `merged.get(name, {})` behind an `isinstance(sub, dict)` guard. One collects union
tags, the other callable openers; what each adds on top is a per-field predicate.

Both answer the same question — *what does this config name?* — and both feed
`build_dynamic_flags` and shell completion
([04-cli-adapters.md#static-and-dynamic-flags](../../architecture/04-cli-adapters.md#static-and-dynamic-flags)),
so a node one walk visits and the other does not registers bind flags for a class whose tag
the other half cannot see. Fix direction: one shared generator in `_tags.py` yielding every
reachable `(path, struct_type, node_dict)` — `_build.py` already imports from `_tags`, so no
cycle — with both collectors reduced to per-node predicates. The differences to preserve while
collapsing: the union recursion and the self-tag line on the tags side, `_unwrap_optional` and
the absence of a union arm on the fn-path side.

Risk is **medium**: a node-coverage mistake stays silent in the adapters' dynamic registration
while vanilla, whose own type walk is separate, stays correct. Not
[REF-26](REF-26-config-files-parsed-three-times.md), which is about the same files being
*parsed* repeatedly; this is the *walk* over their contents being written twice.
