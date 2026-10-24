# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A module that warns when it is imported, which a configuration names by a class path.

Its warning is raised once in the life of the process, so whoever imports it first is the one
that may show it (tests/cli/test_backend_contract.py, TestANamingTypesWhatItsLayerBuildsContract).
"""

import warnings

warnings.warn("noisy module imported", UserWarning, stacklevel=1)


class Noisy:
    """A callable class the warning comes with."""

    def __init__(self, x: int = 0) -> None:
        self.x = x

    def __call__(self) -> int:
        return self.x
