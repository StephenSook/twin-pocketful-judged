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
