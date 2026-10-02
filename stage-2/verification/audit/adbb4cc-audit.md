# LEDGER AUDIT adbb4cc

Cumulative: ab6b0b2 through adbb4cc. Covers R2-202, S2 ambiguity updates, and R2-123 fix.

## 1. Normative sentences with no covering entry: None

All prior gaps closed. R2-202 now binds pay-uncertain as a data-testid.

## 2. Entries whose reading differs from the text: None

- S2-A1: confirmed S2-1 ruling -- exact RFC 3339 visible, separate relative label permitted.
- S2-A2: confirmed S2-2 ruling -- expired -> authorization_expired, captured/voided -> authorization_not_open.
- S2-A3: confirmed -- capture records visible after void/expiry, remaining_amount=0.
- S2-A4: confirmed S2-4 -- imported stage-1 replays retain original body without authorization_id.
- S2-A6: confirmed S2-3 -- seeded closed authorizations hold zero; tests check status/visibility/held0/409 codes only.
- R2-123: reading updated from "pending ruling precedence" to "coordinator S2-2 confirms precedence" -- stale wording fixed.

All rulings faithful to the coordinator's text. No misreading.

## 3. Ambiguities resolved without quoting the text

S2-A6 (seeded closed authorizations defaults): The spec says "Only open holds anything" and "Seeded status is open, captured, voided or expired." The spec does not state the default values for captured_amount, payment_ids, payment_id, or remaining_amount on seeded closed authorizations. The ledger resolves: captured_amount = amount for captured, 0 otherwise; payment_ids = []; payment_id = null; remaining_amount = 0. This is the natural reading -- a closed hold has no history the fixture didn't supply -- but is not quoted from the text.

## 4. Coverage marked as checked that is not: None

R2-202 is correctly marked "unchecked browser check." All other coverage markings unchanged from ab6b0b2, with appropriate caveats.
