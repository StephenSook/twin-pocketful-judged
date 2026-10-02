# REJECT c4b5c5f

Exact clean image c4b5c5f543ddf1aa57bdbf4be15c7db2454c5d3a, built and run at 2 CPUs/2 GiB on the internal network. Clean-copy and dispatched shared-repository harnesses exit 0 through stage 3. Modeler run_all exits 0: 532 inherited plus 75 temporal operations.

`seeded_history_import.py http://172.24.0.7:18080 gatekeeper-s2-8038718 gatekeeper-s1-internal` exits 1: own Stage3 seeded exports now pass, but accepted Stage2 open/expired past-expiry exports still import with 422. Voided/captured Stage2 exports initially import, then their Stage3 re-export fails to import. Builder's e33b85a addresses this follow-up; retest pending.

`history_import.py http://172.24.0.7:18080` exits 1 on two additional inconsistent-state cases. Create an authorization of 20, capture 5 nonfinally, export. Independently change either auth_events.noHistory to true or auth_events.initialHold to 19. Both imports return 204, expected 422 with no replacement. The former makes the open hold disappear from historical queries while current /me still holds 15; the latter changes historical held to 14 while current held remains 15. The no-lifecycle exemption for closed seeds cannot apply to an active hold, and the historical initial amount must agree with its authorization/capture records.

Other completed core checks all exit 0: exact arithmetic, lifecycle chronology, default read clock, history, historical holds, mixed correction races, inherited holds/payments, boundaries, large temporal ledger, large-user limits, accepted Stage2 source destruction and migration, API security and password scope. Environment exits 0: 422 assertions, startup 0.4196/0.4259 seconds, maximum request 2.8274 seconds. These do not override the invalid-import failures.

Evidence lives in `/tmp/gatekeeper-s3-x6k0z8vs/*-c4b5c5f.log`; the expanded tamper cases are in `history_import-expanded-c4b5c5f.log`. No export contents or credentials are written to those logs.
