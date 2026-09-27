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
