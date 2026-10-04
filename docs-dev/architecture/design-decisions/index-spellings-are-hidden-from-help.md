# Index spellings are hidden from help

A flag whose own segment is a bare index — `--pt.0`, `--pt.-1`, `--pair.1` — is accepted
by every front-end but kept out of its `--help` listing. One `FlagSpec.hidden` field,
honoured by each adapter through its framework's own mechanism (argparse:
`help=argparse.SUPPRESS`; click and typer: `hidden=True`; cyclopts: `show=False`), so the
flag parses and completes exactly as before and only the listing changes.

The scope is the index spellings of a *fixed-length* sequence: a namedtuple's per-index
sub-flags (positive and negative, BUG-80) and a `tuple[X, Y]`'s element patches, found by
the argv scan when typed. A dict key that happens to be digits stays visible — it is a
key, not a position — and whether a varlen collection's element flags should follow is an
open question (Q-2).

Why hide at all: the index spellings are patch syntax, not a discoverable interface.
`--pt.x` names the field; `--pt.0` and `--pt.-1` name the same field another way, and a
namedtuple registers all three statically, so an n-field namedtuple was showing 2n index
lines before the negative spelling doubled them again. The whole-value flag and the name
spellings are the interface `--help` should advertise; the patch spellings are for the
user who already knows them, and the fixed tuple already agrees: its element flags are
dynamic, so they only reached help when the same argv spelled them.

The cost is discoverability: a reader of `--help` no longer sees that `--pair.0` exists.
That is the same trade every framework's own `hidden`/`SUPPRESS` mechanism takes, and the
name spelling is always visible beside it.

Precedent: argparse's `SUPPRESS`, click's `hidden=True` and cyclopts's `show=False` all
exist precisely for flags a tool accepts but declines to advertise; using the mechanisms
the frameworks ship means completion and parsing keep their native behavior, and only the
rendering is confarg's to decide.
