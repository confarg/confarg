# A remote document reaches only its own origin

A relative `__include__` in a remote document resolves within that document's scheme and host. An
include naming another scheme or host, a local path included, raises
`InvalidConfigFileError.cross_origin_include`. A local file may still include any registered
location.

The asymmetry is the trust boundary: whoever wrote a local file is whoever runs the program,
while a location fetched over the network may be attacker-influenced — via a `--config` argument,
a `CONFIG` environment variable, or a compromised server. Without the rule, any config URL
doubles as a local-file-read and internal-network-probe primitive (`__include__: /etc/passwd`,
`__include__: http://169.254.169.254/…`) whose result lands in the merged configuration.

Rejected: full symmetry with local files, which is simpler and has no new rule to document, but
buys that simplicity with the primitive above. Also rejected: a `trust_remote_includes=` opt-out,
which would add a public keyword every one of the five front-ends must carry for a case nobody
has asked for. The rule is structural rather than a check — resolution joins paths within the
base's origin — so there is no place for it to be forgotten
([config files](../config-files/locations-and-schemes.md#relative-includes-resolve-within-one-origin)).
