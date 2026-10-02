# Stage 2 requirement ledger

Stage 1 entries below retain their IDs. Stage 1 observed evidence is historical, not a claim about stage 2. All new R2 entries initially unchecked; provided-check coverage unknown.

# Stage 1 requirement ledger

Source: supplied Pocketful Stage 1 §§1–11. IDs are permanent; later stages copy these entries without renumbering. A check listed below is a refutation procedure, not a claim that it passed. No provided checks have been inspected: **provided-check coverage is unknown for every entry**. Initially all entries are unchecked; the coverage section is updated with executable evidence.

## Ambiguity rulings

- A1: “The caller may be included ... or omitted” and “shares covers every participant including the caller, in the order given”: participant list alone defines the denominator and ordering; never implicitly append an omitted caller.
- A2: “A share of 0 is legal and still produces a request”: a zero split request can be paid, producing a zero payment; direct payment/request amount minimum remains 1.
- A3: “same method, the same path and the same body”: idempotency scope is user + method + concrete path + key; unknown body fields remain part of JSON-value identity even though ignored by endpoint validation.
- A4: “note ... 200 characters”: count Unicode code points, preserving the original string. The spec does not explicitly define UTF-16 versus code points; notify implementation before adversarial Unicode length tests.
- A5: request list tie ordering is unspecified by the text; compare sets within equal timestamp groups. Activity permits arbitrary relative order within a second. No check assumes generated ID syntax or timestamp precision.
- A6: generic errors do not establish global precedence among multiple independent invalid fields; test one fault at a time except explicit idempotency and settlement-entry precedence.
- A7: test-control export/import are exceptions to §6's earlier authentication list, as explicitly stated in §10.
- A8: no acceptance rule rejects optional extra response fields. Compare required fields; replay compares complete JSON responses exactly.
- A9 (coordinator ruling, R1-041): “outside ±2⁵³” excludes neither endpoint. Reset/import accept nonnegative balances through 9007199254740992 inclusive. Aggregate wallet totals remain exact even above 2^53. Boundary checks debit one unit, restore it, execute a net-zero settlement at the upper boundary, and export/import that state.
- A10 (coordinator final revised ruling, R1-033/049/050/093/095/096): endpoint-specific “Not the payer is 403 forbidden” and “Not the requester is 403 forbidden” take precedence over the generic visibility error rule. Any wrong-role caller, including an unrelated third party, gets 403 on pay/decline/cancel of an existing request; unknown IDs get 404. Listings still exclude unrelated requests. This withdraws the earlier third-party-404 ruling and confirms the existing model and driver behavior.

### Coordinator rulings on ledger audit f0a9650

- R1-024, null amount: “invalid amount values (including strings and booleans) ... are 422 validation_failed”. Coordinator: “Including” is not exhaustive; null is not a valid amount. The “Other wrong JSON types” sentence covers fields other than amount, note and visibility. Null amount therefore returns 422 validation_failed; existing reading retained.
- A1, split denominator: “The caller may be included in participant_handles or omitted. Shares follow the equal-split rule in §9, in the order the handles are given” and “A request is created for every participant except the caller”. Coordinator: participants are exactly the handles given; “including the caller” applies when the caller is listed. Existing reading retained.
- A2, zero shares: “A share of 0 is legal and still produces a request for that participant.” Coordinator: the 1..1000000000 amount rule applies to POST /payments, /requests, /splits and settlement bodies; the pay endpoint has no amount rule, so a zero request is payable. Existing reading retained.
- A4, code points: “Unicode and emoji survive a round trip”. Coordinator: counting code points matches this requirement and does not count one emoji as two characters. Existing reading retained.

## Entries

Each row is `ID | quoted requirement | tested reading / falsifying check`. Coverage is **unchecked** unless explicitly listed below.

