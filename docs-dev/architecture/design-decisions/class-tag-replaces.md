# A class tag replaces, not merges

A dict carrying the union tag discards the previous value during merge ([pipeline](../pipeline/deep-merge.md#deep-merge-semantics)), so switching variants does not inherit the old variant's fields.
A `call:` replaces the same way ([a call replaces what lies below](a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)).
It does where the type reads the key as the tag; where a member owns the tag's spelling, or a `dict` holds it as data, the key refines like any other ([the type decides](the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
