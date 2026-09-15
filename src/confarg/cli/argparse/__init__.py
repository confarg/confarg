# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Argparse integration.

The framework-neutral half — :class:`~confarg.cli.FlagSpec`,
:class:`~confarg.cli.FieldMeta`, :func:`~confarg.cli.build_static_flags` and
:func:`~confarg.cli.build_dynamic_flags` — lives in :mod:`confarg.cli`; this package holds
only what speaks :mod:`argparse`.

Public API
----------
- :func:`load_flags_into_parser` — load specs into an :class:`argparse.ArgumentParser`
- :func:`make_parser` — build a parser pre-populated for a target type
- :func:`populate_parser` — one-shot: build + load (+ optional dynamic extension)
- :func:`merge_namespace` — merge all sources into a raw dict from a parsed :class:`argparse.Namespace`
- :func:`from_namespace` — construct a dataclass from a parsed :class:`argparse.Namespace`
- :func:`setup_completion` — enable tab-completion (requires ``argcomplete``)
"""

from confarg.cli.argparse._completion import setup_completion
from confarg.cli.argparse._namespace import from_namespace, merge_namespace
from confarg.cli.argparse._register import load_flags_into_parser, make_parser, populate_parser

__all__ = [
    "from_namespace",
    "load_flags_into_parser",
    "make_parser",
    "merge_namespace",
    "populate_parser",
    "setup_completion",
]
