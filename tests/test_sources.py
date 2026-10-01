# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for config source locations: scheme dispatch, reading, format, joining, identity."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

import confarg
from confarg._sources import _SCHEME_READERS, _identity, _join, _read_bytes, _scheme_of, _suffix
from confarg.exceptions import InvalidConfigFileError
from tests.conftest import WithDefaults

# ---------------------------------------------------------------------------
# _scheme_of
# ---------------------------------------------------------------------------


class TestSchemeDetection:
    """Which locations name a scheme, and which stay local paths."""

    @pytest.mark.parametrize(
        "loc",
        [
            "config.yaml",
            "./a/b.yaml",
            "../up.yaml",
            "/etc/app.yaml",
            r"C:\Users\bob\config.yaml",
            "c:/Users/bob/config.yaml",
            r"\\server\share\config.yaml",
            "./weird:name.yaml",
        ],
    )
    def test_local_paths_have_no_scheme(self, loc: str) -> None:
        """A path, including a Windows drive letter, is not a URL."""
        assert _scheme_of(loc) == ""

    @pytest.mark.parametrize(
        ("loc", "expected"),
        [
            ("file:/home/bob/config.yaml", "file"),
            ("file:///home/bob/config.yaml", "file"),
            ("http://h/app.yaml", "http"),
            ("https://h/app.yaml", "https"),
            ("HTTPS://h/app.yaml", "https"),
            ("s3://bucket/key.yaml", "s3"),
        ],
    )
    def test_registered_schemes_are_recognised(self, loc: str, expected: str) -> None:
        """A registered scheme is returned lowercased."""
        assert _scheme_of(loc) == expected

    def test_single_letter_scheme_is_a_drive_letter(self) -> None:
        """A one-character prefix is never a scheme, so a drive letter survives."""
        assert _scheme_of("d:/data/app.yaml") == ""

    def test_unregistered_scheme_raises_naming_the_registered_ones(self) -> None:
        """An unknown scheme is an error, not a filename."""
        with pytest.raises(InvalidConfigFileError, match="No handler registered") as exc:
            _scheme_of("gs://bucket/app.yaml")
        message = str(exc.value)
        assert "file" in message
        assert "https" in message
        assert "register_scheme" in message

    def test_unregistered_scheme_error_hints_the_dot_slash_escape(self) -> None:
        """A local filename containing a colon is escapable, and the error says how."""
        with pytest.raises(InvalidConfigFileError, match=r"\./weird:"):
            _scheme_of("weird:name.yaml")


# ---------------------------------------------------------------------------
# _suffix
# ---------------------------------------------------------------------------


class TestSuffix:
    """The format a location names."""

    @pytest.mark.parametrize(
        ("loc", "expected"),
        [
            ("app.yaml", ".yaml"),
            ("app.TOML", ".toml"),
            ("dir.d/app.json", ".json"),
            ("https://h/app.yaml", ".yaml"),
            ("https://h/deep/path/app.yml", ".yml"),
            ("https://h/app.YAML", ".yaml"),
            ("s3://bucket/deep/app.toml", ".toml"),
            ("file:///C:/x/app.json", ".json"),
        ],
    )
    def test_suffix(self, loc: str, expected: str) -> None:
        """A suffix is read the same way for every scheme."""
        assert _suffix(loc) == expected

    def test_query_and_fragment_are_stripped(self) -> None:
        """A query string does not become part of the extension."""
        assert _suffix("https://h/api/app.yaml?env=prod&v=3") == ".yaml"
        assert _suffix("https://h/api/app.yaml#section") == ".yaml"

    def test_extensionless_url_has_no_suffix(self) -> None:
        """An endpoint with no extension yields no format, for the caller to reject."""
        assert _suffix("https://h/api/config") == ""

    def test_query_alone_does_not_invent_a_suffix(self) -> None:
        """A dotted query on an extensionless path is not an extension."""
        assert _suffix("https://h/api/config?format=.yaml") == ""


# ---------------------------------------------------------------------------
# _join
# ---------------------------------------------------------------------------


