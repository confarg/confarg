# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Framework-agnostic CLI building blocks."""

from confarg.cli.argparse._build import build_dynamic_flags, build_static_flags
from confarg.cli.argparse._spec import FieldMeta, FlagSpec

__all__ = [
    "FieldMeta",
    "FlagSpec",
    "build_dynamic_flags",
    "build_static_flags",
]
