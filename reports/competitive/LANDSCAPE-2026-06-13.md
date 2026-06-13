# Rondo Competitive Landscape + Benchmark — 2026-06-13

**Goal (Mark):** scan many loop/agent ideas + code, download the good ones to
learn from + benchmark against, then a deep code-to-code / doc-to-doc / spec
comparison. Honest read of where rondo is good, where it's behind, what to do
before going public.

**Method:** web scan → curated shallow-clone (kept in `reference/loop-repos/`,
gitignored) → read their ACTUAL loop/verify code via parallel Explore agents →
benchmark matrix → honest rating. Grounded in real file:line, not blog summaries.

**Cursor note:** the deep code-to-code/doc-to-doc/spec comparison Mark wants from
Cursor needs Cursor's quota (resets 6/15). Inputs are staged in §6 so it runs
fast then. The analysis below is from Claude + parallel Explore reads of the real
code; an interim cross-vendor panel can run now via rondo's own tools.

---

## 1. What was examined (real code, in reference/loop-repos/)

| Repo | Loop | Verification — WHO observes? | Anti-lying |
|------|------|------------------------------|-----------|
| **mini-swe-agent** | fixed `while True` step loop, LM picks next bash | env detects a magic string + `returncode==0`; the **SWE-bench harness runs the real tests EXTERNALLY** (`environments/local.py:45-56`) | magic-string + exit-code + stateless subprocess; no hash/re-verify |
| **aider** | edit → lint/test → reflect (≤3) in-LLM-loop (`base_coder.py:1585-1623`) | runs lint/tests but **sends the OUTPUT text back to the model to read & fix** — does NOT gate on an independent exit-0 (`commands.py:993-1048`) | structural only (edit-block must match); no semantic pass/fail gate |
| **OpenHands** | distributed, event-driven; agent loop runs inside a Docker agent-server | **trusts the agent-server's event stream** (self-reported); health-checks only, no file/test re-verify in core | Docker sandbox + per-sandbox session keys; no proof-of-work |
| **promptfoo** | NOT a loop — a declarative test/eval harness (run prompt → assert → report) | 70+ assertions: deterministic (regex/json/exit/code) AND llm-graded (rubric); explicit deterministic-vs-LLM boundary | n/a (it's an eval tool, not an agent) |
| **live-swe-agent** | config-tuned mini-swe-agent; "self-evolving" = OFFLINE harness tuning, not runtime | none of its own (relies on SWE-bench) | none documented |
| **loop-engineering** | patterns/docs + npm tools (loop-audit/init/cost); "Five Building Blocks + Memory"; maker/checker split | **maker/checker = an AI checker sub-agent** (AI checks AI) + human gate; not mechanical ground-truth | concept-level; no enforced mechanism |

## 2. Benchmark matrix (rondo vs the field)

Legend: ●=strong, ◐=partial, ○=absent.

| Dimension | rondo | mini-swe | aider | OpenHands | promptfoo | loop-eng | Conductor/bernstein* |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Scripted step-by-step loop control | ● | ◐ | ◐ | ◐ | ○ | ◐(docs) | ● |
| **Verification: who observes?** rondo/independent vs AI-self | **● (rondo runs it)** | ◐ (ext harness) | ○ (model reads output) | ○ (event stream) | ● (harness asserts) | ○ (AI checker) | ◐ |
| Anti-lying depth (fail-closed, contract, cross-vendor) | ● | ◐ | ○ | ○ | ◐ | ○ | ◐ |
| Cross-vendor jury (other AIs review) | ● | ○ | ○ | ○ | ◐ (llm-rubric) | ◐ (maker/checker) | ○ |
| Tool's OWN anti-lying is mutation-tested | ● | ○ | ○ | ○ | ○ | ○ | ? |
| Assertion richness | ◐ | ○ | ◐ | ○ | ● | ○ | ◐ |
| Sandboxing / runtime isolation | ◐ (roadmap) | ◐ | ○ | ● | ○ | ○ | ◐ |
| Tamper-evident signed audit chain | ◐ (REQ-117 draft) | ○ | ○ | ○ | ○ | ○ | **● (bernstein)** |
| Maturity / adoption | ○ | ● | ● | ● | ● | ◐ | ◐ |
| Multi-session memory / context compaction | ○ | ○ | ◐ | ◐ | n/a | ◐ | ◐ |
| Observability dashboard | ○ | ◐ | ◐ | ● | ● | ○ | ◐ |
| Accessibility as design spec | ● | ○ | ○ | ○ | ○ | ○ | ○ |

\*Conductor (Microsoft) / bernstein / Hive / Symphony — not cloned; from the
awesome-harness-engineering catalog + scan (see §3).

## 3. The real competitive picture (honest)

**rondo's core claim holds up in code.** The mainstream coding agents trust the
model MORE than rondo does:
- **aider** runs the tests but feeds the output back to the model to "read and
  fix" — it never gates on an independent exit-0. The model can keep saying it's
  fixed.
- **OpenHands** trusts the agent-server's self-reported event stream.
- **mini-swe-agent** is clever (magic-string + exit-code) but the REAL test
  verification is the external SWE-bench harness, not the agent.
- **loop-engineering** (the thesis leader) uses an AI maker/checker split — an AI
  checking an AI. rondo's wedge vs the thesis itself: **the checker is MECHANICAL**
  (rondo runs the test/hashes the file), not another model to be fooled.

So "the model is never allowed to grade its own observable work" is a genuine,
code-confirmed differentiator vs the popular tools.

**BUT the scriptable-verified-orchestration niche is contested**, and one finding
matters for the roadmap:
- **bernstein** — "deterministic scheduler for 40+ CLI coding agents in parallel
  git worktrees, **HMAC-signed audit chain**, per-artefact lineage, zero-LLM
  coordination loop." That is essentially rondo's REQ-117 (signed receipts)
  **already shipped**. rondo is not first to signed audit chains for agent loops.
- **Conductor (Microsoft)** — YAML-first multi-agent orchestration, Jinja2
  routing, "zero token overhead." rondo's closest YAML-orchestration competitor.
- **Hive (YC)** — objectives → deterministic DAGs, crash recovery, cost
  enforcement, human-in-the-loop.
- **Symphony (OpenAI)** — GitHub-native, proof-of-work artifacts as handoffs.
- **LangGraph** — entrenched in production, but NOT verification-focused.

## 4. Honest rating — how rondo would land if posted soon

**~7/10 for its niche.** Genuinely ahead on: verification-the-model-can't-grade
(vs aider/OpenHands/mini-swe), cross-vendor jury, the mutation-tested anti-lying
core (nobody else mutation-tests their lie-catcher), and the accessibility design
spec. Behind on: maturity/adoption (aider 33k★, mini-swe in prod at Meta/NVIDIA),
sandboxing (OpenHands), assertion richness (promptfoo's 70+), signed audit chain
(bernstein already has it), context compaction + multi-session memory +
observability dashboards (the awesome-harness catalog treats these as solved).

**Defensible wedge (lead with this, not "another agent loop"):** the scripted
loop where *the model is structurally prevented from lying about whether it did
the work*, with a *cross-vendor jury* and a *mutation-proven* lie-catcher, aimed
at the **individual developer driving Claude Code live** — not enterprise
orchestration (Conductor/Hive) and not pure compliance (bernstein).

## 5. Ideas to steal — prioritized, grounded

| # | Idea | From | Rondo target | Value |
|---|------|------|--------------|-------|
| 1 | Richer verify assertions: `assert-set` (all/any), transform-before-assert, regex, json-schema, `not-` inverse, optional llm-rubric | promptfoo `src/types/index.ts:608-662` | REQ-115 v0.3 | HIGH — on-brand, cheap, closes the assertion gap |
| 2 | Per-sandbox random session keys + Docker/container isolation, key on host | OpenHands `docker_sandbox_service.py:413` | REQ-117 sandbox (Apple container) | HIGH — unblocks the signed-receipts guarantee |
| 3 | Git auto-commit per step (checkpoint/rollback) | aider `base_coder.py` | conductor / pipeline | MED — real UX + safety |
| 4 | Stateless subprocess isolation per check | mini-swe `local.py:72-92` | verify cmd execution | MED |
| 5 | "Loop readiness score" CLI | loop-engineering `loop-audit` | a `rondo doctor`-style loop-readiness score | MED — great launch hook |
| 6 | Vocabulary: "loop engineering", "maker/checker", "the building blocks", "human gate" | loop-engineering | README / GOLDEN-FIVE messaging | MED — adopt the market's language |
| 7 | Magic-string completion protocol (explicit submit signal) | mini-swe `local.py:48` | inline control / advisory | LOW-MED |

## 6. Deep-report plan (Cursor 6/15) + interim panel

**Staged for Cursor (quota resets 6/15)** — a focused brief so it runs fast:
- INPUT A: rondo's `src/rondo/{pipeline,verify,scope}.py` + the flagships.
- INPUT B: `reference/loop-repos/{mini-swe-agent,aider,promptfoo}` core files.
- ASK: code-to-code on the verification path (rondo verify vs aider auto-test vs
  promptfoo assertions); doc-to-doc (rondo specs vs loop-engineering patterns);
  what's missing, what to clean up, where rondo is genuinely better. Use
  `cursor-review` from the repo root.

**Interim (available now):** a cross-vendor panel via `rondo_multi_review` /
`rondo_review_codebase` to pressure-test §3-§5 before Cursor — dogfooding.

## 7. Bottom line

The loop is table stakes (Conductor/Hive/LangGraph/aider/OpenHands all loop).
rondo's rare, code-confirmed edge is **"the model can't grade its own work, a
different vendor double-checks, and the lie-catcher itself is mutation-proven."**
The niche is contested (bernstein already shipped signed audit chains), so the
launch must lead with the verification+honesty wedge for the individual Claude
Code developer — and the highest-leverage build items are promptfoo-grade verify
assertions (#1) and the sandbox that makes signed receipts real (#2).
