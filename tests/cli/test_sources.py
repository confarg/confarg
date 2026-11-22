# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What every adapter reads back of a registration: its options and its runs (REF-114)."""

from __future__ import annotations

import pytest

from confarg.cli._sources import Registration, options_for, runs_of
from confarg.exceptions import ConfargError


def test_options_for_an_unregistered_parse_reads_given_alone() -> None:
    """With no registration, the options are the ones given, resolved."""
    options = options_for(None, "merge_namespace", {"argv": ["--a", "1"], "env_prefix": "APP_"})
    assert options.argv == ["--a", "1"]
    assert options.env_prefix == "APP_"


def test_options_for_reuses_what_registration_read() -> None:
    """An option not given is the one registration read."""
    registration = Registration(_recorded(env_prefix="APP_"), frozenset(), None)
    assert options_for(registration, "merge_namespace", {"argv": []}).env_prefix == "APP_"


def test_options_for_refuses_a_recorded_option_that_differs() -> None:
    """An option given that registration read differently is refused, naming the caller."""
    registration = Registration(_recorded(env_prefix="APP_"), frozenset(), None)
    with pytest.raises(ConfargError, match=r"env_prefix mismatch.*merge_context\(\)"):
        options_for(registration, "merge_context", {"env_prefix": "OTHER_"})


def test_runs_of() -> None:
    """The runs are the registration's, ``None`` when confarg registered none."""
    assert runs_of(None) is None
    assert runs_of(Registration(_recorded(), frozenset({"a.b"}), None)) == frozenset({"a.b"})


def _recorded(**overrides: object) -> dict[str, object]:
    """Return the recorded options of a registration made with the defaults, *overrides* beside them."""
    return {
        "files": (),
        "env": None,
        "env_prefix": None,
        "env_separator": "__",
        "env_config": None,
        "config_flag": "config",
    } | overrides