class TestJoinLocalBase:
    """A local document resolves includes as it always has."""

    def test_relative_resolves_against_the_including_file(self) -> None:
        """A sibling name lands beside the including document."""
        assert _join(str(Path("cfg") / "app.yaml"), "db.yaml") == str((Path("cfg") / "db.yaml").resolve())

    def test_the_joined_location_is_absolute(self, tmp_path: Path) -> None:
        """The join resolves, so an error or a cycle names the file rather than a path through it.

        A relative include reached through a parent step would otherwise print as
        ``a/../b/c.yaml``, and every level of nesting would add another step.
        """
        base = tmp_path / "env" / "app.yaml"
        joined = _join(str(base), "../shared/db.yaml")
        assert Path(joined).is_absolute()
        assert ".." not in joined
        assert joined == str(tmp_path / "shared" / "db.yaml")

    def test_a_local_file_may_include_a_url(self) -> None:
        """An absolute registered location is taken as written."""
        assert _join("cfg/app.yaml", "https://h/db.yaml") == "https://h/db.yaml"

    def test_a_local_file_may_include_an_s3_object(self) -> None:
        """Any registered scheme is reachable from a local document."""
        assert _join("cfg/app.yaml", "s3://bucket/db.yaml") == "s3://bucket/db.yaml"


class TestJoinRemoteBase:
    """A remote document resolves includes inside its own origin."""

    @pytest.mark.parametrize(
        ("base", "relative", "expected"),
        [
            ("https://h/env/app.yaml", "db.yaml", "https://h/env/db.yaml"),
            ("https://h/env/app.yaml", "./db.yaml", "https://h/env/db.yaml"),
            ("https://h/env/app.yaml", "../base.yaml", "https://h/base.yaml"),
            ("https://h/env/app.yaml", "sub/db.yaml", "https://h/env/sub/db.yaml"),
            ("https://h/env/app.yaml", "/root.yaml", "https://h/root.yaml"),
            ("s3://bucket/env/app.yaml", "db.yaml", "s3://bucket/env/db.yaml"),
            ("s3://bucket/env/app.yaml", "../base.yaml", "s3://bucket/base.yaml"),
            ("file:///srv/env/app.yaml", "db.yaml", "file:///srv/env/db.yaml"),
        ],
    )
    def test_relative_joins(self, base: str, relative: str, expected: str) -> None:
        """Joining is by URL path, so it works identically for every scheme."""
        assert _join(base, relative) == expected

    def test_s3_join_does_not_lose_the_base(self) -> None:
        """Urljoin would return the relative unchanged for s3; joining by path does not."""
        assert _join("s3://bucket/env/app.yaml", "db.yaml").startswith("s3://bucket/")

    def test_a_user_scheme_joins_the_same_way(self, scheme_registry) -> None:
        """A registered scheme inherits relative resolution without saying anything."""
        confarg.register_scheme("gs", lambda loc: b"")
        assert _join("gs://bucket/env/app.yaml", "../db.yaml") == "gs://bucket/db.yaml"

    def test_query_and_fragment_are_not_inherited(self) -> None:
        """A child document is not fetched with its parent's query string."""
        assert _join("https://h/env/app.yaml?v=3#s", "db.yaml") == "https://h/env/db.yaml"

    def test_climbing_above_the_root_clamps(self) -> None:
        """Too many parent steps stay at the origin root rather than escaping it."""
        assert _join("https://h/app.yaml", "../../../etc/passwd") == "https://h/etc/passwd"

    @pytest.mark.parametrize(
        "relative",
        ["file:///etc/shadow", "s3://other/x.yaml", "http://evil.test/x.yaml", "gs://b/x.yaml"],
    )
    def test_leaving_the_origin_is_refused(self, relative: str) -> None:
        """A scheme-bearing include from a remote document is refused, registered or not."""
        with pytest.raises(InvalidConfigFileError, match="may not include"):
            _join("https://cfg.example.com/app.yaml", relative)

    def test_an_absolute_path_stays_on_the_origin(self) -> None:
        """A leading slash is a server path, not a local filesystem path."""
        assert _join("https://h/env/app.yaml", "/etc/passwd") == "https://h/etc/passwd"


