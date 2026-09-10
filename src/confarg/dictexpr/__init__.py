# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Expression interpolation engine for nested dicts.

Resolves ``${field.path}`` references and safe Python expressions embedded in
string values of a nested dict.  The engine operates on plain dicts and has no
dependency on any config-source or dataclass logic.

Typical use::

    from confarg.dictexpr import resolve_expressions

    data = {"base": "/app", "log": "${base}/logs"}
    resolved = resolve_expressions(data)
    # resolved == {"base": "/app", "log": "/app/logs"}

:func:`contains_expression` tells whether resolution would rewrite a value
(``${...}`` or the ``$${...}`` escape); code inspecting values before resolution
uses it to leave such values untouched.

Agent Notes:
    architecture/07-expressions.md
"""

from confarg.dictexpr._expressions import contains_expression, resolve_expressions
from confarg.exceptions import (
    CircularReferenceError,
    ExpressionEvalError,
    MissingReferenceError,
    UnsafeExpressionError,
)

__all__ = [
    "CircularReferenceError",
    "ExpressionEvalError",
    "MissingReferenceError",
    "UnsafeExpressionError",
    "contains_expression",
    "resolve_expressions",
]
