# LEDGER AUDIT ab6b0b2

Incremental audit since f73cb58 (commit 582aa3c). Diff: 80 insertions, 64 deletions.

## 1. pay-uncertain gap: CLOSED

R2-065 now reads: "require a visible element with data-testid='pay-uncertain' and nonempty text, and no element with data-testid='pay-error'." The coverage section explicitly acknowledges auditor revision 582aa3c. Gap resolved.

## 2. Rulings S2-1 to S2-4 and S2-A3 confirmation

- **S2-1** (authorization-expires visible RFC 3339): Not changed in this diff; remains as f73cb58. Ledger ambiguity section still captures the conflict with the brief's hidden-time preference and the requirement's precedence (written requirements win). Faithful to the ruling.

- **S2-2** (expired vs not-open precedence): R2-123 coverage upgraded to "own HTTP/model check". Reading text still says "pending ruling precedence" — this is stale wording since the coordinator has ruled, but it does not affect the test behavior (which correctly checks expired -> authorization_expired). S2-A2 ambiguity entry still says "Pending coordinator ruling" but is otherwise accurate.

- **S2-A3** (capture records stay visible after void/expiry, remaining_amount 0): Coverage section confirms: "API-generated partial history is checked exactly after void/expiry/import." R2-120 (remaining_amount zero when closed) and R2-121 (preserve records) now both "own HTTP/model check". Faithful to the ruling.

- **S2-3/S2-4** (captured_amount/payment_ids persistence, migration replay): Covered by R2-118/119/121/111 coverage upgrades. No misreading.

## 3. New misreadings: None found

All reading text unchanged from f73cb58; only coverage markings changed. The coverage column updates ("own HTTP/model check" replacing "unchecked") are appropriate for a modeler check that now has executable refutations.

## 4. Overstated coverage: None

The coverage section is transparent: it lists partial/unchecked items (R2-075/077/081/148 sequential invariants, R2-087 concurrency, R2-100/101/103/108 field combinations, R2-123 stale wording). Visual/browser entries remain unchecked by modeler. The observed evidence clearly states "No browser or independent gatekeeper acceptance is claimed."
