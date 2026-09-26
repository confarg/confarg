# Plans

How a settled design is going to be built. One file per design, for work too large to describe on a
board and not yet built.

A plan is the staging area between a ticket and the code. It holds what was decided, what was
rejected and why, the order to build it in, and how to tell it worked — the material that has nowhere
else to live while the code does not exist yet, because
[`../architecture/`](../architecture/README.md) documents why the code *is* the way it is, not why it
is going to be. Open work stays on the boards in [`../todo/`](../todo/README.md); a plan is cited by
the ticket it serves, and it carries no work items of its own.

**A plan is never a destination.** When the work lands, its rationale moves to `../architecture/` and
the plan file is deleted, the same way a ticket's file is deleted when it closes. Nothing in the
repository should cite a plan for a feature that already exists — if it does, the move never happened.

So a plan is the one place here that is allowed to go stale, and the only cure is landing the work or
abandoning it. Two plans for the same ticket is a contradiction, not a comparison: reconcile them into
one before building anything.
