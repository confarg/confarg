# A shadowed tag warns on use

A member that owns the union tag's spelling makes the tag's class-path dispatch unreachable
at that position, and the member's value selects the concrete class structurally instead
([CLI parsing](../cli-parsing/casts-and-reserved-words.md#real-field-wins)). That trade-off
is accepted silently only where the tag was never a real alternative — a struct with no
subclasses, a struct nobody dispatches. Where it was, `build()` emits a `ConfargWarning` the
moment a tag-shaped key is consumed by a member: once per dispatch position, naming the
field path, what the fields select, and the rename-or-`union_tag` remedy. The precedent is
the env channel's unknown-variable warning (BUG-90): non-fatal surprises are named when they
happen, and filterable as a category.

Rejected alternatives:

- **Warn on the collision itself, whenever a walked type owns the tag's spelling.** Catches
  intent even when the spelling is never used, but fires on every `load()` of a plain struct
  with a field named `class` — exactly the "plain structs that never use a union" the
  member-wins rule refuses to break, now warned at them on every run.
- **Keep it silent.** The structural selection can pick a subclass the user did not mean
  (their class-path value matched a sibling's field), and nothing would name the surprise;
  the remedy would stay buried in the architecture notes.
- **Deduplicate the two dispatch positions.** A union whose variant itself dispatches
  consumes the key at both levels; one warning per position says two true things ("the
  variant is selected structurally", "the subclass is selected structurally"), and deduping
  would need per-build state the recursion does not carry.