# ---------------------------------------------------------------------------
# _identity
# ---------------------------------------------------------------------------


class TestIdentity:
    """What makes two locations the same document, for cycle detection."""

    def test_local_paths_resolve(self, tmp_path: Path) -> None:
        """Two spellings of one path share an identity."""
        direct = tmp_path / "app.yaml"
        indirect = tmp_path / "sub" / ".." / "app.yaml"
        assert _identity(str(direct)) == _identity(str(indirect))

    def test_a_fragment_does_not_make_a_new_document(self) -> None:
        """A fragment addresses a position inside a document."""
        assert _identity("https://h/app.yaml#a") == _identity("https://h/app.yaml")

    def test_a_query_does_make_a_new_document(self) -> None:
        """A query string can select different content, so it is part of the identity."""
        assert _identity("https://h/app.yaml?env=prod") != _identity("https://h/app.yaml?env=dev")


# ---------------------------------------------------------------------------
# register_scheme
# ---------------------------------------------------------------------------


class TestRegisterScheme:
    """The public registration API."""

    def test_a_registered_scheme_loads_a_configuration(self, scheme_registry) -> None:
        """A three-line handler is enough to load configuration from a new scheme."""
        confarg.register_scheme("mem", lambda loc: b"name: from-mem\ncount: 3\n")

        cfg = confarg.load(WithDefaults, files=["mem://anywhere/app.yaml"], argv=[])
        assert (cfg.name, cfg.count) == ("from-mem", 3)

    def test_the_handler_receives_the_full_location(self, scheme_registry) -> None:
        """A handler is given the location exactly as written, scheme included."""
        seen: list[str] = []

        def read(loc: str) -> bytes:
            seen.append(loc)
            return b"{}"

        confarg.register_scheme("mem", read)
        _read_bytes("mem://bucket/deep/app.json?v=3")
        assert seen == ["mem://bucket/deep/app.json?v=3"]

    def test_a_builtin_can_be_replaced(self, scheme_registry) -> None:
        """Re-registering a built-in is the documented way to add auth or caching."""
        confarg.register_scheme("https", lambda loc: b"name: intercepted\n")
        assert _read_bytes("https://example.invalid/app.yaml") == b"name: intercepted\n"

    def test_registration_is_case_insensitive(self, scheme_registry) -> None:
        """A scheme registered in upper case is found in lower case."""
        confarg.register_scheme("MEM", lambda loc: b"x: 1")
        assert _scheme_of("mem://x/a.yaml") == "mem"

    def test_a_trailing_separator_is_tolerated(self, scheme_registry) -> None:
        """Writing the scheme as it appears in a URL registers the same handler."""
        confarg.register_scheme("mem://", lambda loc: b"x: 1")
        assert _scheme_of("mem://x/a.yaml") == "mem"

    @pytest.mark.parametrize("scheme", ["", "c", "1st", "-x", ":"])
    def test_an_unusable_scheme_name_raises(self, scheme: str, scheme_registry) -> None:
        """A name that could not be detected as a scheme is refused at registration."""
        with pytest.raises(ValueError, match="Invalid scheme"):
            confarg.register_scheme(scheme, lambda loc: b"")

    def test_an_oserror_from_a_handler_becomes_an_invalid_config_file_error(self, scheme_registry) -> None:
        """A handler signals failure with OSError and gets the library's own error class."""

        def read(loc: str) -> bytes:
            msg = "bucket offline"
            raise OSError(msg)

        confarg.register_scheme("mem", read)
        with pytest.raises(InvalidConfigFileError, match="Cannot read config source"):
            _read_bytes("mem://x/a.yaml")


# ---------------------------------------------------------------------------
# unregister_scheme
# ---------------------------------------------------------------------------