| ID | Quoted requirement | Reading / refuting check |
|---|---|---|
| R1-001 | “sum of wallet balances always equals the total seeded” | Sum all authenticated /me balances after every operation, failures and retries; compare with fixture total. |
| R1-002 | “No wallet balance may be negative, including transiently” | Sequential model rejects negative final state; concurrent observer probes must never see negative balances. Transient internal state requires independent audit. |
| R1-003 | “A payment request may move money at most once” | Repeated pay with same and new keys; racing pay/decline/cancel must yield at most one debit. |
| R1-004 | “All amounts are exact integer counts of minor units” | Compare exact integer balances and amounts, including near 2^53. |
| R1-005 | “Money moves only between existing wallets” | Unknown handles fail without balance or receipt change; no implicit wallets. |
| R1-006 | “HTTP service, a Dockerfile and a RUN.md ... without manual setup” | Build/run documented command from clean checkout and probe health. |
| R1-007 | “image must run on its own with -e PORT ... port mapping” | Run single container on nondefault PORT, no compose or host source imports. |
| R1-008 | “no outbound access ... within that single container” | Run without outbound networking; API and assets remain functional. |
| R1-009 | “CPU ... 2 vCPU ... Memory ... 2 GiB” | Exercise image under both resource limits. |
| R1-010 | “Start to first healthy response ... 60 s” | Bound readiness elapsed time. |
| R1-011 | “Concurrent requests ... up to 50 in flight” | Submit 50 concurrent operations and verify responses plus invariants. |
| R1-012 | “Per-request timeout ... 5 s (10 s ... reset)” | Time each API call; §10 test-control timeout is 10 seconds. |
| R1-013 | “Runtime assets and dependencies must be included in the image” | Offline image execution; inspect delivery outside modeler's source restriction. |
| R1-014 | “Listen on 0.0.0.0 ... PORT ... default 8080” | Probe mapped nondefault and default ports externally. |
| R1-015 | “GET /health -> 200 {status: ok}” | Assert unauthenticated status and JSON after readiness. |
| R1-016 | “Replace all service state ... 204 ... only that fixture” | Reset twice; old tokens and records disappear, fixture balances match. |
| R1-017 | “reset ... enabled ... requires no authentication” | Reset without bearer succeeds. |
| R1-018 | “Requests and responses are application/json; charset=utf-8” | Check response media type on JSON successes and failures. No body required for 204. |
| R1-019 | “Timestamps ... RFC 3339 with an explicit offset” | Validate every receipt timestamp includes Z or numeric offset and is a valid date. |
| R1-020 | “Unknown fields ... ignored, never an error” | Valid writes containing extra fields succeed; fields still affect idempotency identity. |
| R1-021 | “Unknown query parameters are ignored” | Compare list responses with arbitrary extra query parameter. |
| R1-022 | “IDs are opaque strings of at most 64 characters” | Validate all returned resource IDs by type and length only. |
| R1-023 | “one currency ... declared in the fixture” | Reset EUR/2, JPY/0, BHD/3; all receipts and /me retain fixture denomination. |
| R1-024 | “1000, 1000.0 and 1e3 ... same valid ... Booleans and strings are not numbers” | Raw JSON lexical forms succeed; strings/bools/null/fractions fail 422 for amounts. |
| R1-025 | “handle: unique ... ^[a-z0-9_]{1,20}$ ... never changing” | Signup collision tests and repeated /me identity checks. |
| R1-026 | “Seeded users take their handle from the fixture” | /me and receipt handles match fixture exactly. |
| R1-027 | “take the local part, lowercase ... replace ... truncate to 20” | Signup mixed case, punctuation and long local part; compare derived handle. |
| R1-028 | “If that handle is already taken the signup fails” | Collision returns handle_taken; failed signup email must remain unused. |
| R1-029 | “New users start with a balance of 0 ... receive ... asked ... immediately” | Signup, /me, incoming payment and request. |
| R1-030 | “payment ... immediately and atomically” | Receipt success corresponds to both balance changes and exactly one activity record. |
| R1-031 | “requester will receive; payer ... asked” | Pay debits payer, credits requester, sets correct parties in receipt. |
| R1-032 | “pending, and then exactly one of paid, declined or cancelled” | Exercise all terminal transitions and reject incompatible transitions. |
| R1-033 | “Only the payer may pay or decline ... requester may cancel” | Other party and unrelated caller each receive 403, no mutation. |
| R1-034 | “request may exceed the payer's balance” | Create unaffordable request successfully. |
| R1-035 | “pay it while short ... 409 insufficient_funds and changes nothing” | Fail pay; fund payer; reuse failed key and successfully pay same request. |
| R1-036 | “Visibility belongs to the payment, not the request” | Request unknown visibility field ignored; payer's pay visibility controls receipt/feed. |
| R1-037 | “if and only if ... public, or ... sender or ... receiver” | Compare each user's activity to exact visible payment set. |
| R1-038 | “Requests never appear in ... activity ... only ... requester or payer” | Check activity/request collections for exact model membership. |
| R1-039 | “A split is not a feed item” | Split changes request list only; activity unchanged until payment. |
| R1-040 | “Visibility is one value ... identically ... private ... not ... receiver” | Compare both parties' full payment values and exclude third-party visibility. |
| R1-041 | “amount ... at most 1000000000 ... balances ... ±2^53” | Boundary 1e9 succeeds where affordable; 1e9+1 fails; exact high-balance arithmetic. |
| R1-042 | “Seeded users ... log in ... immediately” | Login each fixture user after reset returns token and identity. |
| R1-043 | “balance ... after ... seeded payment ... do not replay” | Seed payment and net balances; /me must equal supplied balances. |
| R1-044 | “balance below zero ... 422 ... change nothing” | Negative reset rejected, old token and full public state unchanged. |
| R1-045 | “minor_units is 0, 2 or 3 ... EUR ... JPY ... BHD” | Exercise all three fixture combinations. |
| R1-046 | “Every 4xx and 5xx ... error ... code ... message” | All error cases must have specified status/code and string human-readable message. |
| R1-047 | “400 malformed_request ... Unparseable body ... wrong JSON type” | Send truncated JSON, array body and wrong-type handle/email/password. |
| R1-048 | “401 unauthenticated ... Missing, malformed or unknown bearer token” | Exercise all bearer failures on wallet and protected writes. |
| R1-049 | “403 forbidden ... not permitted ... resource” | Unauthorized request transition/operator calls fail. |
| R1-050 | “404 not_found ... No such resource, or not visible” | Unknown handles and request IDs fail with correct envelope. |
| R1-051 | “422 ... required field ... missing ... rule violated” | Missing required fields and invalid formats return 422. |
| R1-052 | “invalid amount ... non-string note ... visibility ... 422” | Endpoint exceptions override generic wrong-type 400. |
| R1-053 | “Omission alone selects ... defaults” | Null note/visibility do not select defaults and fail 422. |
| R1-054 | “query ... plain decimal digits: 1e9, 4.0 and +4 ... 422” | Query lexical invalids on both list endpoints. |
| R1-055 | “Idempotency-Key ... 1 to 255 ... 422” | Length 255 valid, 256 invalid; missing/empty separately 400. |
| R1-056 | “limit ... 1 to 200 ... offset ... 0 or more” | Both list endpoints default and boundary pagination, invalid ranges. |
| R1-057 | “Requests must not produce 5xx ... concurrent load” | Reject any 5xx during deterministic, fuzz and concurrent suites. |
| R1-058 | “signup ... 201 ... user_id, display_name, token” | Assert shape, status, identity and immediately usable token. |
| R1-059 | “login ... 200 ... user_id, display_name, token” | Assert identity and token for all seeded/new accounts. |
| R1-060 | “Email already registered ... 409 email_taken” | Duplicate signup rejects without changing original account. |
| R1-061 | “Password shorter than 8 ... 422” | Signup lengths 7 and 8. |
| R1-062 | “email ... local@domain ... 422” | Missing local or domain or at sign fails signup. |
| R1-063 | “Wrong password or unknown email ... 401” | Both login failures. |
| R1-064 | “handle ... already taken ... 409 handle_taken, and no account” | Reattempt same email using a valid unique local part after collision; verify no login for failed account. |
| R1-065 | “Every other endpoint requires a bearer token” | Protected endpoint matrix; explicit test-control exceptions apply. |
| R1-066 | “Tokens do not expire ... multiple valid tokens ... concurrent sessions” | Login twice; both tokens continue working after writes and import. Long-time expiry requires external inspection. |
| R1-067 | “password-hashing function ... Plaintext ... not permitted” | Independent auditor must inspect storage design; modeler never reads product source or prints export credentials. |
| R1-068 | “Five write paths require an idempotency key” | Payment, request, pay, split, settlement each reject absent/empty key with 400. |
| R1-069 | “scoped to the authenticated user” | Same literal key from two users creates two independent successful writes. |
| R1-070 | “same method ... same path ... same body ... different path ... succeed normally” | Same key/body on different request-pay paths succeeds independently. |
| R1-071 | “First use ... 201 ... Replay ... 200 ... body identical” | All five paths exact full JSON equality on replay. |
| R1-072 | “Same key, different body ... 409 idempotency_key_reuse” | Modify one field and extra unknown field after success. |
| R1-073 | “after ... failed with 4xx ... first use” | Validation, permission and insufficient-funds failures do not claim keys. |
| R1-074 | “same JSON value ... key order and whitespace do not matter” | Reorder keys and alter JSON whitespace/numeric lexical form for replay. |
| R1-075 | “concurrent identical ... exactly one ... 201 ... others ... 200” | 50 identical writes return one creation, 49 identical replays and one effect. |
| R1-076 | “even after ... resource changes or ... cancelled” | Create request, cancel, replay create yields original pending response, no new request. |
| R1-077 | “claimed key ... before endpoint field validation or current-resource checks” | Successful key changed to amount null yields 409, terminal pay replay remains 200. |
| R1-078 | “GET /me” | Assert user_id, display_name, handle, balance, currency and minor_units values. |
| R1-079 | “note ... defaults ... empty ... visibility ... public” | Payment omission defaults; null rejected. |
| R1-080 | “POST /payments ... 201” | Assert parties, handles, amount, currency, note, visibility, null request_id, timestamp, ID, null settlement_id. |
| R1-081 | “caller's balance ... below amount ... 409 insufficient_funds” | No balances/feed/idempotency effects on failure. |
| R1-082 | “amount below 1 ... above 1000000000 ... not an integer ... 422” | Edge values across direct payment, request, split and settlement entries. |
| R1-083 | “own handle ... 422 self_payment” | Direct payment and settlement self-transfer rejected. |
| R1-084 | “note longer than 200 ... 422 ... verbatim” | Empty/space/Unicode/escaping roundtrip, 200 accepted and 201 rejected. |
| R1-085 | “visibility ... neither public nor private ... 422” | Wrong strings and types fail consistently. |
| R1-086 | “No user has that handle ... 404” | Unknown recipient and payer, no state change. |
| R1-087 | “failed payment leaves no trace in either” | Exact model state and feeds remain unchanged after each failure. |
| R1-088 | “POST /requests ... caller is requester” | Assert request shape, parties, pending, null payment_id, currency/note/ID/time. |
| R1-089 | “own handle ... 422 self_request” | Self request rejected. |
| R1-090 | “pay ... body ... visibility only, optional, default public” | Unknown fields ignored; visibility controls generated payment. |
| R1-091 | “{} and {visibility: public} ... different JSON values” | Same key across explicit and omitted default returns 409. |
| R1-092 | “Returns 201 ... payment ... request_id ... paid ... payment_id” | Cross-link request and resulting payment; exactly one monetary effect. |
| R1-093 | “request is not pending ... 409 request_not_pending” | New pay key on each terminal state fails. |
| R1-094 | “Replaying ... already paid ... no additional money” | Pay replay returns original 200 before terminal-state check. |
| R1-095 | “decline ... No idempotency key ... 200 ... already-declined ... 200” | Two declines succeed; paid/cancelled fail 409; nonpayer 403. |
| R1-096 | “cancel ... already-cancelled ... 200 ... paid or declined ... 409” | Two cancels succeed; incompatible terminal states reject; nonrequester 403. |
| R1-097 | “GET /requests ... only ... requester or payer ... Newest first” | Exact authorized set and descending creation order, with tie freedom. |
| R1-098 | “direction ... incoming ... outgoing ... absent ... both” | Filter each role and reject unknown enum. |
| R1-099 | “status ... four statuses, or absent for all” | Filter each state; unknown enum fails 422. |
| R1-100 | “limit defaults to 50 ... offset defaults to 0” | Omitted pagination equals explicit defaults, correct page slices. |
| R1-101 | “has_more ... items exist beyond ... last ... returned” | Full, partial, empty and out-of-range pages compute boolean correctly. |
| R1-102 | “splits ... creating one pending request each” | Exact request count and payer amounts, no direct balance change. |
| R1-103 | “caller ... included ... or omitted ... order ... given” | Both list forms use exactly supplied participants and order (A1). |
| R1-104 | “every participant except caller ... caller as requester” | Generated request parties and order match filtered participants. |
| R1-105 | “shares ... every participant ... sums to amount” | Validate all share objects, total, order, response split metadata. |
| R1-106 | “empty ... duplicate handle ... 422” | Empty/duplicate split lists fail atomically. |
| R1-107 | “Any handle is unknown ... 404” | Unknown later participant creates no earlier requests. |
| R1-108 | “only participant ... caller ... valid ... requests: []” | Self-only split succeeds without balance check. |
| R1-109 | “Nothing about a split checks anyone's balance” | Huge splits with zero-balance participants succeed. |
| R1-110 | “GET /activity ... newest first ... same second ... unspecified” | Exact visible set, descending seconds; pagination tie tolerance. |
| R1-111 | “limit and offset ... exactly as ... requests” | Reuse list validation/default/error matrix on activity. |
| R1-112 | “whole minor units ... sum exactly ... differ by at most one” | Integer division model for supplied examples and random positive amounts. |
| R1-113 | “larger shares ... first participants ... order” | Permute participants; extra units follow list indices. |
| R1-114 | “share of 0 is legal ... still produces a request” | Split amount 1 among three; observe/pay zero requests. |
| R1-115 | “Each split's shares are independent ... sum ... seeded total” | Repeated reordered splits and full payments preserve total. |
| R1-116 | “export ... import ... unauthenticated” | Both endpoints work without token. |
| R1-117 | “Return 200 ... track: pocketful, format_version: 1 ... state ... object” | Validate envelope only; keep opaque state in memory, never print. |
| R1-118 | “Import ... entire object ... atomically replaces ... 204” | Import after destructive reset restores all observed behavior. |
| R1-119 | “No dependency on source process, files, volume, port or network address” | Export one instance, import another clean instance. |
| R1-120 | “replacement, not merge ... repeating ... without duplicating” | Add destination-only account/records; import twice removes them both times. |
| R1-121 | “Invalid JSON follows §5 ... missing ... wrong track/version ... invalid state ... 422 ... without changing” | Malformed import 400; envelope/state failures 422 with unchanged observables. |
| R1-122 | “Test control calls ... 10-second timeout” | Deadline reset/import/export calls at 10 seconds. |
| R1-123 | “Export ... atomic, read-only snapshot ... writes do not change it” | Export, mutate source, import earlier snapshot and compare earlier state. |
| R1-124 | “Preserve accounts and hashed-password login, existing bearer tokens, currency, balances” | Pre-export tokens and fresh login both work after import; balances/identity exact. |
| R1-125 | “payments, requests, permissions ... completed idempotent ... bodies ... original responses” | Restore receipts, statuses, operator permission and every write replay exactly. |
| R1-126 | “Identities, timestamps ... must not be regenerated or replayed” | Exact original receipt values and net balances after import. |
| R1-127 | “Failed request keys remain reusable” | Export after a failed key then import; valid reuse creates 201. |
| R1-128 | “Import removes all previous destination data and credentials” | Destination token/login and records vanish. |
| R1-129 | “Reset clears all state, including imported state” | Reset after import removes restored tokens, records, permissions and retry cache. |
| R1-130 | “settlement_operator_ids ... default []” | Missing permission list grants nobody; designated operator can submit. |
| R1-131 | “across any wallets ... does not grant access ... private” | Operator can transfer between others but cannot see their private receipts or requests. |
| R1-132 | “No token ... 401 ... non-operator ... 403” | Settlement authorization matrix before monetary effects. |
| R1-133 | “transfers contains 1..32 objects” | Empty, 33, nonarray, nonobject entries fail 422; 1 and 32 valid. |
| R1-134 | “ordinary payment amount, note and visibility rules ... defaults” | Reuse direct-entry validation matrix plus omission defaults. |
| R1-135 | “Unknown handle ... 404 ... self ... 422 ... malformed batch shape ... 422” | Entry/shape code matrix and no mutations. |
| R1-136 | “Entry errors take precedence in input order, before insufficient funds” | First unaffordable valid entry, later invalid entry: invalid wins; two errors select earlier. |
| R1-137 | “affordable ... after all incoming and outgoing ... nonnegative” | Funded net cycle succeeds even if an individual outgoing exceeds initial balance. |
| R1-138 | “Insufficient collective funds ... 409” | Net-negative batch fails without partial transfers. |
| R1-139 | “all movements ... together or none ... no ... key ... payment or revision” | Compare exact observations and valid same-key retry after rejected batch. Revision not public in stage 1. |
| R1-140 | “201 ... settlement_id, committed_at and payments in input order” | Validate batch receipt identity, timestamp and ordered member list. |
| R1-141 | “ordinary payment ... settlement_id ... nonmembers ... null” | Validate batch linkage and null linkage on direct/request payments. |
| R1-142 | “null request_id ... same ... created_at, equal to committed_at” | Compare all member times and request linkage. |
| R1-143 | “ordinary activity-feed visibility ... response contains every member” | Private members hidden from operator's activity when not a party, but present in batch response. |
| R1-144 | “Replays ... 200 ... original complete response” | Exact batch retry, including after import and subsequent payments. |
| R1-145 | “reset/import ... preserve ... permissions ... membership ... retry responses” | Reset loads fixture permissions; import restores historical batch linkage and cache. Reset otherwise clears prior state per §3/§10. |

