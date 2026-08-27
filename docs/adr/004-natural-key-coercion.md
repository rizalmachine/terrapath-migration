# ADR-004: Natural keys are coerced to str before any comparison

## Context

`Porto`, the sibling project, hit a real bug: a phone-number key round-tripped
through a CSV write/read as `int64` on one side and stayed `str` on the
other, so every key match silently failed and every export row looked "new"
on every run. `farmer_code`, `plot_code`, and `certificate_number` here are
deliberately generated as pure-digit strings (`"700001"`, not `"FARM-0001"`)
specifically so this class of bug has somewhere real to occur, rather than
being designed away by accident.

## Decision

`warehouse/scd2.py`'s `apply_scd2()` and `resolve_scd2_key()` both coerce the
natural-key column to `str` on every input before comparing, joining, or
indexing by it -- explicitly, at the top of each function, not left to
whatever dtype happened to arrive. `tests/test_scd2.py::
test_natural_key_coercion_matches_across_numeric_and_string_types` and
`test_resolve_scd2_key_point_in_time` both pass a natural key as a plain
Python `int` on one side and a `str` on the other, and assert they still
match -- so this can't regress silently.

`warehouse/validate.py`'s row-hash checksum doesn't need this same explicit
coercion: it stringifies every column of every row before hashing (`str(700001)
== str("700001")`), so the same class of failure can't occur there by
construction, not by discipline. That's `warehouse/validate.py`'s design; the
coercion in `scd2.py` is deliberate because that code path indexes and
compares by key directly.

## Consequences

Coercing to `str` means a natural key that's *supposed* to change type
(unlikely here, but not impossible in a real system) would be silently
accepted rather than flagged. That's an acceptable trade for this domain --
`farmer_code`/`plot_code` are assigned once at issuance and never
retyped in the real system this is modeled on.
