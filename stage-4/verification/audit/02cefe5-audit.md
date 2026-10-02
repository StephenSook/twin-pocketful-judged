# LEDGER AUDIT 02cefe5

Stage 4 — R4-001 to R4-052, plus R1-R3 carry-overs.

## 1. Normative sentences with no covering entry: None

Every normative statement in the stage-4 spec has at least one R4 entry. The ten idempotent paths (R4-002), refund validation matrix, batch correction rules, and error precedence are all covered.

## 2. Entries whose reading differs from the text: None

All 52 R4 entries were reviewed against the spec and are consistent:

- R4-008 (refund amount validation): zero invalid is correct — refund creates a payment, and payment minimum is 1 (stage-1 §8). S4-A1 confirms this.
- R4-009 (cumulative cap tracked against current corrected amount): reading says "correction changes cap" — matches "current corrected amount" in the spec.
- R4-022 (cannot reduce below refunded): reading says "exact refunded amount allowed" — the spec says "cannot reduce a payment below its already-refunded amount," so the boundary at exact amount is valid.
- R4-032 (identical effective instants): reading accepts equal offset spellings — matches spec "identical effective instants (offset spellings may differ)."
- R4-035–038 (error precedence): correctly follows spec order: item errors in input order, then settlement completeness, then current available, then historical boundaries.

## 3. Ambiguities resolved without quoting the text

- S4-A1 (refund amount minimum): The spec does not explicitly state the refund amount minimum. S4-A1 resolves it as the ordinary payment range 1..1e9 (zero invalid). Textually supported by the refund being a payment.
- S4-A2 (cumulative cap reference): The spec says "current corrected amount" but does not say whether a correction that raises the amount also raises the cap. S4-A2 confirms that the latest corrected amount is the reference.
- S4-A5 (correction_batch_id on revisions): The spec says batch revisions expose correction_batch_id but does not say ordinary revisions omit it. S4-A5 resolves that ordinary revisions omit it unless the spec says otherwise.

## 4. Coverage marked as checked that is not: None

All R4 entries are correctly marked "unchecked." R1-R3 carry-overs retain their earlier markings. No overstated claims.
