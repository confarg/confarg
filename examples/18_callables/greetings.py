# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from collections.abc import Callable
from dataclasses import dataclass


def print_greetings(name: str, *, greetings: str = "Hello") -> None:
    print(f"{greetings}, {name}!")


class Print_greetings:
    def __init__(self, greetings: str = "Hello") -> None:
        self.greetings = greetings

    def __call__(self, name: str, *, adjective: str = "") -> None:
        name = f"{adjective} {name}" if adjective else name
        print(f"{self.greetings}, {name}!")


class Greetings_printer:
    def __init__(self, greetings: str = "Hello") -> None:
        self.greetings = greetings

    def print(self, name: str, *, adjective: str = "") -> None:
        name = f"{adjective} {name}" if adjective else name
        print(f"{self.greetings}, {name}!")


@dataclass
class Config:
    greetings_fn: Callable[[str], None]
