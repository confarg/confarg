# An op after a whole-field delete applies to nothing below

`--users- --users.0-` deletes the field, then index 0 of what is left, and nothing is left: the
pair fails as a lone `--users.0-` fails with no file. Every op written after a whole-field
delete, at or below its path, applies to nothing the lower layers hold
(maintainer-chosen, BUG-116). The ops alone then build the field, exactly as they do when no
layer sets it: `--users- --users.0 x` is `[x]`, `--users- --users+ x` is `[x]`, and
`--sec- --sec.a 9` is `a=9` beside the other fields' defaults. The mechanism is in
[deep merge](../pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it).

This is what lets a list be cleared and rebuilt from any channel, the environment included,
which has no whole-list spelling for a list of structs and no append:
`APP_USERS- APP_USERS__0=alice APP_USERS__1=bob` builds `[alice, bob]` whatever the file held,
as `APP_USERS__0=alice APP_USERS__1=bob` builds it when no file sets `users`.

- **Rejected: the later op replaces the delete** — what the code did from BUG-23 to BUG-116.
  `--users- --users.0-` built `[b]` and `--users- --users+ x` built `[a, b, x]` from a file
  `[a, b]`: the delete the user typed vanished without a word. Nobody chose it. BUG-23 added a
  branch replacing a *scalar* left by a whole value, so that a subkey after it would not crash,
  and the delete sentinel fell into that branch. BUG-77 then made the index delete — which
  still crashed on its own walk — go through the same branch, and recorded the side effect as
  the rule.
- **Rejected: the delete leaves an empty value.** `--users- --users.0 x` would then fail on an
  index past `[]`, while `--users.0 x` with no file builds `[x]`. The two spellings differ only
  by a delete of something no layer below holds any more. "Empty" would also need a meaning per
  type — a fixed tuple, a namedtuple, a struct — where "no layer set it" already has one.
- **Rejected: refusing the pair.** It is never silent, but it refuses the one spelling that
  clears a list and rebuilds it from the environment.
- Precedent: RFC 6902 (JSON Patch) applies its operations in order to the document, so an
  operation after a `remove` sees the path removed: an `add` below it fails, its parent being
  gone, and nothing the document held there comes back. confarg differs only in what ops on
  nothing build, which is its own rule for a field no layer sets.
