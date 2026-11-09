# Plan — Say what confarg is for, and let a newcomer reach it

**Drafted:** 2026-11-09 · **Subject:** confarg's value proposition against the libraries it competes with, and the work that makes it visible · **Status:** direction agreed with the maintainer on 2026-11-09; FEAT-63 and FEAT-65 still need their design pass

## Context

[The comparison page](../../../docs/comparison.md) set confarg beside jsonargparse, OmegaConf, Hydra, Dynaconf, pydantic-settings and tyro, running each at its current release.
Its findings shape this plan.

### What only confarg does

In those runs, confarg was the only library that did all of these at once: build the user's own class with no base class, pick a union member from the keys it is given, build a subclass the data names, recompute a value an expression derives after a command-line override changed its input, include one file from another, load a file at a nested key, and append to a defaulted list.
Each competitor covers a part, at a cost confarg avoids: Hydra owns `main`, pydantic-settings requires `BaseSettings`, OmegaConf returns a `DictConfig`, jsonargparse is the parser.

Three of those have no real equivalent elsewhere:

- **Arithmetic in a value, with nothing registered**, over a whitelisted subset of Python, resolved after every layer is merged.
  OmegaConf and Hydra need a resolver registered in Python; jsonargparse re-resolves after a flag only in its experimental `omegaconf+` mode.
- **References anchored to the file that wrote them** (`${.host}`, `${::key}`), so a fragment works wherever it is mounted, which Hydra users get only by switching to relative interpolation.
- **Flags added to the CLI the application already has**: argparse, click, typer, cyclopts.
  Every other library either is the parser or has none.

### Where it loses

- **jsonargparse covers most of the same ground**, matured, with LightningCLI built on it.
  confarg's lead over it is real but incremental — the adapters, the expressions, `__include__` and file-relative references, list deletes and index patches — and nothing a newcomer reads says so.
- **The largest markets are out of reach by scope:** secret stores, `.env` and cloud sources (pydantic-settings, Dynaconf), sweeps and run directories (Hydra), pydantic models (FEAT-63), and Python before 3.12.
- **The pitch argues against the product.**
  "Not a framework, minimal footprint" is true of the Python code an application writes, and false of the configuration language a user learns: `+`, `-`, `__base__`, `__cast__`, `.json`, `class`, `classfn`, `bind`, `call`, `locals`, `::`, dot runs.
  That language is the value, and no single page shows it.
- **The front door is the weakest part.**
  The README quick tour does not run (BUG-322), the landing page renders its note and install tabs as text (BUG-321), and `confarg.load()` answers `--help` with `UnknownArgumentError` (FEAT-65).
  A newcomer meets all three in the first five minutes, while the internals are held to a standard few libraries meet.

## Decisions

| Decision | Choice |
|---|---|
| Target user | An application with a CLI it already built on argparse, click, typer or cyclopts, whose configuration is nested and typed, holds interchangeable components chosen by configuration, is split across several files, and derives values from others — and that does not want a framework to own `main`. Training scripts that do not want Hydra, and operations tools, are the typical case. |
| Headline | Hydra-style composition and jsonargparse-style typing, inside the CLI the application already has, with expressions that recompute after an override. The README says this first, then why not jsonargparse, and links the comparison page (FEAT-64). |
| The language | Owned, not apologized for: one page lists every reserved key, op, cast and expression form (FEAT-66). "Not a framework" stays, as a statement about the application's code. |
| Front door first | The first five minutes are fixed before any feature: BUG-321, BUG-322, FEAT-65. |
| Ecosystem reach | pydantic models are the one gap worth closing now (FEAT-63): the most users reached for the least design, since pydantic publishes the fields as `__signature__`. |

## Not pursued, and why

When this plan closes, each of these moves to [limitations](../../architecture/limitations.md) or a design decision, so it is not proposed again.

- **Secret stores, `.env` files and cloud sources.**
  pydantic-settings and Dynaconf own that market, and their users are configured through the environment, not through composed files.
  `register_scheme()` already lets an application fetch a file from any store it can reach.
- **Sweeps, run directories and config groups.**
  They are what Hydra was designed around, and they need the entry point confarg refuses to own.
  `--config.db pg.yaml` is the group swap confarg offers.
- **Python 3.10 and 3.11.**
  The public API is written in PEP 695 syntax (`def load[T](...)`), which Python 3.11 cannot parse; supporting it means rewriting those signatures and testing two more interpreters, for a user who can choose jsonargparse instead.
- **Competing with tyro as a pure CLI generator.**
  FEAT-41, a tyro adapter, is the way in: tyro users keep tyro and hand one parameter to confarg.

## Build order

1. BUG-321 and BUG-322, which need no design.
2. FEAT-64 and FEAT-66, which can be written beside each other; FEAT-26 becomes FEAT-66's expressions section.
3. FEAT-65 and FEAT-63, each through its design pass first.

## How to tell it worked

- A reader of the README alone can say who confarg is for, and why they would pick it over jsonargparse.
- Every code block in the README and on the landing page runs as written, and the landing page renders its note and tabs.
- `confarg.load(Config, argv=["--help"])` prints the flags of `Config`.
- `confarg.load(Holder, argv=["--p.a", "4"])` builds `Pm(a=4)` for a pydantic model field `p: Pm`.
- No user-facing page leaves a reader to learn a reserved key or an expression rule from an error message.
