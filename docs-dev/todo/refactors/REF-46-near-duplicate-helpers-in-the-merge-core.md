---
filed: 2026-09-24
where:
  - src/confarg/_parse_cli.py::_handle_delete_token
  - src/confarg/_parse_cli.py::_restart_restated_node
effort: S
risk: medium
needs_design: true  # routing the delete handler through _peek_nested fixes a delete under an appended item: a decision, not a refactor
impact: behavior
severity: trivial
---

# REF-46 — Two token handlers hand-roll the nested descent `_merge._peek_nested` was written for

`_handle_delete_token` (`_parse_cli.py`, the `for _p in parent_path` loop) and `_restart_restated_node` (its `node.get(part)` loop) descend `ctx.data` by exact key, where `_merge._peek_nested` — whose docstring asks the caller to "keep the two in step" — also navigates append-specs and reads a key by the identity the type gives it (`_met_key`).
The other two pairs of the original ticket, `_lookup_declared`/`_lookup_path` and the two CSV loaders, are closed.

Routing the delete handler through `_peek_nested(ctx.data, parent_path, ctx.at)` is not behavior-neutral (run 2026-11-12):

- `--items+ '{}' --items.-1.tags+ 7 8 --items.-1.tags.0-` on `items: list[Item]`, `Item.tags: list[int]`: today `Cannot delete index 0 from 'items[0].tags': the list has 0 element(s) (the list is empty).`; through `_peek_nested` it builds `C(items=[Item(tags=[8])])`.
  The handler picks `DELETE_AFTER` over `DELETE` by looking in the wrong node (the raw `items` key, not the appended item `_accumulate_list_delete` writes into), so the current error is a bug the routing would fix, and it wants a BUG ticket and a test of its own.
- `_restart_restated_node` also needs the `MergeAt` it ends on, which `_peek_nested` does not return: it would take a read-only sibling of `_merge._descend`.

Fix direction: file the delete-under-an-appended-item case as a bug, fix it by routing the delete handler through `_peek_nested`, then give the restart handler a read-only `_descend` twin that also returns `at`.