## Coverage and evidence

The executable check is `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --base-url URL`. Coverage means an executable refutation exists, **not** that the product passed it. A failing early check stops the run, so later checks remain not verified on that run. No provided-check coverage has been established.

**Covered by own checks:**

- `model.transition` plus `Runner.run/observe`: R1-001, R1-004, R1-005, R1-018–024, R1-026, R1-030–041, R1-043, R1-045–057, R1-068–074, R1-076–111, R1-113–115, R1-130–144. Some properties in these entries have the limits below.
- `auth_and_controls`: R1-015–017, R1-027, R1-042, R1-044, R1-058–063, R1-078, R1-129–130.
- `persistence`: R1-116–118, R1-120–128, R1-145. Cross-process R1-119 is covered only when `--second-url` is supplied; without it R1-119 is unchecked.
- `concurrency`: R1-075 for the direct payment path; other four paths remain unchecked concurrently.
- `self_test`: R1-112 supplied zero-share example plus random rounding. A pure-model self-test does not test the product; live split checks cover the model-derived share values.

**Partial or unchecked work queue:**

- R1-002: observed balances checked after each operation; transient internal nonnegativity is unchecked.
- R1-003: sequential retries/new-key terminal payments checked; concurrent pay/decline/cancel race is unchecked by this driver.
- R1-006–014: deployment/resource/readiness/load requirements require gatekeeper evidence. Driver enforces individual call deadlines (R1-012); own live container uses 2 CPUs/2 GiB and 50 identical payments but does not exhaust the load contract.
- R1-025/028/064: successful derived handle and collision code checked; proof of immutable handle and no account after failed collision is incomplete.
- R1-029: initial zero balance checked; immediate incoming payment/request for newly signed-up user remains unchecked.
- R1-041: high balances and 1e9 edge checked; arbitrary decimal lexical precision beyond Python float precision is unchecked.
- R1-041 inclusive-boundary extension: reset at exactly 2^53, one-unit debit and credit, net-zero settlement with incoming entry first, totals above 2^53, and repeat cross-process import are checked by `balance_boundary`.
- R1-065: unauthenticated reads and ordinary modeled user checks covered; full unauthenticated write matrix remains unchecked.
- R1-066: two active sessions checked; unbounded token lifetime is not empirically established.
- R1-067: password storage intentionally unchecked by modeler, who cannot read product source.
- R1-069–074: deterministic witnesses plus replay of all successful paths; exhaustive cross-product of every key rule and write path remains unchecked.
- R1-097/110: list time order checked to seconds; subsecond request ordering is conservatively unchecked. Complete list membership/values are checked exactly; arbitrary page membership among timestamp ties is not overconstrained.
- R1-101: page length and has_more checked; full pagination membership is checked during collection enumeration with no concurrent writes.
- R1-112: split examples/random sequences check rounding, not exhaustive all participant counts and amount combinations.
- R1-123: read-only snapshot restoration checked; concurrent export snapshot atomicity remains unchecked.
- R1-139: balances, receipts and failed-key reuse checked; internal revision changes are not observable in this stage.

