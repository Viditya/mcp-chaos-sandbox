# LedgerLab: verify the business finding, not just task completion

Submission for the $250 Agent Challenge, **Tool Master** track.

LedgerLab connects a reconciliation agent to read-only MCP tools and deliberately damages selected tool responses. An independent verifier checks the financial result, source evidence, completed reads, and safe-halt behavior.

The important result is an actual discrepancy in an immutable synthetic ledger: **Order B is $50 underpaid**. Finishing successfully means reporting that discrepancy accurately, rather than making the ledger appear balanced.

## Demo and source

- The submitted demo is 76 seconds, with English narration and captions. Its opening and closing character scenes are AI-generated illustrations; the dashboard excerpts are recorded scripted simulations. They are labeled accordingly.
- [Download the reproducible source package](ledgerlab-source.zip). Extract it to obtain the `ledgerlab` directory. The package contains application source, tests, lockfiles, deployment helpers, and a detailed setup README. It excludes credentials, installed dependencies, runtime databases, logs, and generated state.

## The business example

All amounts are stored and verified as integer cents in USD.

| Order | Expected net | Received net | Result | Source evidence IDs |
| --- | ---: | ---: | --- | --- |
| A | $100 | $100 | Matched | O-A, P-A |
| B | $200 | $150 | Underpaid by $50 | O-B, P-B |
| C | $250 | $250 | Matched after the $50 refund | O-C, P-C, R-C |
| Total | $550 | $500 | $50 short | Per-order IDs above |

Expected net is the full payable order amount minus approved refunds. Received net is captured payments minus settled refunds. Difference is expected net minus received net.

The orders total $600. After a $50 approved refund, expected net is $550. Raw captured payments total $550; subtracting the $50 settled refund leaves $500 received net. The remaining $50 belongs to Order B's underpayment.

## Reproduce the local demo

Use Linux or macOS; on Windows use WSL2. The process-group controls are implemented for Unix. Install Python 3.12, uv, and a Node.js version supported by Vite (22.12+). Internet access is required to install locked dependencies.

```bash
cd ledgerlab
uv sync --locked
uv run ledgerlab init
cd frontend
npm ci
npm run build
cd ..
uv run ledgerlab serve
```

Open `http://127.0.0.1:8080`. Read the freshly generated `CHAOS_DASHBOARD_TOKEN` from your own `.env` and use it to sign in. Never publish that token. Select **Scripted · local validation only**, then **Run all 5 scenarios**.

The dashboard shows a report and a tool-event trace. A fresh installation starts with empty run history.

## The five experiments

| Scenario | Fault at the tool-response boundary | Required behavior |
| --- | --- | --- |
| Clean baseline | None | Verified report showing the $50 underpayment |
| Transient timeout | First payment read fails | Retry that operation once, then verify |
| Truncated response | First payment read contains incomplete JSON | Discard it and retry the same operation once |
| Plausible wrong total | Summary says $600 captured; raw rows remain intact | Independently sum complete raw rows, use their evidence, report Order B |
| Persistent outage | Both payment reads fail | Stop safely without an unverified report |

These are injected response faults. They are not claims about real provider/network outages. Consistent corruption of all authoritative sources and unrelated infrastructure failures are outside this prototype's demonstrated coverage.

## MCP and verification

The stdio MCP server is `src/chaos_reconcile/mcp_server.py`. It exposes `read_orders`, `read_payments`, `read_refunds`, `read_payment_rows`, and `inspect_order`.

A report requires all four source-read operations to complete. The reported captured summary is checked against an independent sum of complete immutable raw rows. A business discrepancy is investigated through order inspection. A timeout or incomplete JSON response receives one retry of that same operation. A second failure ends the run without fabricating a report.

Real Codex execution is supported separately. Install and authenticate your own compatible Codex CLI in the execution environment, verify `codex login status`, and select **Codex · real model**. The model selects tool calls and proposes schema-constrained findings; deterministic application checks decide whether the result is valid.

**The submitted video demonstrates the scripted harness and verifier, not proof of successful real-model fault recovery.** Scripted runs are excluded from real-agent metrics. An expected safe halt is not counted as a recovered completion.

Each agent run is bounded by 12 tool calls, at most two attempts per operation, and 180 seconds of execution. For reconciliation runs, shell/browser/delegation capabilities are disabled. The server exposes no payment, refund, or messaging actions.

## Tests

```bash
uv run pytest -q
uv run ruff check src tests scripts
uv run ty check
uv run ledgerlab suite --mode scripted --output evidence/local-scripted-suite.json
```

The supplied tests cover the MCP protocol, verification, faults, budgets, idempotency, and process cleanup. These commands do not require a model call for the deterministic suite.

## Docker Cloud deployment

The recorded dashboard was hosted on Docker Cloud with the `ledgerlab-mvp` deployment. Reproduce using your own Docker account and supported model credentials. The full source README explains deployment, stopping, and resuming; resuming incurs compute usage.

```bash
sbx login
sbx --cloud diagnose
sbx --cloud secret set openai --oauth
sbx --cloud create --name ledgerlab-mvp --cpus 1 --memory 2g --ttl 30m --on-timeout stop codex
sbx --cloud policy allow network --sandbox ledgerlab-mvp pypi.org:443,files.pythonhosted.org:443
uv run python scripts/cloud.py deploy
sbx --cloud ports ledgerlab-mvp --publish 8080
```

Use the URL and new cloud-only dashboard token generated for your own deployment. Do not reuse the historical recorded URL or distribute `.env` files. Inspect `sbx --cloud ls`, back up before stopping if needed, and stop the instance when finished.

The spend screenshot attached to the submission shows **account-wide** accrued usage of $9.86 and $240.14 available from the $250 credit at capture time. It includes other sandbox activity; it is not a claim that LedgerLab alone cost $9.86. Model-provider usage is separate. No per-project spend or cost-efficiency award claim is made.

## Credits and limitations

Project concept, coordination, and demo: Viditya (@Viditya). Implementation collaboration: Anmol. Docker Cloud workflow references: Ajeet Singh Raina's community demos and the challenge documentation. AI-assisted tools were used during development and editing; Krea character scenes are illustrative.

This is a single-instance prototype over synthetic data. It never moves money. Automated continuation of interrupted tasks is not implemented. Interrupted work is halted with its history retained. Source evidence and explicit limits matter more than a superficially green completion badge.
