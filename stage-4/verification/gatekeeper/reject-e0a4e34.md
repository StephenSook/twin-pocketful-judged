# Rejection: e0a4e34

Clean copy: `/tmp/gatekeeper-s4-qhvnpd4n/product-e0a4e34`.

`PYTHONDONTWRITEBYTECODE=1 python3 stage-4/verification/gatekeeper/refund_batch_import.py http://172.24.0.9:18080` exited 1. Five invalid exported-state edits were accepted with 204 instead of 422:

- Refund note differs from the target.
- Refund visibility differs from the target.
- One batch revision has a different recorded instant.
- Settlement members' batch revisions have different effective instants.
- One corrected settlement member loses its batch ID.

Reproduction: seed a=200, b=0, c=0 with c an operator. Settle a→b100 and b→a100. Batch both amounts to50 at their original effective instant. Make a direct a→b50 and refund10. Export; independently modify each field above; import. The script keeps credentials and exported state in memory and prints only case labels/statuses. Unchanged exports import204; a refund pointing to itself correctly gives422.

The isolated provided harness passed stages1–4 (exit0). Model run_all passed inherited532, temporal75 and refund/batch40 operations, including three legacy imports (exit0). Independent refund/batch semantics and 50-flight races passed870 assertions (exit0). These passes do not close the import failures.