**Observed evidence:** at verification revision e8dfb7d, `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --self-test` exited 0 with `MODEL SELF-TEST PASS operations=663`. Against product b5fac7f, the live command above with URL `http://127.0.0.1:18081 --steps 100` exited 1: `operation status /requests/rq_seed/decline: expected 403, observed 404 not_found`. Deletion shrinking found one operation after 14 attempts. This refutes R1-033/R1-095 on that revision; remaining later checks were not verified. The builder subsequently committed 2299fe8 to correct request-action authorization; recheck pending.

**Completed recheck:** product 2299fe8, built into two isolated containers with `--cpus=2 --memory=2g`, passed `PYTHONDONTWRITEBYTECODE=1 python3 -u stage-1/verification/model/driver.py --base-url http://127.0.0.1:18081 --second-url http://127.0.0.1:18082 --steps 100` with exit 0 and `DIFFERENTIAL PASS operations=263 seed=20261001 persistence=pass concurrency=50 auth-controls=pass`. This includes R1-119 cross-process import. The verifier first required two corrections: exact URL-segment binding (67dbebc), and removal of one excess character from its hardcoded 20-character signup-handle expectation. Neither verifier error was attributed to the product. The coverage limits above still apply; this result is not independent gatekeeper acceptance.

**Inclusive-boundary recheck:** product 145a95f was built from a clean clone and run in two isolated containers limited to 2 CPU/2 GiB. `PYTHONDONTWRITEBYTECODE=1 python3 -u stage-1/verification/model/driver.py --base-url http://127.0.0.1:18231 --second-url http://127.0.0.1:18232 --steps 100` exited 0: `DIFFERENTIAL PASS operations=263 seed=20261001 persistence=pass concurrency=50 auth-controls=pass boundary=pass`. The model self-test also exited 0: `MODEL SELF-TEST PASS operations=663 boundary=pass`.


# Stage 2 additions

## Stage 2 ambiguity readings

- S2-A1: visible RFC3339 authorization expiry overrides the brief's hidden-exact-time preference (conflict sent to coordinator).
- S2-A2: clock-expired capture returns authorization_expired even after read materializes expiry; captured/voided returns authorization_not_open. Pending coordinator ruling; no precedence claim until resolved.
- S2-A3: captured_amount/payment_ids persist after void/expiry; remaining_amount is zero when closed rather than amount minus captured.
- S2-A4: arbitrary new fields in migrated historical replay receipts must not be synthesized if doing so changes the original JSON response. Earlier cached receipt equality controls replay; newly read ordinary payments include authorization_id:null.
- S2-A5: model takes explicit logical time as operation input, never reads a clock internally. Live driver binds service timestamps; no time-sensitive random run crosses deadlines accidentally.

## R2 entries

All entries start **unchecked**. Each row specifies an intended falsifier, not observed evidence. Provided checks remain uninspected.

