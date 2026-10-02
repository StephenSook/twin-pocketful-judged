# LEDGER AUDIT f73cb58

Stage 2 -- cumulative audit of R1 carry-overs and R2-001 to R2-201.

## 1. Normative sentences with no covering entry

One gap found:

- **pay-uncertain data-testid.** The spec paragraph "Competing clients and uncertain outcomes": "show pay-uncertain (nonempty text), not pay-error." This is a data-testid requirement, but no R2 entry names pay-uncertain as a required element or verifies its presence/semantics. R2-065 covers the behavioral aspect (uncertainty shown, error not shown) but does not check the testid attribute. Add an entry that binds pay-uncertain to R2-065 or create a dedicated R2 entry.

All other normative statements in the stage-2 spec have at least one R2 or carried-over R1 entry.

## 2. Entries whose reading differs from the text

None found. The following entries were reviewed and found consistent:

- R2-107: capture amount optional defaults to remaining amount. Consistent with spec.
- R2-114: final boolean default true; nonboolean malformed400 under generic wrong-type rule. Textually supported by section 5.
- R2-137/138: list filtering and data-status attributes. Correctly matches spec caller-scope and status enumeration.
- R2-141: authorization-expires RFC 3339 value. Correctly follows S2-1 ruling.
- R2-069: available/held latest-refresh-wins. Correctly extends R2-062 rule.

## 3. Ambiguities resolved without quoting the text

- S2-A2 (expired vs not-open precedence): The spec error table lists "not open" then "expires_at at or before now." An expired authorization is also not open. The ledger resolves expired -> authorization_expired, captured/voided -> authorization_not_open, without citing a textual clause for the precedence. Coordinator ruling S2-2 confirms this.
- S2-A3 (captured_amount/payment_ids after void/expiry): The spec says void/expiry "preserve all capture records" but does not explicitly say captured_amount and payment_ids remain visible on the response after closure. The ledger resolves that they persist and remaining_amount is zero.
- S2-A4 (migration replay receipts): The spec says "New fields do not change idempotency body equality" but does not say whether stage-1 cached responses should have authorization_id injected on replay. The ledger resolves original cached response returned unchanged.

## 4. Coverage marked as checked that is not actually checked

All R2 entries are marked "unchecked," which is honest for a new revision. R1 entries retain their earlier coverage markings which carry appropriate caveats. No overstated claims found.
