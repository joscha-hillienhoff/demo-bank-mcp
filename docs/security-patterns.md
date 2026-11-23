# Security patterns

Every tool result ends up in the context of a language model, and every tool call is a decision
made by one. These patterns reduce what can go wrong. Code: [`security.py`](../src/demo_bank_mcp/security.py)
and [`server.py`](../src/demo_bank_mcp/server.py). A walk-through with the seeded attack is in
[learn/04-security-patterns.md](learn/04-security-patterns.md).

## Patterns

**Confirmation step.** `prepare_transfer` only creates a draft; `confirm_transfer` executes it,
and the descriptions tell the model to show the summary and get the user's explicit agreement
in between. A single-step "send money" tool would let one wrong model decision move money, so
the human gets a checkpoint where the real recipient and amount are visible.

**Server-side limits and draft rules.** The API refuses transfers above 1,000 EUR, more than 3
per day, drafts older than 5 minutes, unknown drafts and second confirmations. Limits enforced
in the tool or the prompt could be talked around; limits in the API hold no matter what the
model or the host does.

**Least privilege.** Read tools use a token with `accounts:read`; only the two transfer tools
use the token with `payments:write`. A mistake in the read path cannot start a payment, and a
leaked read token cannot move money.

**Audit log.** Every tool call appends one JSON line to `logs/audit.jsonl` (gitignored; the path
can be changed with `DEMO_BANK_AUDIT_LOG`) with timestamp, tool name, arguments and a status of
`ok` or `error`. IBANs in the arguments, including those inside free text, are masked. Results are
not logged, so the log shows what was asked without copying customer data into another place.

**Data minimisation.** Tools return only the fields a task needs: no owner name, no raw API
envelope, masked IBANs for the customer's accounts and for counterparties, and at most 50
transactions per search. What the model never receives cannot appear in a transcript or be
repeated back to someone else.

**Injection guard.** Free text written by third parties (counterparty name and purpose of a
transaction) is returned inside `<untrusted-data>` tags, together with a notice that it is data
and not instructions; angle brackets inside the text are escaped so it cannot close the tag. The
server itself never calls a write tool because of anything it reads: tools only act when the host
calls them.

**Tool annotations.** Read tools are marked `readOnlyHint`, `confirm_transfer` is marked
`destructiveHint`. Hosts can use this to decide when to prompt the user.

## What these patterns cannot guarantee

- **The model decides.** The server cannot see why a model calls a tool. Marking text as
  untrusted and telling the model not to follow it makes injection less likely to work; it does
  not make it impossible. A model can still be talked into preparing a transfer.
- **The host decides.** Whether the user really sees the summary, and whether "yes" means yes,
  is up to the host application. A host that auto-approves every tool call defeats the
  confirmation step. Annotations are hints that a host may ignore.
- **The user can be fooled too.** The summary shows the real recipient, but a user who confirms
  without reading it confirms an attacker's transfer.
- **Masking is not access control.** It reduces what leaks into transcripts. Anyone who can call
  the tools can read the same data.
- **The audit log is local and plain.** It is not tamper-proof, and a failure to write it is
  reported on stderr instead of blocking the tool.
- **Mock limits are mock limits.** Count and amount limits here are per day (UTC) for the whole
  bank, with one user and no balance check.

What protects the money in the end is the combination of the confirmation step and the limits
enforced by the bank API: even a fooled model and a careless host cannot do more than the limits
allow, and every transfer needs a draft that the user had the chance to see.