class TestUnregisterScheme:
    """Removing a reader, which is how an application forbids a scheme."""

    def test_a_removed_scheme_is_no_longer_loadable(self, scheme_registry) -> None:
        """After removal the location is refused the way any unknown scheme is."""
        confarg.register_scheme("mem", lambda loc: b"name: from-mem")
        confarg.unregister_scheme("mem")

        with pytest.raises(InvalidConfigFileError, match="No handler registered"):
            _read_bytes("mem://x/a.yaml")

    def test_removing_http_forbids_fetching_over_the_network(self, scheme_registry) -> None:
        """The documented way to refuse network configuration, checked through a real load."""
        confarg.unregister_scheme("http")
        confarg.unregister_scheme("https")

        with pytest.raises(InvalidConfigFileError, match="No handler registered"):
            confarg.load(WithDefaults, files=["https://cfg.example.invalid/app.yaml"], argv=[])

    def test_the_remaining_schemes_are_named(self, scheme_registry) -> None:
        """The error a removal causes lists what is left, so the removal is visible."""
        confarg.unregister_scheme("s3")
        with pytest.raises(InvalidConfigFileError, match=r"Registered schemes: file, http, https"):
            _read_bytes("s3://bucket/app.yaml")

    def test_removal_is_case_insensitive_and_tolerates_a_separator(self, scheme_registry) -> None:
        """A scheme is named for removal the same ways it is named for registration."""
        confarg.register_scheme("mem", lambda loc: b"x: 1")
        confarg.unregister_scheme("MEM://")
        assert "mem" not in _SCHEME_READERS

    def test_removing_what_is_not_registered_raises(self, scheme_registry) -> None:
        """A silent no-op would leave a misspelled scheme loadable, so it raises."""
        with pytest.raises(ValueError, match="No reader is registered"):
            confarg.unregister_scheme("gs")

    def test_removing_twice_raises(self, scheme_registry) -> None:
        """The second removal is the misspelling case, and is reported as one."""
        confarg.unregister_scheme("s3")
        with pytest.raises(ValueError, match="No reader is registered"):
            confarg.unregister_scheme("s3")

    def test_an_unusable_scheme_name_raises(self, scheme_registry) -> None:
        """The name is validated before the lookup, as it is on registration."""
        with pytest.raises(ValueError, match="Invalid scheme"):
            confarg.unregister_scheme("c")

    def test_register_puts_a_removed_builtin_back(self, scheme_registry) -> None:
        """Removal is not permanent: the scheme is a registry entry like any other."""
        confarg.unregister_scheme("https")
        confarg.register_scheme("https", lambda loc: b"name: restored")
        assert _read_bytes("https://example.invalid/app.yaml") == b"name: restored"


# ---------------------------------------------------------------------------
# the file:// handler
# ---------------------------------------------------------------------------


class TestFileUrlReader:
    """Reading through the built-in file:// handler."""

    def test_as_uri_round_trips(self, tmp_path: Path) -> None:
        """A path and its own file:// URL name the same bytes."""
        p = tmp_path / "app.yaml"
        p.write_text("name: from-file-url\n", encoding="utf-8")
        assert _read_bytes(p.as_uri()) == _read_bytes(str(p))

    def test_localhost_host_is_accepted(self, tmp_path: Path) -> None:
        """file://localhost/... is the same document as file:///...."""
        p = tmp_path / "app.yaml"
        p.write_bytes(b"name: x\n")  # write_bytes: write_text would CRLF-translate on Windows
        localhost_url = p.as_uri().replace("file:///", "file://localhost/")
        assert _read_bytes(localhost_url) == b"name: x\n"

    def test_another_host_is_refused(self) -> None:
        """A UNC-style file:// URL is refused rather than silently reinterpreted."""
        with pytest.raises(InvalidConfigFileError, match="local machine only"):
            _read_bytes("file://someserver/share/app.yaml")

    def test_missing_file_reports_not_found(self, tmp_path: Path) -> None:
        """A file:// URL naming nothing gets the same error a path does."""
        url = (tmp_path / "missing.yaml").as_uri()
        with pytest.raises(InvalidConfigFileError, match="not found"):
            _read_bytes(url)


