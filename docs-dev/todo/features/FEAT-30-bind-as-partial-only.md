---
filed: 2026-10-06
where:
  - src/confarg/_callable.py
effort: M
risk: medium
impact: config
severity: major
blocked_by: [FEAT-29]
---
# FEAT-30 — `bind:` yields a partial of its target; `fn:` and the `bind:` kwargs form are removed

`bind: T` with siblings returns `functools.partial(T, **siblings)`. `bind:` takes a target
string or a target dict, never a kwargs dict. The `fn:` opener and the `fn` + `bind` kwargs form
are removed.

Breaking for configuration (`impact: config`). Before removal, decide with the maintainer whether
the old forms stay with a deprecation warning for one release, or are removed outright. The
mapping for a migration note:

| Old | New |
|---|---|
| `f: {fn: pkg.g, bind: {a: 1}}` | `f: {bind: pkg.g, a: 1}` |
| `f: {fn: pkg.Cls, bind: {a: 1}}` (factory) | `f: {bind: pkg.Cls, a: 1}` |
| `f: {class: pkg.Cls, x: 1}` | `f: {class: pkg.Cls, x: 1}` (unchanged) |
| `f: {call: pkg.g, a: 1}` | `f: {call: pkg.g, a: 1}` (unchanged) |

Depends on FEAT-29 so that `class:` is settled before `bind:` takes over the partial role.
