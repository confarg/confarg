# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generic classes whose annotations are postponed: a method's own ``T`` is no module global."""

from __future__ import annotations

from dataclasses import dataclass


class Handwritten[T]:
    """A plain generic class whose ``__init__`` names the class's ``T`` in a string annotation."""

    def __init__(self, item: T) -> None:
        self.item = item


class Wider[T, X]:
    """A generic descriptor whose methods name the class's parameters in string annotations."""

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = "_" + name

    def __get__(self, obj: object, objtype: object = None) -> T:
        if obj is None:
            raise AttributeError
        return getattr(obj, self._attr)

    def __set__(self, obj: object, value: T | X) -> None:
        setattr(obj, self._attr, int(value))  # ty: ignore[invalid-argument-type]  # an int or its digits


@dataclass(kw_only=True)
class Counted:
    count: Wider[int, str] = Wider()
