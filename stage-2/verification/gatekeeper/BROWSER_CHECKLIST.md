# Stage 2 independent acceptance coverage

This is a pre-candidate checklist, not passing evidence. Only stage-2 verification files may change. Stage 1 is frozen at its accepted product d1ebec2 and later evidence-only commits.

## Automated starting point

`holds.py URL` covers held-funds refusal on each immediate debit path, partial/final/void capture history, expiry precedence, third-party/operator authorization, fifty-way available-funds races with atomic export snapshots and a serial witness, fifty partial captures, and capture-versus-void races. Its opaque-export adapter must be checked against the exact candidate.

`browser_checks.py URL /tmp/EVIDENCE` runs with the existing harness venv's headless Playwright at 375 and 1440 CSS pixels on plain non-loopback HTTP. It covers login, no horizontal overflow, input labels, click interception, decimal rejection without a POST, unchanged-form and lost-response replay identities, reversed refresh responses, holds, expiry text, native navigation, split preview, runtime asset origin, and active animation property checks. It intentionally logs no credentials or response bodies.

## Complete before accepting

- Each required route `/`, `/requests`, `/split`, `/signup`, `/login`, `/authorizations`: direct URL and native navigation, signed-in name/handle, labels, keyboard focus, contrast, 375/1440 overflow; every required testid and exact amount/attribute formatting.
- EUR, JPY, BHD amounts: display precision and decimal parsing; numeric-invalid, overprecision and note/visibility/default semantics; no request on client-side decimal error.
- Capture screenshots at both widths for each route's empty, filled, loading and refused states, plus home uncertain state. Only states applicable to that screen are required. Save working images under /tmp; retain final screenshots under stage-2/verification/gatekeeper/evidence/. Never commit reference images or credentials.
- All feed fields/order/privacy; empty note element; all request groups/statuses/actions, refusal after an external cancel, disappearance of stale pay button; explicit refresh after external spend preserves form.
- Authorizations: outgoing void, incoming capture, prefilled remainder, partial capture data, expired/captured controls absent, status-specific captured amount, exact RFC3339 expiry text (S2-1), seeded holds immediately reflected, available largest monetary value, held hidden at zero.
- Loading evidence by delaying real responses; refused evidence by real API errors; uncertain evidence by committing a payment and dropping its response. Capture successful retry removing both error elements and exactly one money movement.
- Upgrade continuity: build stage1 d1ebec2 source in a clean temporary copy. Obtain source tokens/pending request; import source snapshot into Stage2 target; sign browser in with the preserved source token. Forward one browser payment POST to source, commit then abort response. Export source, stop/remove it, import into target between requests, retry unchanged form on target, and pay the original pending request via UI. Preserve browser form/session without reload. Compare the original receipt as a complete JSON value.
- Reduced motion, first-load intro <=700ms/no repeat in session, background animation pauses offscreen/hidden, control box does not move while hovered. Font families/weights and local license files; bundled owner art with decorative alt and RUN attribution. Compare craft against supplied brief/reference without copying reference material.

## Eight behavior rules — individual verdict required

1. Data-ready required elements visible immediately; sample initial insertion and frames for zero opacity or scroll-triggered withholding. Required amounts always final, including first visible frame.
2. Early-frame hit testing and actual input during intro/animation prove no intercepting overlay.
3. No smooth-scroll library; navigation produces ordinary document requests; no script replacement of normal links.
4. Inspect all animation keyframes and relevant source: only transform/opacity. Timestamp POST dispatch versus click and result visibility; effects never delay either.
5. Observe required amount text and data-amount over frames after writes: no intermediate counters.
6. Every animation/font/image/script asset served locally; runtime has no outbound networking.
7. Inspect product for automation/test/client detection and behavior branches. Required fixture/control endpoints are normative and not such branches.
8. Native dialog events absent; offscreen/hidden effects paused; no ongoing idle effect loop; hovered control bounding box stable.

## Rulings carried forward

S2-3: seeded captured, voided and expired authorizations hold zero. Checks assert status, visibility, zero held and specified refusal codes, without inventing capture history absent from the fixture. Required fallback fields are captured_amount equal to amount for captured (otherwise zero), payment_ids [], payment_id null and remaining_amount zero. Partial-capture history is checked through API operations and exports.

S2-4: a successful Stage 1 receipt replayed after import must equal the original JSON value exactly, without an added authorization_id. Fresh activity reads expose authorization_id:null for non-authorization payments. Upgrade checks must distinguish immutable replay responses from current read representations.

Existing request/capture/void wrong-role parties receive403, unknown IDs404. Balances include2^53 and arithmetic remains exact. Handles lowercase the whole local part before code-point replacement/truncation. Null amounts422; exactly supplied split participants; zero shares payable; note lengths use code points. Fixture seeds may use per-user salted Argon2id1024KiB,t1, upgrading on successful login; signup47104KiB,t2. All test controls retain10s including5000 distinct seeds. Email case-insensitive; timestamps second precision+00:00; unknown routes404/wrong methods405 with envelopes. S2-2: expired capture409authorization_expired even after a read; captured/voided409authorization_not_open even after deadline; void of expired/captured409authorization_not_open.
