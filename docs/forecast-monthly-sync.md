# Monthly FORECAST synchronization

## Source contract

- Exact worksheet: `FORECAST'18`.
- Part No. marker: `D3=Part No.`.
- CUSTOMER FORECAST month region: columns `F:S`.
- Right boundary: `T3=Total`.
- Every `F4:S4` header must normalize to a unique, strictly increasing month.
- Excel dates with Buddhist years subtract 543. Strict labels such as `Jul-69`
  are interpreted as July 2569 BE, or `2026-07` CE. Ambiguous labels fail.
- Columns at `T` and later are summary/downstream fields and are never imported.

## Identity and drift gate

Parent identity remains `source_sheet + source_row + normalized_part_no`. Before
any automatic write, synchronization blocks its entire transaction when it finds:

- duplicate complete source identities;
- an existing source row containing a different normalized Part No.;
- more than `max(5, 5% of existing parents)` Parts moving over five rows;
- more than `max(10, 10% of existing parents)` existing identities disappearing.
- more than `max(25, 10% of existing parents)` identities appearing at once.

Blocked synchronization never updates quantities, Lots, parents, or monthly rows.
Stale rows below the safety threshold are reported and retained; no automatic
delete occurs. New valid identities may be inserted. Monthly upsert SQL changes
only `quantity` and `source_label`, so Lot and updater attribution remain intact.

## Default month

UI selects current `YYYY-MM` when imported. Otherwise it selects latest imported
month not after current month. If every imported month is later, it selects earliest.

## Worker operation

`forecast-sync` runs outside Gunicorn. Every interval it checks size and modified
time, waits for stability, rechecks, copies a private temporary snapshot, hashes it,
and skips an unchanged successful hash. Changed workbooks validate and apply in one
database transaction. Failure rolls back and retries next interval. Source mount is
read-only; only worker-owned temporary snapshots are deleted.

The service is profile-gated, so normal `docker compose up` cannot activate it
before migration approval. After migration and source review, activation requires
the explicit `--profile forecast-sync` Compose option.
