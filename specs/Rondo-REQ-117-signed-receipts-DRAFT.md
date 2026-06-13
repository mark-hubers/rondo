# Rondo-REQ-117 (DRAFT): Signed, Chained Verification Receipts

*The model reports; rondo verifies; and now rondo SIGNS the verdict with a key
the model never holds, chains it to the previous verdict, and stores it where
the model can't reach. "rondo checked it" becomes "here is tamper-evident proof
rondo checked it, independently re-verifiable."*

**Status:** DRAFT for hostile design review (2026-06-12). NOT built.
**Depends on:** REQ-115 (verified execution — the check), STD-113 (audit), STD-114 (sanitize).
**Driver:** the 2026 verifiable-execution wave (Diagrid/Dapr 1.18, NABAOS signed
tool receipts, authproof-sdk, EU AI Act logging). rondo verifies but does not yet
ATTEST. This closes that gap and matches the emerging best-practice.

---

## 1. The trust property we want

Today (REQ-115): rondo runs the check itself, so the model's `passed=true`
cannot override rondo's observation. Gap: the EVIDENCE rondo records is just a
JSON blob — nothing stops a compromised step (or a later process, or a bug) from
EDITING a past evidence record to read "verified" when it wasn't, and nothing
lets a THIRD PARTY confirm rondo actually ran the check.

After REQ-117, three new guarantees:

1. **Unforgeable** — each verification receipt is signed with a key the MODEL
   never sees (never in a prompt, never in output, stored 0o600 out of reach).
   The model cannot manufacture a receipt that says "verified".
2. **Tamper-evident** — each receipt carries the hash of the previous receipt
   (a chain). Altering ANY past receipt breaks every signature after it; a
   verifier detects the break.
3. **Independently re-verifiable** — `rondo replay <dispatch_id>` re-checks the
   signature AND re-runs the declared checks (re-hash files, re-run cmd), so
   anyone can confirm both "rondo signed this" and "the world still matches".

## 2. Proposed mechanism (the parts the panel must attack)

- **Receipt payload:** `{dispatch_id, verified_at, checks:[{path, sha256, size}
  | {cmd, exit_code, expected}], ok:bool, prev_receipt_hash, seq}`.
- **Signature:** sign `sha256(canonical_json(payload))`. OPEN: HMAC-SHA256
  (symmetric — simple, but the verifier needs the secret) vs Ed25519
  (asymmetric — anyone verifies with the PUBLIC key, only rondo signs with the
  private key). Leaning Ed25519 for true third-party verification.
- **Key storage:** private key generated on first use, `~/.rondo/keys/`, 0o600,
  NEVER sanitized into any payload, NEVER passed to a dispatch. OPEN: rotation,
  loss/recovery, per-tenant keys.
- **Chain:** append-only `receipts.jsonl` (0o600) in the audit dir. Each receipt
  links `prev_receipt_hash`. OPEN: one global chain vs per-dispatch; concurrency
  (two processes appending — reuse the audit flock from STD-110 r016?).
- **Verification CLI/MCP:** `rondo replay <id>` → re-run checks + re-verify sig +
  walk the chain; returns `{authentic, chain_intact, world_matches}`.

## 3. Honest threat model (what it does NOT stop)

- A process that fully controls the host (and the key file) can sign anything —
  this raises the bar (model-in-the-loop can't forge), it is NOT a defense
  against a fully-compromised host. State that plainly (no overclaiming).
- It verifies OBSERVABLE effects (files, exit codes) — never the correctness of
  a free-text answer (REQ-115's existing honest limit carries forward).

## 4. Questions for the hostile review

1. Ed25519 vs HMAC for this use case — which, and why? Key-management traps?
2. Is the chain design sound against reordering / truncation / splice attacks?
   What MUST be in the signed payload to prevent receipt substitution/replay?
3. Where does this leak? Could the signing key end up in an audit field, a
   prompt, a result file, an error message? (rondo's whole point is not leaking.)
4. Concurrency: two rondo processes writing the chain — how, without a torn
   chain or a lost link?
5. What is the SMALLEST honest version that delivers the trust property without
   over-engineering (Mark ships soon)?
6. Does this actually make the system "less able to lie", or is it security
   theater on top of a host the model could already compromise?

---

## 5. HOSTILE REVIEW FINDINGS — Gemini:high + Grok:grok-4.3 via rondo_multi_review (2026-06-12)

Both vendors INDEPENDENTLY converged on the same central flaw (high signal).

### THE KILLER (both): same-UID key theft = theater without a sandbox
If the model has shell access (and in the prompt-coding loop it does — it runs
tests, edits files), it runs under the SAME UID as rondo and can `cat
~/.rondo/keys/*` to steal the private key and forge any receipt. 0o600 does NOT
help against the same user. Verdict: signed receipts are security theater UNLESS
the model's code execution is sandboxed (container) with rondo + key OUTSIDE it.
rondo already uses Apple `container` (RONDO-341) — the execution seam exists.
THIS IS THE DECISION (§6).

### Concrete must-haves both flagged (independent of the sandbox decision)
1. Ed25519, not HMAC (Gemini, strong): HMAC requires sharing the secret to
   verify → destroys independent third-party verification, the whole point.
   (Grok dissent: HMAC + kernel keyring via keyctl avoids on-disk key — but loses
   public verifiability. Ed25519 wins for the stated goal.)
2. Anti-splice fields (both): signed payload MUST include run_uuid (UUIDv7),
   rondo_binary_sha256, key_fingerprint. Without a per-run id a valid "passed"
   receipt from run A splices into run B.
3. Anti-truncation (both): prev_hash detects EDITS, not tail deletion (delete
   last N → valid shorter chain). Anchor it: sign a final MANIFEST of all receipt
   hashes per run, and/or a monotonic seq the verifier checks for gaps.
4. Lock wraps read-sign-append (both): reading prev_hash outside the flock →
   forked chain. The exclusive lock must cover read-prev → sign → append as ONE
   transaction. Single-writer; reject concurrent writers.
5. Replay verifies STATE, not actions (Gemini): re-running arbitrary cmds is
   non-deterministic (network/time/DB) AND TOCTOU (model can edit the file right
   after verify). `rondo replay` re-checks file HASHES + signatures + chain, NOT
   re-exec. The receipt proves PAST state, not current.
6. Key-leak vectors to seal (both): core dumps, /proc/<pid>/environ, error paths
   that stringify the signing context, ~/.rondo/keys/ showing up in a file-glob
   result handed to the model, and a model-authored test printing the key to
   stdout (rondo would capture it in the cmd-output payload).

### Smallest honest version (synthesized)
Ephemeral Ed25519 key PER RUN; each receipt carries run_uuid + seq + prev_hash +
rondo_binary_sha256; single-writer append under exclusive lock; a signed final
manifest of all receipt hashes (anti-truncation); `rondo replay` verifies
hashes+sigs+chain only (no re-exec). Sandbox question per §6.

## 6. THE DECISION this surfaced (Mark's call) — sandbox vs honest-scope
The feature only delivers UNFORGEABLE against a shell-capable model if execution
is sandboxed. Two honest paths:
- (A) Sandbox the model's execution (Apple `container`, key on host): fully
  delivers the guarantee. Bigger — containerize the dispatch seam. Strongest
  launch story ("the model literally cannot reach the key").
- (B) Ship receipts now, scope the claim honestly: receipts defend the
  no-shell/inline/advisory path + integrity-over-time + later-tamper detection,
  and DOCUMENT that a shell-capable same-UID model can defeat them (sandbox the
  fix, roadmapped). Ships in days. Weaker but honest guarantee.
