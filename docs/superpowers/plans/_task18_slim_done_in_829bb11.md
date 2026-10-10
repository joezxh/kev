# Task 18 — slim seed_to_kev + check_volume

**Status: completed (in commit `829bb11`).**

Task 18's "delete `SPEC_FOR` dict from `seed_to_kev.py` and `check_volume.py`; replace
with a DB lookup via `Store.list_scenario_slugs()`" was done inline as part of the
snapshot-preservation commit `829bb11` (which also includes Task 26's regression tests
and snapshots). The two file diffs in that commit are:

- `kev/console/distill/check_volume.py` (+40 / -2)
- `kev/console/distill/seed_to_kev.py` (+29 / -3)

The earlier commit message named only Task 26, which is misleading. This file is
added so a reviewer can see what 829bb11 actually did, and so a follow-up re-run
of Task 18 has nothing to apply (it would be a no-op).

**No separate commit** for Task 18: re-doing it would be a no-op against `829bb11`
(verified by the Task 18 subagent on 2026-10-10, whose `git diff HEAD` was empty
after re-applying the same edits).
