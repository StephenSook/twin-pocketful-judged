# Stage 4 independent acceptance

Accepted product: `a288cc48240d0ecd6ca2f01c92c0e7f1e2469ca9`.
Stage tree: `37810a489fdcfd6335464527a1d9f5b935f2bbc0`.

`acceptance-a288cc4.json` records every command, exit status, count, ruling, audit closure and limitation. `evidence-a288cc4/` contains summarized results and 88 browser screenshots at 375 and 1440 CSS pixels. Synthetic credentials and exports are never retained.

Run the provided harness first, from `/home/ubuntu/work/dark-factory-wearedevs`:

```sh
.venv/bin/python -m harness run --track pocketful --repo /home/ubuntu/work/band-work/current --stage 4 --mode isolated --out /home/ubuntu/work/band-work/checks/pocketful-judged/s4-1
```

Use fresh services for destructive checks. Run the model wrapper with two stage-4 URLs and frozen stage-1, stage-2 and stage-3 sources, as documented in `../model/RUN.md`. Every `probe.py`-based check accepts the isolated target URL as its first argument. Browser scripts require the harness virtualenv Python and a screenshot output directory. Additional image/network arguments are documented in each script.

Stage-4 additions are `refund_batches.py`, `refund_batch_import.py`, `refund_batch_races.py`, `new_path_controls.py`, `batch_limits.py`, `upgrade_history.py`, `browser_refunds.py` and `mutate_refunds.py`. Earlier gates are copied here so frozen stages remain untouched. Planted faults run only in scratch copies.

The original candidate e0a4e34 failed five invalid-import checks; a288cc4 closes all five. The full gates were repeated on a clean a288cc4 copy. All 22 planted faults are caught. The provided tool claims stage 4; no later suite was reported applicable. No custom next-stage probe was made.
