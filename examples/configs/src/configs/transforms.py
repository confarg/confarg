from dataclasses import dataclass


@dataclass
class Transform:
    p: float = 0.5


@dataclass
class RandomNoise(Transform):
    mean: float = 0.0
    std: float = 1.0


@dataclass
class RandomGamma(Transform):
    range: tuple[float, float] = (0.8, 1.2)
