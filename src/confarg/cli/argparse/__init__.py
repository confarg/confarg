# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Argparse integration for confarg.

Public API
----------
- :class:`FlagSpec` — framework-agnostic description of one CLI flag
- :class:`FieldMeta` — per-field metadata (help text, metavar)
- :func:`build_static_flags` — collect flag specs from a dataclass type
- :func:`build_dynamic_flags` — collect flag specs discoverable from partial argv
- :func:`load_flags_into_parser` — load specs into an :class:`argparse.ArgumentParser`
- :func:`populate_parser` — one-shot: build + load (+ optional dynamic extension)
- :func:`from_namespace` — construct a dataclass from a parsed :class:`argparse.Namespace`
- :func:`setup_completion` — enable tab-completion (requires ``argcomplete``)
"""

from confarg.cli.argparse._build import build_dynamic_flags, build_static_flags
from confarg.cli.argparse._completion import setup_completion
from confarg.cli.argparse._namespace import from_namespace
from confarg.cli.argparse._register import load_flags_into_parser, populate_parser
from confarg.cli.argparse._spec import FieldMeta, FlagSpec

__all__ = [
    "FieldMeta",
    "FlagSpec",
    "build_dynamic_flags",
    "build_static_flags",
    "from_namespace",
    "load_flags_into_parser",
    "populate_parser",
    "setup_completion",
]
