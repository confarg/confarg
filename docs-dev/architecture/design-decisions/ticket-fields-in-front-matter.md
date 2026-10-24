# A ticket's fields live in YAML front matter

A board ticket opens with YAML front matter holding the fields a script reads — `filed`, `where`, `effort`, `risk`, `impact`, `severity`, `introduced_by` on a bug, and `needs_design`, `inferred` and `blocked_by` when they apply — and only those ([todo/README.md § Front matter](../../todo/README.md#front-matter)).
It replaced a preamble of bold `**Where:** … · **Filed:** …` lines that `docs-dev/todo/index.py` read with patterns.

The preamble was not failing at what it did: every sized ticket carried effort, risk and impact, and the script validated them.
An agent reading one ticket reads either form equally well.
What the preamble could not do was everything past that:

- **A value and its qualifier were one string.**
  Eleven efforts carried a parenthetical — seven of them the same "design pass; implementation not sized", which is a fact about the ticket and not about the size — and the `*(inferred …)*` marker rode inside the Where line.
  Now the value is bare, the recurring qualifier is a key (`needs_design`), and a one-off qualifier is a YAML comment on the same line: dropped by the parser, kept for the reader.
- **`Where` was prose**, wrapped over up to four lines, mixing paths, symbols, globs, shortened paths and phrases.
  As a list of repository-root paths with optional `::symbol` (pytest's node-id spelling), it answers "which open tickets touch the file I am about to edit?" (`index.py --where`), and it is checked against the tree, so a rename that orphans a ticket is reported by the next run instead of found by a sweep.
- **Dependencies were prose**, so nothing noticed when a blocker closed.
  `blocked_by` names open tickets, and an entry whose ticket closed is an error.

Precedents.
PEPs carry an RFC 822 header block that a script parses into the PEP index, the same role as `index.py`'s tables.
Kubernetes KEPs keep their metadata in a validated `kep.yaml` beside the prose.
Backlog.md, a Markdown task tracker built for coding agents, and MADR put it in YAML front matter.
Rust RFCs keep loose header bullets nothing validates, which is roughly where this repository was.

**YAML rather than TOML.**
YAML front matter is the convention across Jekyll, MkDocs, Obsidian, MADR and Backlog.md, and GitHub renders it as a table at the top of the file, where a TOML `+++` block (Hugo's spelling) shows as raw text.
TOML's edges — `tomllib` in the standard library, no implicit typing — matter little for eight keys whose values are dates, booleans, lists and enums chosen to avoid YAML's surprises (`none` stays a string; nothing is spelled `no` or `null`), and `pyyaml` is a development dependency already.

**Keys deliberately left out.**
No `id` or `title`: the filename and the heading hold them, and a third copy would drift from both.
No `status`: a ticket is open until its file is deleted.
No `priority`: it is derived from `severity`, `blocked_by` and `effort` ([ticket-severity-and-work-order.md](ticket-severity-and-work-order.md)), so a written one would drift.
No `board` or `type`: the folder says it.
No `component` or `labels`: `where` says where the work is.
No `author` or `updated`: version control knows.
No `related`: a "see also" is a link in the body, and no query needs it.

Cost: filing a ticket means writing YAML, and a `where` must name what exists, so a ticket filed against a module that is about to be created says so in a comment (`where: []  # a new console script`).
A code change that renames a file or a function a ticket names fails the `ticket-boards` pre-commit hook ([board-and-anchor-checks-run-in-pre-commit.md](board-and-anchor-checks-run-in-pre-commit.md)) — by design, and on the author of the change, not on whoever runs `index.py` next.
