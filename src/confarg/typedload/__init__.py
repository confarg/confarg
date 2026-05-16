# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""confarg.typedload — type-aware construction of Python dataclasses from raw dicts.

Builds typed instances from plain dicts, with union disambiguation (tag-based,
structural, or leaf-coercion), nested dataclass support, and collection handling.
Also exposes leaf-value coercion for scalar types.

Typical use::

    from dataclasses import dataclass
    from confarg.typedload import construct, coerce


    @dataclass
    class Server:
        host: str
        port: int


    srv = construct(Server, {"host": "localhost", "port": "8080"})
    # srv == Server(host="localhost", port=8080)

    val = coerce(int, "42")
    # val == 42
"""

from confarg._errors import (
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