| ID | Quoted text / excerpt | Reading and refuting check | Coverage |
|---|---|---|---|
| R2-001 | “The stage-1 requirements continue to apply” | Run inherited differential suite and migration; R1 IDs retained. | unchecked |
| R2-002 | “screens must be reachable by URL” | Browser direct visits /, /requests, /split, /signup, /login, /authorizations at both widths. | unchecked |
| R2-003 | “Other screens must be reachable through the UI” | Follow navigation without address-bar edits. | unchecked |
| R2-004 | “Return the UI for Accept: text/html” | GET shared routes with HTML accept receives usable HTML; absent accept receives JSON. | unchecked |
| R2-005 | “UI must expose the data-testid attributes” | Check each separately numbered selector row below, presence and semantics. | unchecked |
| R2-006 | “coherent, presentation-ready consumer finance product” | Human/browser visual review, no raw API dumps as UI. | unchecked |
| R2-007 | “Available funds must be the clearest monetary value” | Compare visual prominence available versus total and held with active holds. | unchecked |
| R2-008 | “status, direction, privacy and money movement should be understandable” | Inspect populated rows for readable semantic labels. | unchecked |
| R2-009 | “consistent visual system for typography, spacing, colour, controls and feedback” | Compare all six screens and states. | unchecked |
| R2-010 | “Primary actions must be easy to identify” | Inspect action hierarchy at 375 and1440. | unchecked |
| R2-011 | “Available, held, pending, loading, successful, refused and uncertain states must be visually distinct” | Capture and compare each state with textual/noncolour cues. | unchecked |
| R2-012 | “Format people, amounts and timestamps for people first” | Review handles/names, exact formatted amounts and human timestamps except required expiry. | unchecked |
| R2-013 | “375 CSS-pixel viewport ... without horizontal page scrolling” | Assert document scrollWidth <= innerWidth at375 and1440 on all screens/states. | unchecked |
| R2-014 | “Inputs need visible labels” | Match every form input with visible accessible label. | unchecked |
| R2-015 | “keyboard focus must be apparent” | Tab through controls and capture focus state. | unchecked |
| R2-016 | “text and controls need sufficient contrast” | Check WCAG AA text/control contrast at both widths. | unchecked |
| R2-017 | “considered empty, loading and error states” | Exercise data empty, delayed response and refusals per screen. | unchecked |
| R2-018 | “navigation consistent across required routes” | Compare common navigation destinations and placement. | unchecked |
| R2-019 | “signup-email, signup-password, signup-display-name” | Inputs visible on /signup; enter values and submit signup-submit. | unchecked |
| R2-020 | “login-email, login-password, login-submit” | Inputs/button visible on /login; valid and invalid sign-in. | unchecked |
| R2-021 | “auth-error ... Present only when there is one” | Failed auth displays; successful auth removes node. | unchecked |
| R2-022 | “current-user ... every screen ... contains display name” | Visit all routes signed in and compare caller display name. | unchecked |
| R2-023 | “current-handle ... exactly caller's handle” | Assert text equality, no @ or words. | unchecked |
| R2-024 | “logout-button” | Click logout; authenticated state removed and protected data inaccessible. | unchecked |
| R2-025 | “wallet-balance ... exactly formatted ... data-amount” | Compare total display and numeric attribute to API across EUR/JPY/BHD. | unchecked |
| R2-026 | “pay-handle, pay-amount, pay-note” | Type handle, decimal amount and verbatim note; verify resulting API receipt. | unchecked |
| R2-027 | “pay-visibility ... public or private” | Assert option values and payment privacy from both parties and outsider. | unchecked |
| R2-028 | “pay-submit” | Submit valid payment and observe exactly one transfer. | unchecked |
| R2-029 | “pay-error ... refused ... insufficient funds” | Trigger insufficient available and validation refusal, inspect error. | unchecked |
| R2-030 | “request-handle, request-amount, request-note, request-submit” | Submit request above payer funds; compare pending request. | unchecked |
| R2-031 | “request-error ... request refused” | Invalid/self/unknown request shows error. | unchecked |
| R2-032 | “Keep pay form values after success” | Assert all input values unchanged after successful submit. | unchecked |
| R2-033 | “again without changing a field must not send another payment” | Repeat submit; one feed receipt, one debit, no pay-error. | unchecked |
| R2-034 | “Changing a field ... new payment request” | Alter each field independently and verify new key/operation. | unchecked |
| R2-035 | “decimal with exactly minor_units ... single space ... currency” | Assert e.g.100.00 EUR,1200 JPY,1.234 BHD, no sign. | unchecked |
| R2-036 | “15.00 and15 ...1500;15.5 ...1550” | Browser request interception checks decimal-to-minor conversion. | unchecked |
| R2-037 | “Nonnumeric ... more than minor_units ... without sending” | Invalid decimal shows form-specific error and zero network writes;15.005 never rounded. | unchecked |
| R2-038 | “activity-list ... children newest first in DOM” | Seed ordered timestamps; inspect DOM order; allow equal timestamps either order. | unchecked |
| R2-039 | “activity-item-{payment_id} ... data-visibility” | One item per API-visible payment, correct attribute; private outsider excluded. | unchecked |
| R2-040 | “activity-parties-{payment_id} ... both handles” | Compare sender and recipient handles. | unchecked |
| R2-041 | “activity-amount-{payment_id} ... exactly formatted” | Compare each amount with currency precision. | unchecked |
| R2-042 | “activity-note-{payment_id} ... exactly note ... even empty” | Check whitespace, Unicode, empty note node and text equality. | unchecked |
| R2-043 | “empty-activity ... instead of list” | Empty fixture shows empty node and no list. | unchecked |
| R2-044 | “incoming-list, outgoing-list” | Requests grouped by caller payer/requester role, no unrelated rows. | unchecked |
| R2-045 | “request-item-{request_id} ... data-status” | Compare status attribute with current API state. | unchecked |
| R2-046 | “request-amount-{request_id} ... exactly formatted” | Compare precision and currency across fixtures. | unchecked |
| R2-047 | “request-pay-{request_id} ... only pending incoming” | Assert presence iff role/status predicate, then pay. | unchecked |
| R2-048 | “request-decline-{request_id} ... only pending incoming” | Assert presence iff predicate, then decline. | unchecked |
| R2-049 | “request-cancel-{request_id} ... only pending outgoing” | Assert presence iff predicate, then cancel. | unchecked |
| R2-050 | “request-error ... pay, decline or cancel refused” | Force stale state for each action and inspect refusal. | unchecked |
| R2-051 | “empty-requests ... both lists empty” | Check both-empty versus single-nonempty fixtures. | unchecked |
| R2-052 | “split-amount ... same rule as pay-amount” | Validate decimal parsing/no-network rejection for splits. | unchecked |
| R2-053 | “split-handles ... commas, in order” | Enter ordered handles and inspect server request order. | unchecked |
| R2-054 | “split-note, split-submit” | Submit and verify verbatim note in created requests. | unchecked |
| R2-055 | “split-preview ... before submitting ... one split-share per participant” | Assert preview before any POST; change fields to recompute. | unchecked |
| R2-056 | “split-share-{handle} ... exactly formatted” | Assert allocation including zero and remainder by order. | unchecked |
| R2-057 | “preview and submitted split ... identical shares” | Compare DOM shares to captured API response after submit. | unchecked |
| R2-058 | “After any successful action ... new state without manual reload” | Compare same-page balance/feed/requests after each write. | unchecked |
| R2-059 | “Navigation must wait for write to succeed” | Delay response; navigation/data refresh cannot precede success. | unchecked |
| R2-060 | “no live-update requirement” | Do not require polling or remote updates absent action/refresh. | unchecked |
| R2-061 | “wallet-refresh ... without clearing pay form” | Change remote state, click refresh, assert balances/feed fresh and inputs retained. | unchecked |
| R2-062 | “Latest refresh wins” | Delay earlier GET responses past later ones; newer view must remain. | unchecked |
| R2-063 | “refused payment ... refreshes balance/feed ... preserves inputs” | Spend remotely then submit stale form; assert refusal and fresh values. | unchecked |
| R2-064 | “request cancelled elsewhere ... request-error ... stale pay button disappears” | Cancel in other client, click stale pay, check refreshed terminal row. | unchecked |
| R2-065 | “payment response lost ... pay-uncertain ... not pay-error” | Abort committed response; uncertainty nonempty, rejection absent. | unchecked |
| R2-066 | “unchanged form retryable ... same key and body” | Intercept retry after response loss and compare parsed body/header. | unchecked |
| R2-067 | “Successful retry removes both ... moves money exactly once” | Recover receipt and compare one debit/feed row plus no error/uncertainty. | unchecked |
| R2-068 | “No ... recovery across page reloads required” | Restrict uncertain/migration tests to same document session. | unchecked |
| R2-069 | “same balance refresh rules ... available and held” | Out-of-order reads with created/voided holds cannot roll values back. | unchecked |
| R2-070 | “accept export ... stage-1 service” | Import unmodified opaque export from frozen stage1 process into stage2. | unchecked |
| R2-071 | “browser signed in ... remain signed in afterwards” | Existing bearer token used after import without login/reload. | unchecked |
| R2-072 | “Existing pending requests remain payable” | Imported request pay via retained browser session succeeds. | unchecked |
| R2-073 | “lost before export ... same body and key ... original payment” | Commit stage1 payment/drop response, import, retry and compare exact original receipt. | unchecked |
| R2-074 | “form and pending retry identity must survive upgrade” | Preserve input values/key/body through import between requests. | unchecked |
| R2-075 | “sum ... total ... seeded” | Sum exact integer totals after every model operation, including captures. | unchecked |
| R2-076 | “hold moves no money” | Authorization changes held/available only; totals/feed unchanged. | unchecked |
| R2-077 | “available = total − held ... never negative” | Assert each wallet identity and nonnegativity after every operation/read. | unchecked |
| R2-078 | “Held funds cannot fund ... payments, authorizations or settlement net debits” | Reserve funds then exercise each debit and request payment against available. | unchecked |
| R2-079 | “Captures may spend ... reserved” | Fully hold payer, capture succeeds despite zero available. | unchecked |
| R2-080 | “Cumulative captures must not exceed authorized amount” | Random partial captures and remaining+1 rejection; failed capture no change. | unchecked |
| R2-081 | “Each idempotent capture moves money once” | Concurrent/sequential replay returns original receipt, one debit. | unchecked |
| R2-082 | “closed hold cannot be captured again” | Capture/void/expire then fresh capture key rejected. | unchecked |
| R2-083 | “balance equals total ... available ... held” | GET/me required fields exact; no-hold agreement and held0. | unchecked |
| R2-084 | “payments ... immediate ... no intermediate hold” | Payment response and subsequent authorization listing show no implicit hold. | unchecked |
| R2-085 | “request ... immediate ... authorizing ... out of scope” | Request pay produces ordinary payment, no authorization. | unchecked |
| R2-086 | “POST /splits unchanged” | Run inherited rounding,zero-share and no-balance checks with holds present. | unchecked |
| R2-087 | “seven idempotent write paths ... independently” | Reuse key across paths and users; per-path identical200/different409/failure reusable. | unchecked |
| R2-088 | “authorization_ttl_seconds ... defaults600 ... positive integer” | Omitted defaults600; invalid0,-1,fraction,bool,string rejects reset without mutation. | unchecked |
| R2-089 | “Seeded authorisations ... own absolute expires_at” | Fixture expiry unaffected by default TTL. | unchecked |
| R2-090 | “available derived, never seeded” | Supply misleading available in fixture; compute from total/open holds. | unchecked |
| R2-091 | “seeded unexpired open holds larger ...422 ... changing nothing” | Overheld reset rejection preserves prior tokens, balances,records,keys. | unchecked |
| R2-092 | “Seeded status ... open,captured,voided,expired ... Only open holds” | Seed each status and check held/open remainder. | unchecked |
| R2-093 | “omit authorizations ... empty list” | Earlier fixture accepted, list empty and held0. | unchecked |
| R2-094 | “expires_at at or before now ... expired ... no funds” | Pure clock equality test and live past/future seeds. | unchecked |
| R2-095 | “Reads and writes must reflect expiry ... no request at deadline” | Sleep past short TTL then read/list/debit, released remainder visible. | unchecked |
| R2-096 | “GET/authorizations ... expired ... GET/me ... released remainder” | Compare status filters and exact available after clock passage. | unchecked |
| R2-097 | “POST/authorizations ... key required ... caller payer” | Missing/empty/long key; assert sender identity cannot be overridden. | unchecked |
| R2-098 | “note and visibility ... same defaults” | Omitted empty note/public; explicit null rejected422. | unchecked |
| R2-099 | “expires_at is created_at plus ttl” | Compare parsed timestamps and configured/default TTL exactly. | unchecked |
| R2-100 | “available below amount ...409 insufficient_funds” | Reserve greater than available; failed key reusable after release. | unchecked |
| R2-101 | “amount below1 above1e9 not integer ...422” | Numeric integral acceptance and invalid type/value edge matrix. | unchecked |
| R2-102 | “own handle ...422 self_payment” | Self-authorization rejected and no hold/key claim. | unchecked |
| R2-103 | “note over200 ... visibility neither ...422” | Unicode code point length and all invalid visibility types. | unchecked |
| R2-104 | “No user has handle ...404” | Unknown recipient creates no hold and key reusable. | unchecked |
| R2-105 | “open authorisation ... not feed item” | Feed unchanged on reserve,void,expiry; capture alone adds payment. | unchecked |
| R2-106 | “Only receiver ... capture” | Payer/third-party403; unknown404; no monetary change. | unchecked |
| R2-107 | “capture amount optional ... remaining” | Omitted amount captures current remainder, not original authorization amount. | unchecked |
| R2-108 | “{} and explicit amount ... different ...409” | Same key semantic-equivalent different body rejected before current state checks. | unchecked |
| R2-109 | “capture201 ... payment ... authorization_id ... request_id null” | Compare full ordinary receipt plus linkage/null request. | unchecked |
| R2-110 | “payment note and visibility copied” | Capture request unknown overrides ignored; original note/privacy in payment/feed. | unchecked |
| R2-111 | “without authorization ... authorization_id null” | Seed/direct/request/settlement payments expose null. | unchecked |
| R2-112 | “default captured ... releases remainder immediately” | Partial final capture closes, remaining0, available rises by uncaptured share. | unchecked |
| R2-113 | “second capture after final ...409 authorization_not_open” | Fresh key after final must fail; original key still replay200. | unchecked |
| R2-114 | “final boolean default true” | Omitted true; false retains; nonboolean malformed400 under generic type rule. | unchecked |
| R2-115 | “final:false and remainder ... stays open” | Multiple partial captures update cumulative and latest payment_id. | unchecked |
| R2-116 | “entire remainder closes ... final:false” | Exact remaining closes captured and remaining0. | unchecked |
| R2-117 | “capture_exceeds ... remaining” | After partial capture, amount between remaining+1 and original rejected422. | unchecked |
| R2-118 | “captured_amount cumulative” | Sum capture receipts equals captured_amount across all statuses. | unchecked |
| R2-119 | “payment_id latest ... payment_ids every capture in order” | Compare ordered receipt IDs and latest/null on creation. | unchecked |
| R2-120 | “remaining_amount ... held ... zero closed” | Open amount-captured; captured/voided/expired0. | unchecked |
| R2-121 | “Void and expiry ... partially captured ... preserve records” | Close partial holds, retain captured_amount/payment_ids and payments. | unchecked |
| R2-122 | “not open ...409 authorization_not_open” | Captured/voided terminal states reject new capture. | unchecked |
| R2-123 | “expires_at at/before now ...409 authorization_expired” | Expired capture rejected consistently before/after read; pending ruling precedence. | unchecked |
| R2-124 | “capture amount below1/not integer ...422” | Explicit0,negative,fraction,string,bool,null reject. | unchecked |
| R2-125 | “Only payer may void ... no key” | Receiver/outsider403; payer200 without key. | unchecked |
| R2-126 | “void ... already-voided200 current state” | Repeat void changes nothing and returns same current authorization. | unchecked |
| R2-127 | “captured or expired void ...409 authorization_not_open” | Terminal void rejected; records/balances unchanged. | unchecked |
| R2-128 | “GET authorizations only involving caller” | Public visibility never reveals authorization to outsider. | unchecked |
| R2-129 | “authorizations newest first created_at” | Seed distinct times and paginate; equal-time tie unconstrained. | unchecked |
| R2-130 | “direction outgoing payer incoming receiver absent both” | Test role filters and unknown direction422. | unchecked |
| R2-131 | “status four statuses ... expired never open” | Test each filter and unknown422 after clock passage. | unchecked |
| R2-132 | “limit offset has_more ... requests” | Defaults50/0; limits1..200; plain digits; pagination completeness. | unchecked |
| R2-133 | “wallet-available ... data-amount ... headline” | Exact available formatted and attribute; visually largest number. | unchecked |
| R2-134 | “wallet-held ... data-amount ... absent when zero” | Assert conditional node and exact nonzero held amount. | unchecked |
| R2-135 | “authorize-handle,amount,note,visibility,submit ... same rules” | Decimal conversion/defaults/privacy and submission error/no-network parsing. | unchecked |
| R2-136 | “authorize-error ... refused ... insufficient available” | Force insufficient reservation, inspect error with fresh wallet state. | unchecked |
| R2-137 | “authorization-list ... newest first DOM” | Compare visible party-only rows/order to API. | unchecked |
| R2-138 | “authorization-item-{id} ... data-status” | Check open/captured/voided/expired attributes. | unchecked |
| R2-139 | “authorization-amount-{id} ... formatted authorised amount” | Original amount remains shown after partial capture. | unchecked |
| R2-140 | “authorization-captured-{id} ... only captured” | Node exists iff captured status; text cumulative formatted value. | unchecked |
| R2-141 | “authorization-expires-{id} ... RFC3339 expires_at” | Exact visible timestamp required despite visual brief preference. | unchecked |
| R2-142 | “authorization-capture-amount-{id} ... remaining ... incoming open only” | Prefill remainder after partial capture; hide closed/outgoing. | unchecked |
| R2-143 | “authorization-capture-{id} ... incoming open only” | Presence iff role/status; action captures displayed amount. | unchecked |
| R2-144 | “authorization-void-{id} ... outgoing open only” | Presence iff role/status; action voids hold. | unchecked |
| R2-145 | “authorization-error ... capture or void refused” | Stale/unauthorized/refused actions show error and usable state. | unchecked |
| R2-146 | “empty-authorizations ... list empty” | Empty node shown only with no involving authorizations. | unchecked |
| R2-147 | “reflect seeded and newly created holds ... immediately after reset” | Initial page reads display available/held correctly before user write. | unchecked |
| R2-148 | “Concurrent ... same results ... one at a time ... every read” | Independent gatekeeper linearizable histories for reserve/capture/void/payment/expiry. | unchecked |

