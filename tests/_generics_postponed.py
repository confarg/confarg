# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generic classes whose annotations are postponed: a method's own ``T`` is no module global."""

from __future__ import annotations


class Handwritten[T]:
    """A plain generic class whose ``__init__`` names the class's ``T`` in a string annotation."""

    def __init__(self, item: T) -> None:
        self.item = item
