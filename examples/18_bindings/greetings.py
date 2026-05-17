# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Callables and dataclasses for the 130_callable example."""

from collections.abc import Callable
from dataclasses import dataclass


def print_greetings(name: str, *, greetings: str = "Hello") -> None:
    """Print a greeting for the given name."""
    print(f"{greetings}, {name}!")


class Print_greetings:
    """Callable class with a configurable greeting string."""

    def __init__(self, greetings: str = "Hello") -> None:
        """Initialize with the greeting string."""
        self.greetings = greetings

    def __call__(self, name: str, *, adjective: str = "") -> None:
        """Print the configured greeting for the given name."""
        name = f"{adjective} {name}" if adjective else name
        print(f"{self.greetings}, {name}!")


class Greetings_printer:
    """Class with a print method using a configurable greeting string."""

    def __init__(self, greetings: str = "Hello") -> None:
        """Initialize with the greeting string."""
        self.greetings = greetings

    def print(self, name: str, *, adjective: str = "") -> None:
        """Print the configured greeting for the given name."""
        name = f"{adjective} {name}" if adjective else name
        print(f"{self.greetings}, {name}!")


@dataclass
class Config:
    """Application configuration with a callable greeting function."""

    greetings_fn: Callable[[str], None]
