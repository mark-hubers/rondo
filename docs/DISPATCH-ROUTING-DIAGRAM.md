# Rondo v0.7 Dispatch Routing

## How Every Model Gets Routed

```
YOU SAY                          MODEL PARAM              ENGINE         HOW IT RUNS
─────────────────────────────── ──────────────────────── ────────────── ──────────────────────────
"just run this"                  model=""                 INLINE         Current session, full context
"run this"                       model omitted            INLINE         Current session, full context

"run on sonnet"                  model="sonnet"
  in Claude Code session?
    yes ─────────────────────────────────────────────── AGENT          Agent(model="sonnet")
    no (CLI) ────────────────────────────────────────── SUBPROCESS     claude -p --bare

"run on opus"                    model="opus"
  in Claude Code session?
    yes ─────────────────────────────────────────────── AGENT          Agent(model="opus")
    no (CLI) ────────────────────────────────────────── SUBPROCESS     claude -p --bare

"run on haiku"                   model="haiku"
  in Claude Code session?
    yes ─────────────────────────────────────────────── AGENT          Agent(model="haiku")
    no (CLI) ────────────────────────────────────────── SUBPROCESS     claude -p --bare

"ask Gemini"                     model="gemini:high"      HTTP           GeminiAdapter API call
"ask Gemini flash"               model="gemini:gemini-flash-latest"     HTTP           GeminiAdapter API call
"ask Grok"                       model="grok:grok-4.3"      HTTP           ChatCompletionsAdapter
"ask OpenAI"                     model="openai:gpt-5.5"   HTTP           ChatCompletionsAdapter
"ask Mistral"                    model="mistral:large"     HTTP           ChatCompletionsAdapter
"use local qwen"                 model="local:qwen:32b"   HTTP           OllamaAdapter localhost

"use Anthropic API"              model="anthropic:sonnet"  HTTP           AnthropicAPIAdapter
                                                                         (API key, costs money)

"force new session"              model="sonnet:new"        SUBPROCESS    claude -p (fresh context)
"run in background"              background=True           SUBPROCESS    claude -p --bare (detached)
"overnight batch"                scheduled/cron            SUBPROCESS    claude -p --bare (no session)
```

## The Decision Tree

```
rondo_run(model=?, background=?, prompt=?)
    |
    |-- background=True?
    |       yes --> SUBPROCESS (always, any model)
    |
    |-- has provider prefix? (gemini: grok: openai: mistral: local: anthropic:)
    |       yes --> HTTP ADAPTER (direct API call)
    |
    |-- model empty or omitted?
    |       yes --> INLINE (current session executes it)
    |
    |-- model ends with :new?
    |       yes --> SUBPROCESS (force fresh session)
    |
    |-- model is Claude? (sonnet, opus, haiku, sonnet[1m], opus[1m])
    |       |
    |       |-- inside Claude Code session? (CLAUDECODE env var set)
    |       |       yes --> AGENT (host spawns Agent with model param)
    |       |       no  --> SUBPROCESS (CLI usage, subprocess OK)
    |       |
    |
    |-- else --> ERROR (unknown model)
```

## What Each Engine Returns

```
INLINE returns:
    { "engine": "inline",
      "kind": "inline_dispatch_plan",
      "prompt": "...",
      "done_when": "...",
      "model": "current" }
    --> Claude: execute this prompt yourself, right now

AGENT returns:
    { "engine": "agent",
      "kind": "agent_dispatch_plan",
      "prompt": "...",
      "done_when": "...",
      "model": "haiku" }
    --> Claude: spawn Agent(model="haiku", prompt="...")

HTTP returns:
    (actual dispatch happens, returns TaskResult with output)
    --> real API response from Gemini/Grok/OpenAI/etc.

SUBPROCESS returns:
    (actual dispatch happens via claude -p, returns TaskResult)
    --> only for background, overnight, CLI, or :new suffix
```

## When Subprocess Fails (and Why)

```
Inside Claude Code session + claude -p = ALWAYS FAILS
    Reason: nested session can't authenticate
    Error: "Not logged in - Please run /login"
    Audit data: 59/59 failures (100%)

That is why v0.7 routes in-session Claude models to AGENT instead.
AGENT uses Claude Code's built-in Agent tool = hooks, CLAUDE.md, Caliber all active.
```

## Cost Comparison

```
Engine          Billing               Cost
─────────────── ───────────────────── ────────────────────
INLINE          Max plan (included)   $0 extra
AGENT           Max plan (included)   $0 extra
HTTP gemini     Gemini API key        ~$0.01-0.10 per call
HTTP grok       Grok API key          ~$0.01-0.10 per call
HTTP anthropic  Anthropic API key     ~$0.01-0.50 per call
HTTP local      Ollama (free)         $0 (runs on Mac)
SUBPROCESS      Max plan or API key   $0 extra (if Max)
```
