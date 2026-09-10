# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from collections.abc import Iterable


class BaseOptimizer:
    def __init__(self, params: Iterable, lr: float) -> None:
        self.params = params
        self.lr = lr


class Optimizer(BaseOptimizer):
    def __init__(self, params: Iterable, lr: float = 0.1, momentum: float = 0.99) -> None:
        super().__init__(params, lr=lr)
        self.momentum = momentum

    def __repr__(self) -> str:
        return f"Optimizer(lr={self.lr}, momentum={self.momentum})"
