# A bug ticket names the revision that introduced it

Every bug ticket carries `introduced_by`, the revision the bug came from, and an `Origin:` paragraph saying why that revision produced it.
The revision that fixes the bug repeats the origin as an `Introduced-by:` trailer ([todo/README.md § Origin](../../todo/README.md#origin)).

**What was missing.**
A ticket described the symptom and a fix direction, and the fix went where the symptom showed.
That is the right place only when the bug is an isolated slip.
Three cases it gets wrong are invisible from the symptom and visible from the history:

- the change that introduced the bug was itself the mistake, and should be reverted or reworked rather than patched around;
- several open bugs share one origin, and fixing each narrowly leaves the cause in place;
- two fixes keep undoing each other, each bringing the other bug back in a new shape, because the constraints they serve meet at one place in the code and neither fix honors both.

The third case matters most in this repository, where cross-channel parity puts many constraints on one walk and one merge, and where most tickets are filed and fixed by agents that see one ticket at a time.

**Precedents.**
The Linux kernel requires a `Fixes: <sha> ("subject")` trailer on every bug-fix commit, naming the commit that introduced the bug; the stable maintainers backport on it, and it makes "what did this commit break" a `git log --grep`.
Mozilla's Bugzilla has a `Regressed by` field and its inverse, `Regressions`, plus a `regression` keyword.
Its triage process asks for the field to be filled, often by bisecting with `mozregression`, so that regression chains can be followed from bug to bug.
Chromium's bug template asks whether the bug is a regression and for a bisect range.
This repository takes Bugzilla's field, since the boards are its tracker, and the kernel's trailer, since a closed ticket's file is deleted and only the history outlives it.

**Why a field, and not just prose.**
A field is checked, and it is shown in the bugs table, where two open bugs with one origin sit side by side.
Prose alone would rely on someone reading every ticket to notice the cluster.
The *why* stays prose: it is an explanation, which no script reads.

**Why `introduced_by` and not `regressed_by`.**
Many bugs here were never correct: the case was missed when the code was written, and nothing regressed.
Both kinds have an origin worth reading, so the key names the origin and the `Origin:` paragraph says which kind it is.

**Why a ticket ID or a PR number, never a commit ID.**
Pull requests are squash-merged into `master`, and revisions on their way there are rebased, so a commit ID names nothing a month after it is written.
A revision's description cites the ticket it closed, and `master`'s cites its PR, and neither changes.
The ticket is usually closed by the time it is named, which is why `introduced_by` accepts IDs that `blocked_by` would refuse.

**Why `unknown` is allowed.**
Some origins cannot be found: the bug runs through code reshaped several times since, or the cause is an interaction no single revision added.
Requiring an answer anyway would invite a guess.
`unknown`, with a comment saying what was searched, is an answer a reader can trust, and it is distinct from a missing key, which means nobody looked.

**Why only from 2026-10-07.**
The bugs open when the rule was written predate it.
Backfilling them all at once is a large history search with no fix behind it; instead, a board sweep fills them in as it passes, and `index.py` requires the key only on tickets filed since.

**Cost.**
Filing a bug takes a history search on top of the reproduction.
That is usually a blame and a log, sometimes a bisect.
A drive-by finding filed in the middle of other work pays it too, which is the point: the history is cheapest to read when the code is fresh in mind.
