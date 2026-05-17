# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Transform dataclasses."""

from dataclasses import dataclass


@dataclass
class Transform:
    """Base transform with an application probability."""

    p: float = 0.5


@dataclass
class RandomNoise(Transform):
    """Add random Gaussian noise."""

    mean: float = 0.0
    std: float = 1.0


@dataclass
class RandomGamma(Transform):
    """Apply random gamma correction."""

    range: tuple[float, float] = (0.8, 1.2)