# ---------------------------------------------------------------------------
# the http/https handler
# ---------------------------------------------------------------------------


class TestHttpReader:
    """Reading through the built-in http handler, over a loopback server."""

    def test_reads_bytes_verbatim(self, tmp_path: Path, tmp_http: str) -> None:
        """The handler returns exactly what the server sent."""
        (tmp_path / "app.yaml").write_bytes(b"name: served\n")
        assert _read_bytes(f"{tmp_http}/app.yaml") == b"name: served\n"

    def test_a_missing_document_reports_not_found(self, tmp_http: str) -> None:
        """404 is the one status that maps to the not-found error."""
        with pytest.raises(InvalidConfigFileError, match="not found"):
            _read_bytes(f"{tmp_http}/missing.yaml")

    def test_a_dead_port_reports_unreachable(self) -> None:
        """A connection failure is a read failure, not a parse failure."""
        with pytest.raises(InvalidConfigFileError, match="Cannot read config source"):
            _read_bytes("http://127.0.0.1:1/app.yaml")

    def test_a_query_string_survives_to_the_server(self, tmp_path: Path, tmp_http: str) -> None:
        """The location reaches the handler whole, so a query string is sent."""
        (tmp_path / "app.yaml").write_bytes(b"name: served\n")
        assert _read_bytes(f"{tmp_http}/app.yaml?env=prod") == b"name: served\n"


# ---------------------------------------------------------------------------
# the s3 handler
# ---------------------------------------------------------------------------


def _stubbed_s3(monkeypatch):
    """Return a boto3 S3 client with a Stubber attached, installed as boto3.client's answer."""
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # a stub never authenticates
    )
    stubber = Stubber(client)
    monkeypatch.setattr(boto3, "client", lambda *a, **k: client)
    return client, stubber


class TestS3Reader:
    """Reading through the optional s3 handler, against botocore's own service model."""

    def test_reads_an_object(self, monkeypatch) -> None:
        """A successful get_object hands back the body's bytes."""
        _, stubber = _stubbed_s3(monkeypatch)
        payload = b"name: from-s3\n"
        stubber.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(payload), len(payload))},
            {"Bucket": "my-bucket", "Key": "deep/app.yaml"},
        )
        with stubber:
            assert _read_bytes("s3://my-bucket/deep/app.yaml") == payload

    def test_a_missing_key_reports_not_found(self, monkeypatch) -> None:
        """NoSuchKey is the same verdict as a missing file."""
        _, stubber = _stubbed_s3(monkeypatch)
        stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        with stubber, pytest.raises(InvalidConfigFileError, match="not found"):
            _read_bytes("s3://my-bucket/app.yaml")

    def test_another_client_error_reports_unreachable(self, monkeypatch) -> None:
        """A permissions failure is a read failure, and says so."""
        _, stubber = _stubbed_s3(monkeypatch)
        stubber.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
        with stubber, pytest.raises(InvalidConfigFileError, match="Cannot read config source"):
            _read_bytes("s3://my-bucket/app.yaml")

    @pytest.mark.parametrize("loc", ["s3://bucket-only", "s3:///key-only.yaml"])
    def test_a_malformed_location_is_rejected(self, loc: str) -> None:
        """An s3 URL needs both a bucket and a key."""
        with pytest.raises(InvalidConfigFileError, match="Malformed S3 location"):
            _read_bytes(loc)

    def test_missing_boto3_names_the_extra(self, monkeypatch) -> None:
        """Without boto3 the error says what to install, as the other optional parsers do.

        The command has to be runnable as printed: ``pip install boto3`` would work by accident
        and leave the extra uninstalled, so the match covers the whole instruction.
        """
        monkeypatch.setitem(sys.modules, "boto3", None)
        with pytest.raises(InvalidConfigFileError, match=r"Install it with: pip install confarg\[s3\]"):
            _read_bytes("s3://bucket/app.yaml")
