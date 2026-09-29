# Real field wins over reserved words

Reserved names (casts, locals) are only reserved where they would not shadow a real member, so
confarg never forbids a field name ([CLI parsing](../cli-parsing/casts-and-reserved-words.md#real-field-wins)).
