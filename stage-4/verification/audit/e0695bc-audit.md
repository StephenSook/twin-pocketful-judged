# LEDGER AUDIT e0695bc

Incremental since 02cefe5. Diff: coverage upgrades, R4-053 added, coverage limits and evidence sections added.

## S4-1/S4-2/S4-3 rulings: Faithfully recorded

- **S4-1** (refund amount 1..1e9): Already in S4-A1 and R4-008. No change needed.
- **S4-2** (cap uses latest corrected amount): Already in S4-A2 and R4-009. No change needed.
- **S4-3** (correction_batch_id null unless batch; stored receipts/replays byte-identical): R4-044 (revision correction_batch_id linkage) and R4-047 (original body on retries) cover this. The coverage note correctly documents the verifier overconstraint on fresh-read JSON equality and its correction.

## Misreadings or gaps: None

All R4 readings unchanged from 02cefe5; only coverage markings changed. R4-053 (retain settlement membership/corrections/snapshots on import) is correctly added.

## Overstated coverage: None

The coverage section is transparent:
- R4-051 (concurrent shared expected revision) correctly remains "unchecked"
- All partial markings and limits are explicitly documented
- The evidence section states "modeler observations, not independent acceptance"
- The verifier overconstraint (correction_batch_id on fresh reads) is honestly reported as a verifier error, not a product defect
