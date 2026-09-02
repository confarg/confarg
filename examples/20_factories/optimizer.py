# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Optimizers."""

from collections.abc import Iterable


class BaseOptimizer:
    """Base optimizer class."""

    def __init__(self, params: Iterable, lr: float) -> None:
        """Initialize with parameters and learning rate."""
        self.params = params
        self.lr = lr


class Optimizer(BaseOptimizer):
    """Optimizer with momentum."""

    def __init__(self, params: Iterable, lr: float = 0.1, momentum: float = 0.99) -> None:
        """Initialize with parameters, learning rate, and momentum."""
        super().__init__(params, lr=lr)
        self.momentum = momentum

    def __repr__(self) -> str:
        """Return a string representation of the optimizer."""
        return f"Optimizer(lr={self.lr}, momentum={self.momentum})"
