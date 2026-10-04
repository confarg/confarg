# REF-81 — `90_integration/README.md` opens at h3 and sandwiches a lone h2 between h3 sections

**Where:** `examples/90_integration/README.md` · **Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

Every other tutorial README opens with an h1 title and the tip blockquote; this one starts at
`### Integration with CLI framework` with no title, and the `## Old help` heading sits
mid-document between h3 sections, inverting the hierarchy (h3 → h2 → h3). Found while fixing
REF-80, in the collapse of the double blank line just above that heading; the structure
pre-dates that change.

[BUG-46](../bugs/BUG-46-old-help-blocks-document-a-removed-api.md) tracks the stale API in the
`Old help` python blocks and REF-59 the hand-copied snippets; neither covers the heading
structure. Fix direction: open with an h1 like the sibling tutorials and level `Old help` with
the sections around it — or fold the section away entirely when BUG-46 rewrites its blocks,
since the folder is not in the site nav either way.
