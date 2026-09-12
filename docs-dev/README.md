# docs-dev

Documentation for contributors and coding agents working *on* confarg. It is internal: the
published site (`docs/`) is built for people *using* the library, and nothing here is copied
into it.

| Folder | Holds |
|---|---|
| [architecture/](architecture/README.md) | **Why** the code is the way it is: design choices, rejected alternatives, trade-offs, invariants, vocabulary, source map. The single source of truth for rationale — docstrings must not repeat it. |
| [todo/](todo/README.md) | **What is left to do**: bugs, desirable features, refactors, and questions for the maintainer. The place to file drive-by findings instead of silently fixing or forgetting them. |

The two are complements: a ticket describes work; closing it usually leaves a decision, and
the decision belongs in `architecture/`.

Start at [architecture/README.md](architecture/README.md) — it carries the reading guide that
maps source modules to documents, so you can open only what your change touches.

## Where things go

| What you have | Where it goes |
|---|---|
| A contract: arguments, return value, errors, footguns, an example | The docstring |
| A reason, a trade-off, a rejected alternative, an invariant | `architecture/` |
| Something broken, missing, or ugly that you are not fixing right now | `todo/` |
| A question only the maintainer can answer | `todo/questions.md` |
| Anything a *user* of confarg needs | `README.md`, `docs/`, `examples/` |
