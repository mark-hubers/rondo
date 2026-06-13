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

## 7.5 Cross-vendor reality check — it knocked us down (Gemini + Grok, 2026-06-13)

An interim hostile panel (rondo_multi_review, both vendors) was asked to find
where THIS report overrates rondo. They converged hard. Recorded honestly, NOT
softened — the §4 self-rating was too generous:

- **"Ahead on verification" is overstated.** aider/OpenHands run real tests too;
  mechanical test-running is TABLE STAKES, not a moat. aider feeding output back
  to the model is a feature (that's how it fixes code), not a flaw. rondo's true
  distinction is narrower: it gates the LOOP on the independent result rather than
  trusting the model to iterate — real, but not a categorical "ahead."
- **The "individual dev + Claude Code" wedge is absorbable.** Both: Anthropic /
  Cursor / Copilot Workspace ship native verified loops within months; rondo
  risks being "a temporary polyfill for a missing feature in a beta product."
- **Missed competitors: Cline + Roo Code** — high-traction VS Code agent-loops
  with verification. A real gap in the scan (add to reference next refresh).
- **Mutation-tested core = launch theater.** Internal QA metric, not a user value
  prop; "zero users adopt on that." (It's why the tool is trustworthy — but it's
  not a headline.)
- **bernstein/Hive underweighted**, and **no proof**: "publish real failure cases
  where aider/OpenHands accepted a bad patch that rondo rejected" (Grok). Claims
  without that proof read as every-other-wrapper.
- **Realistic external rating: 3-4/10 as positioned** (not 7). Reaches 7 ONLY via
  the pivot below + published proof + a benchmark vs bernstein on audit integrity.

**THE PIVOT both vendors independently prescribed — the actual moat:**
> Lead with the **CROSS-VENDOR JURY**: Claude writes, Gemini/Grok *independently*
> judge, and disagreements are surfaced. Anthropic/Cursor/Copilot **structurally
> will not build this** — they're single-vendor and won't critique their own
> model with a competitor's. That is the one thing they can't absorb.

Action items from this check (supersede §4's framing):
1. Reframe the launch thesis around the cross-vendor adversarial jury, not
   "anti-lying" or "control Claude live." (controlled_review_loop.py is already
   the seed — make it THE flagship.)
2. Surface jury DISAGREEMENTS as the product's visible value (not a hidden gate).
3. Publish concrete proof: a case where a single-vendor loop accepts a bad patch
   and rondo's cross-vendor jury catches it.
4. Add Cline + Roo Code to the next reference refresh + benchmark.
5. Keep mutation-testing/anti-lying as a TRUST credential, not the headline.

## 7. Bottom line (revised after the §7.5 cross-vendor reality check)

The loop is table stakes; "independent verification" is table stakes too
(aider/OpenHands run tests). Mutation-testing is a trust credential, not a
headline. The niche is contested (bernstein shipped signed audit chains;
Conductor/Hive/Cline/Roo Code are all here).

**The one thing rivals structurally cannot copy — and therefore the launch
thesis — is the CROSS-VENDOR ADVERSARIAL JURY:** Claude writes, a *different
vendor* (Gemini/Grok) independently judges, disagreements surfaced. Anthropic,
Cursor, and Copilot are single-vendor and won't critique their own model with a
competitor's. `controlled_review_loop.py` is already the seed of this.

Honest standing: **3-4/10 as positioned today, ~7/10 if rondo reframes around the
cross-vendor jury + publishes proof** (a real case where a single-vendor loop
accepts a bad patch and the jury catches it). Highest-leverage next moves:
(1) make the cross-vendor jury THE flagship + surface disagreements; (2) publish
the proof case; (3) promptfoo-grade verify assertions; (4) add Cline/Roo Code to
the benchmark. Deep Cursor code/doc/spec comparison still queued for 6/15 (§6).
