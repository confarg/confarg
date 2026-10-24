# Plans live under `todo/`

The plans of settled but unbuilt designs sit in `docs-dev/todo/plans/`, beside the boards whose tickets cite them — not as a third top-level folder of `docs-dev/`, which is where PR-210 created the folder when FEAT-23 was settled, and which BUG-207's fix direction assumed would stay.

**Why.**
A plan's whole life runs through a ticket: a ticket on the boards says the work is missing, the plan says what was settled about it and in what order to build it, and landing the work deletes both — the ticket's file when it closes, the plan's when its rationale moves to `architecture/`.
Boards and plans are read together, so they live under one folder and one umbrella README; `architecture/` stays the separate destination, because it holds what outlives both.
The placement was settled by the maintainer while fixing BUG-207, whose own fix direction had been only to relink `AGENTS.md` to the top-level folder.

**Precedents.**
The four boards already share one `todo/` folder and one umbrella `README.md` instead of four top-level folders; and `architecture/` splits its notes into topic folders once a folder stops being readable whole (PR-238), so folders here follow the reader.
The closest external analogue is Python's `peps/`: proposals of every status share one folder, grouped by who reads them rather than by lifecycle stage.

**Cost.**
Every link from a plan into the notes gains one path level (`../../architecture/`), and a ticket citing its plan pays the same from the other side (`../plans/…`).
The boards' tooling is untouched: `index.py` reads only the four board folders, so `plans/` beside them is invisible to it, and `todo/README.md` carries the pointer that keeps a plan from being mistaken for a board.
