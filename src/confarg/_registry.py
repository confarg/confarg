# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The leaf registry ``register_leaf_type`` writes, which ``typedload._coerce`` fills with the built-in leaves.

It lives apart so that ``_types`` reads it without importing ``typedload``, which imports
``_types``: a registered subclass of a builtin is a leaf, not the builtin it subclasses.
"""

from __future__ import annotations

from typing import Any

#: A leaf type to the function that coerces a value to it.
LEAF_COERCIONS: dict[type, Any] = {}

#: A leaf type to the function that writes one of its values as a configuration holds it.
LEAF_SERIALIZERS: dict[type, Any] = {}
