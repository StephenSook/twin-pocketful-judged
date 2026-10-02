# LEDGER AUDIT de870bb

Stage 3 — R3-001 to R3-108, plus R1 and R2 carry-overs.

## 1. Normative sentences with no covering entry

**Minor gap: S3-2 ruling (offset space parsing).** Coordinator ruling S3-2: "a decoded space in the offset-sign position of a query instant is read as '+'." No R3 entry explicitly covers this query-parameter parsing behavior. R3-009 validates date/offset format but does not mention space-to-plus conversion. Add a note to R3-009 or create a dedicated entry referencing S3-2.

All other normative statements in the stage-3 spec have at least one R3 entry.

## 2. Entries whose reading differs from the text

**R3-077 (snapshot token lifetime across import).** Quoted: "Tokens last until reset." Reading: "Repeated page retrieval valid across ordinary actions; import epoch per ownership contract." The spec says "Tokens last until reset" (line 140) and never says import invalidates them. "Import epoch per ownership contract" could be read as import creating a new epoch that invalidates prior tokens. The safest reading of "Tokens last until reset" is that only `POST /_test/reset` terminates tokens; import does not. This entry's reading may over-invalidate. The coordinator should confirm: do snapshot tokens survive import?

**R3-019 (statement ordering rule).** Quoted: "created_at ascending then payment id ... ties." The spec line 68 originally stated created_at ordering, but line 127 now says "Statement ordering is now by selected effective_at, then payment id." This is the universal rule (corrections or not; for uncorrected payments effective=created, so the ordering is identical). R3-066 correctly captures the superseding rule. The reading in R3-019 ("Uncorrected equal-time seeded IDs sorted lexically ascending") is functionally equivalent but the quoted text should reference effective_at for consistency.

## 3. Ambiguities resolved without quoting the text

**S3-A2 (historical affordability at instant boundaries).** The spec says "Balances at a boundary include the combined effect of all movements at that instant" (line 110-111). The ledger resolves that temporary negative intermediate balances within the same instant are permitted as long as the aggregate is nonnegative. This is a reasonable interpretation but is not directly stated.

**S3-A5 (correction authorization for public payments).** The spec says correction requires the original sender but does not say whether a non-sender's visibility-based access (e.g. public payment) overrides the authorization. The ledger resolves that sender authorization is always required, even for public payments. Textually supported by "requires an idempotency key and the original sender" (line 89).

## 4. Coverage marked as checked that is not: None

All R3 entries are correctly marked "unchecked." No overstated claims.
