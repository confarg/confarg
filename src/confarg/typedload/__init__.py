# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Type-aware construction of Python dataclasses from raw dicts.

Builds typed instances from plain dicts, with union disambiguation (tag-based,
structural, or leaf-coercion), nested dataclass support, and collection handling.
Also exposes leaf-value coercion for scalar types.

Values are expected to carry their final type already, as they do when loaded from
YAML, TOML or JSON. Text is parsed into other types (``"8080"`` → ``8080``) only for
the string tokens produced from command-line arguments and environment variables;
a plain ``str`` given for an ``int`` field is a ``TypeCoercionError``.

Typical use::

    from dataclasses import dataclass
    from confarg.typedload import construct


    @dataclass
    class Server:
        host: str
        port: int


    srv = construct(Server, {"host": "localhost", "port": 8080})
    # srv == Server(host="localhost", port=8080)

Agent Notes:
    architecture/05-types-and-construction.md
"""

from confarg.exceptions import (
    AmbiguousUnionError,
    MissingFieldError,
    TypeCoercionError,
)
from confarg.typedload._coerce import _coerce_leaf as coerce
from confarg.typedload._construct import construct

__all__ = [
    "AmbiguousUnionError",
    "MissingFieldError",
    "TypeCoercionError",
    "coerce",
    "construct",
]