## Visual brief requirements (written API/UI requirements take precedence)

| ID | Quoted text | Reading and refuting check | Coverage |
|---|---|---|---|
| R2-149 | “This brief is visual direction from the product owner. The written requirements always win: if anything here conflicts with a requirement, a required element, a required state or an accessibility rule, follow the requirement and note the conflict in the room.” | Independent visual/source-asset review against each quoted prohibition/direction; no reference code/fonts/branding/material copied; written requirements prevail. | unchecked |
| R2-150 | “The reference screenshots in `reference/` show a consumer website whose craft we admire: confident type, rounded colour panels, sticker details, a short branded intro and motion with personality. Take the design language, never the material. Do not copy its code, its fonts, its name, its logo, its illustrations or its words. Everything you ship is written by you and bundled with the service.” | Independent visual/source-asset review against each quoted prohibition/direction; no reference code/fonts/branding/material copied; written requirements prevail. | unchecked |
| R2-151 | “Friendly and bold on the outside, calm and exact where money is shown. Think of a well-made consumer finance app that is fun to open: big confident headings, warm colour, one playful detail per screen, and then numbers, forms and statuses that are quiet, aligned and unmistakable. Playfulness lives in headings, empty states, success moments and the intro. It never touches an amount, a status or an error.” | Independent visual/source-asset review against each quoted prohibition/direction; no reference code/fonts/branding/material copied; written requirements prevail. | unchecked |
| R2-152 | “Bundle all fonts as files served by the service (no outside requests at run time). Use open-licensed fonts only, for example from the Google Fonts catalogue under the SIL Open Font License, and include the licence file next to the fonts.” | Inspect bundled font files/licences and computed family,weight,size,tracking,line-height; compare desktop/phone; verify tabular digits on every amount. | unchecked |
| R2-153 | “- Display: Bricolage Grotesque, weight 800, tight tracking (about -0.02em), line height about 0.85 to 0.95 for large headings. Used for page titles, the brand word and big moments.” | Inspect bundled font files/licences and computed family,weight,size,tracking,line-height; compare desktop/phone; verify tabular digits on every amount. | unchecked |
| R2-154 | “- Text and controls: Figtree, weights 500, 600 and 700.” | Inspect bundled font files/licences and computed family,weight,size,tracking,line-height; compare desktop/phone; verify tabular digits on every amount. | unchecked |
| R2-155 | “- Handwritten accent: Caveat, used sparingly for one short annotation per screen at most (for example a scribbled note beside an empty state). Never for information the user needs.” | Inspect bundled font files/licences and computed family,weight,size,tracking,line-height; compare desktop/phone; verify tabular digits on every amount. | unchecked |
| R2-156 | “- Money: use tabular figures (`font-variant-numeric: tabular-nums`) for every amount so columns align and values do not jump when they change.” | Inspect bundled font files/licences and computed family,weight,size,tracking,line-height; compare desktop/phone; verify tabular digits on every amount. | unchecked |
| R2-157 | “Scale (desktop / phone): hero 96 / 48 px, page title 56 / 36, section 30 / 24, body 18 / 16, small 14. The available balance is the largest number on the page.” | Inspect bundled font files/licences and computed family,weight,size,tracking,line-height; compare desktop/phone; verify tabular digits on every amount. | unchecked |
| R2-158 | “Warm cream page, saturated panels, deep indigo ink. Check every text and control pair for WCAG AA contrast; adjust tints, never the rule.” | Inspect computed colours and AA contrast for each listed state/control; labels/icons must convey each state without colour. | unchecked |
| R2-159 | “- Ink: indigo `#2B2270` for text on light panels, near-black `#0B0B0F` for body text.” | Inspect computed colours and AA contrast for each listed state/control; labels/icons must convey each state without colour. | unchecked |
| R2-160 | “- Page: cream `#FFF8E7`.” | Inspect computed colours and AA contrast for each listed state/control; labels/icons must convey each state without colour. | unchecked |
| R2-161 | “- Panels: sunflower `#FFD24A`, butter `#FAED8F`, aqua `#A4F6F8`, pink tint `#FFDBFD`, indigo `#3B308F` (with white text) for the footer and the intro.” | Inspect computed colours and AA contrast for each listed state/control; labels/icons must convey each state without colour. | unchecked |
| R2-162 | “- Primary action: indigo `#3B308F` with white text. Secondary: white with an indigo 2 px border. The one loud accent is hot pink `#FF3D9A`, for brand moments and highlights only, not for primary actions and never for errors.” | Inspect computed colours and AA contrast for each listed state/control; labels/icons must convey each state without colour. | unchecked |
| R2-163 | “- States, each with an icon or label so colour is never the only signal: available = deep green `#0E7A4B`, held = amber `#B36B00` on a light amber chip, pending = indigo, successful = green, refused = red `#C4271B`, uncertain (outcome not known) = a striped or dashed indigo-grey chip with the words "not confirmed yet".” | Inspect computed colours and AA contrast for each listed state/control; labels/icons must convey each state without colour. | unchecked |
| R2-164 | “- Big rounded panels: 24 px radius on phone, 32 px on desktop, full-width colour sections that sit on the cream page like stacked cards.” | Compare screenshot and computed radii,borders,control sizes at both widths; inspect SVG decoration and reject blurred shadows. | unchecked |
| R2-165 | “- Controls: pill buttons (fully rounded), 48 px tall minimum, bold labels. A button can carry a separate square arrow chip on its right, like a ticket stub.” | Compare screenshot and computed radii,borders,control sizes at both widths; inspect SVG decoration and reject blurred shadows. | unchecked |
| R2-166 | “- Cards: 18 px radius, 2 px ink border or a white 3 px ring on coloured panels, no blurry drop shadows. Sticker details may be rotated 2 to 6 degrees.” | Compare screenshot and computed radii,borders,control sizes at both widths; inspect SVG decoration and reject blurred shadows. | unchecked |
| R2-167 | “- Organic background blobs drawn as inline SVG paths in two tints of the panel colour.” | Compare screenshot and computed radii,borders,control sizes at both widths; inspect SVG decoration and reject blurred shadows. | unchecked |
| R2-168 | “`art/` holds six transparent 3D illustrations made for this product by the product owner (generated images, supplied as assets): `phone-coin`, `coins`, `paper-plane`, `split-receipt`, `hold-padlock` and `wallet`, all WebP. You may copy them into the service and serve them as bundled static files. They are decoration: give each an empty `alt` unless it carries meaning, and never let one replace text the user needs. Suggested use: `phone-coin` on the sign-up and log-in panel, `paper-plane` beside the pay form and in the success moment, `coins` on the balance panel, `split-receipt` on the split screen, `hold-padlock` on the authorisations screen, `wallet` in empty states. Rest them at a slight tilt like stickers. Record in the stage's run document that these images were supplied by the product owner, not made by the band.” | Inspect bundled supplied art,decorative alt text,legibility and RUN attribution; reject external asset requests or missing required attribution. | unchecked |
| R2-169 | “- Sign-up and log-in: the one place for marketing flair. A split layout on desktop: a colour panel with a large display heading, organic blobs, three or four tilted pill "stickers" naming benefits (see `reference/desktop-013.0.jpg`) and a short row of tilted step cards explaining how it works (see `reference/desktop-009.5.jpg`); the form sits on a white card on the other side. Stacked on phone with the form first.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-170 | “- Home: the available balance as the hero number on a sunflower panel with held and total as quiet secondary figures below it; pay and request forms as two clear cards; the activity feed as a scannable list with avatar initials, direction arrow, amount coloured by direction, privacy shown as a small icon and label, and people-first timestamps ("2 min ago", full date on hover or focus).” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-171 | “- Requests: incoming and outgoing as two clearly labelled groups; each row shows who, how much, what for, and a status chip; actions are buttons on the row.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-172 | “- Split: a form that shows each person's share live as the user types, and the total that must match.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-173 | “- Authorisations: holds as cards with the reserved amount, what remains, status and actions.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-174 | “- Every screen: the same top bar with the brand word, navigation to every required screen, and the signed-in person's name; a consistent footer.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-175 | “- Placeholders never look like real data: no real handles, names or amounts as input examples (write "their handle" or "0.00", not a user's name).” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-176 | “- Times: relative for recent events ("2 min ago"), a date in words for older ones ("12 Sep, 14:05"); the exact timestamp only on hover or focus, never as the visible text.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-177 | “- Empty states: an illustration or blob shape, one friendly display line, one helpful line of text and the action that fills the list.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-178 | “- Loading: skeleton rows with a slow shimmer in the page colours, never a bare spinner on its own.” | Browser plan steps1–3 and7–10: inspect each named layout/semantic/state detail; required expiry timestamp exception follows S2-A1. | unchecked |
| R2-179 | “Motion gives personality; it must never cost correctness, speed or access.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-180 | “The personality comes from a handful of rules. Two tempos: springy for objects, crisp for interface. Two easing curves: "snap" `cubic-bezier(0.32, 0.72, 0, 1)` for interface moves (200 to 400 ms) and "glide" `cubic-bezier(0.625, 0.05, 0, 1)` as the default for everything else; springs with light overshoot for stickers only.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-181 | “- Intro: a branded intro of at most 700 ms on first load in a browser session: a fat, rounded brush-stroke shape in indigo sweeps across a sunflower field while the round brand mark pops in and out, then the stroke peels away along its own path to reveal the page. The real page is fully rendered and usable underneath from the first frame; the intro layer ignores pointer events and is removed from the DOM when it ends.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-182 | “- Headlines stretch rather than fade: each word starts squashed (about 10% height, 85% width, shifted right and tilted about 8 degrees, pinned at its top-left corner), becomes opaque almost at once, then springs to full size; words start about 60 to 90 ms apart. Keep the heading's full text available to assistive technology as one string.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-183 | “- Handwritten notes write themselves letter by letter (each letter from a small tilt, about 15 ms apart).” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-184 | “- Stickers (benefit pills, step cards, badges, success confirmations) arrive like a sticker being slapped on: from about 90% size and a tilt, springing to a resting angle that is deliberately not straight (2 to 11 degrees).” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-185 | “- Small labels settle down into place; large objects rise up into place.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-186 | “- Buttons: a springy press (scale 0.97 on press, back with overshoot) and an arrow chip that nudges on hover. On devices with a fine pointer, the label may do a quick squash on hover, animated on a wrapper so the label stays one text node.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-187 | “- New feed items and successful actions: a "plop in" (scale from 0.9 with overshoot, 250 to 350 ms) and a brief tint of the changed number. A successful payment triggers a short burst of about 20 small brand shapes from the button (transform only, hidden from assistive technology, removed when done).” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-188 | “- Ambient life is slow: background blobs may breathe on a 6 s loop, paused when off screen or when the tab is hidden.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-189 | “- Panels: gentle parallax or a slight rise as they enter the viewport on the home screen.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-190 | “- Page changes: use the browser's cross-document view transitions for a quick cross-fade where supported; never intercept normal navigation.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-191 | “- Respect `prefers-reduced-motion`: no intro, no parallax, no bursts; state changes still show instantly.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-192 | “Rules that protect behaviour (follow exactly):” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-193 | “1. Every required element is present, visible and clickable as soon as its data is ready. Nothing required starts at opacity 0 or waits for scrolling to appear.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-194 | “2. No layer ever covers controls while it animates in a way that intercepts clicks.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-195 | “3. No smooth-scroll library and no script that replaces page navigation.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-196 | “4. Animations use transform and opacity only, and no animation may delay a network request, a form submission or a displayed result.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-197 | “5. Numbers shown in required elements are always the final value, never an animated count.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-198 | “6. All animation code and libraries are bundled with the service; plain CSS and small hand-written scripts are preferred over large libraries.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-199 | “7. The interface behaves the same for every visitor. Never detect automation, test tools or particular clients to change behaviour; make every effect safe for everyone instead.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-200 | “8. No native alert, confirm or prompt dialogs, no loops that keep running while nothing is visible, and no effect that moves a control while the pointer is over it.” | Browser motion plan steps8–10: inspect timing, computed styles, reduced-motion and pointer/network traces against every clause quoted; any violated clause refutes entry. | unchecked |
| R2-201 | “Before handing off, capture every required screen in a real browser at 375 px and at 1440 px, in its empty, filled, loading, refused and uncertain states where they exist, and save the images in the verification area. Check contrast and keyboard focus on each.” | Capture all six screens at375/1440 in applicable states; fail if evidence or contrast/focus inspection missing. | unchecked |
