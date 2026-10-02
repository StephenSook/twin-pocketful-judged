# REJECT 5e403de

The exact clean image passes both isolated harness invocations (clean copy and dispatched shared-repository command), all supplied stages 1–3, claimed stage 3. Modeler run_all.py exits 0 with 532 inherited and 75 temporal operations. These passing checks miss valid seeded hold history during import.

Minimal fixture: wallets a=100, b=0 and authorization `{id:"a_past",from_user_id:"a",to_user_id:"b",amount:10,note:"",visibility:"private",status:"expired",expires_at:"2020-01-01T00:00:00+00:00"}` with created_at omitted. Reset returns 204; export returns 200; importing the unchanged export returns 422 `state authorization history is invalid`, expected 204. The same failure occurs with statuses open, voided and captured. These fixtures are permitted; seeded closed holds need not reconstruct a lifecycle, and an expired-on-arrival open hold never reserves funds.

The real accepted Stage2 image 8038718 exhibits the same migration failure: open/expired seed exports return 422 on import into 5e403de; voided/captured exports import initially but the upgraded Stage3 export cannot re-import. The source container is stopped and removed before destination import.

Reproduce: `PYTHONDONTWRITEBYTECODE=1 python3 stage-3/verification/gatekeeper/seeded_history_import.py http://172.24.0.7:18080 gatekeeper-s2-8038718 gatekeeper-s1-internal`, exit 1. Log: `/tmp/gatekeeper-s3-x6k0z8vs/seeded_history_import-5e403de.log`. Exports and credentials stay in memory; printed evidence contains only status labels and HTTP statuses.

Builder received all eight own-export/migration cases and committed proposed fix c4b5c5f. Full independent acceptance of that successor is still required.
