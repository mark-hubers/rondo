# reference/ — local research data (mostly gitignored)

Local reference material for understanding rondo's competitive landscape. This
README is tracked; the bulky clones under `loop-repos/` are **gitignored**
(see `.gitignore`) — they are reference DATA, not part of rondo, and must never
be committed or treated as rondo source.

## `loop-repos/` — competitor / prior-art clones (gitignored)

Curated loop-engineering / agentic-coding / verification repos, cloned shallow
(`--depth 1`), `.git` stripped (we want the code to READ, not the history).
Kept locally so Claude and Cursor can read real code instead of blog summaries.

| Dir | What it is | Why it's here |
|-----|-----------|---------------|
| `mini-swe-agent` | ~100-line bash-first coding agent, >74% SWE-bench | the minimal verified loop — closest to rondo's lean conductor |
| `loop-engineering` | patterns/docs for "loop engineering" (Cherny/Osmani-inspired) + npm tools | the THESIS leader — vocabulary + the maker/checker pattern |
| `aider` | mature practical coding agent (git + tests, 33k★) | edit→test→fix loop; how a mature tool handles verification |
| `OpenHands` | full SWE agent, Docker-sandboxed runtime | sandboxing + event-driven loop (rondo's sandbox roadmap) |
| `promptfoo` | declarative YAML prompt/eval harness (70+ assertions) | assertion richness for rondo's verify (REQ-115) — kept src/ + docs/ |
| `live-swe-agent` | "self-evolving" SWE harness (config-tuned mini-swe-agent) | the self-evolve angle |
| `awesome-harness-engineering` | curated catalog of harness patterns + tools | the competitive map; surfaced Conductor / bernstein / Hive / Symphony |
| `cline` | high-traction VS Code agent extension (single-vendor, human-gated auto-approve) | added 2026-06-13 (self-audit flagged it missed); the crowded editor-agent niche |
| `Roo-Code` | VS Code agent extension; rich auto-approval (alwaysAllow*) | added 2026-06-13; human-gated single-vendor loop — kept src/+packages/ |

## Refresh

```
mkdir -p reference/loop-repos && cd reference/loop-repos
for url in \
  https://github.com/SWE-agent/mini-swe-agent \
  https://github.com/cobusgreyling/loop-engineering \
  https://github.com/ai-boost/awesome-harness-engineering \
  https://github.com/promptfoo/promptfoo \
  https://github.com/Aider-AI/aider \
  https://github.com/OpenAutoCoder/live-swe-agent \
  https://github.com/All-Hands-AI/OpenHands ; do
    git clone --depth 1 "$url" "$(basename "$url")" && rm -rf "$(basename "$url")/.git"
done
# promptfoo is large — keep only src/ + docs/ for reference
cd promptfoo && rm -rf site examples test drizzle node_modules dist
```

## The analysis built from these

See `reports/competitive/LANDSCAPE-2026-06-13.md` — the benchmark matrix, honest
rating, and the deep-report plan (Cursor 6/15 + interim rondo panel).
