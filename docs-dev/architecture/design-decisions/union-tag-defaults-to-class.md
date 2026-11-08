# union_tag defaults to "class"

`class` is a Python keyword, so no dataclass field can ever be named `class`: the discriminator can never collide with user data.
`type` was rejected as a common field name.
Configurable per call, in every role the key plays, the class opener of a callable spec included ([the union tag is the class key in every role](the-union-tag-is-the-class-key-in-every-role.md#the-union-tag-is-the-class-key-in-every-role)).
Cost: unusual for users expecting `type`, and reads slightly oddly in files.
Precedent: Hydra uses a reserved `_target_` key for the same reason.
