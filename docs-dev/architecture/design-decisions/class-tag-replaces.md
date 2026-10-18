# A class tag replaces, not merges

A dict carrying the union tag discards the previous value during merge
([pipeline](../pipeline/deep-merge.md#deep-merge-semantics)), so switching variants does not
inherit the old variant's fields. A `call:` replaces the same way
([a call replaces what lies below](a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)).
