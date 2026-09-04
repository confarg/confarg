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

:func:`contains_expression` is the canonical predicate for "would resolution
rewrite this value?".  Every gate that inspects a value before resolution runs
— eager leaf coercion, the CLI adapters' parse-time domain checks — must ask
it rather than test for ``${`` itself, so all front-ends and input channels
defer on exactly the same tokens.
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
