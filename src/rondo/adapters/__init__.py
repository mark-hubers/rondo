# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo provider adapters — REQ-109 req 030.

Each adapter handles one API pattern:
- ollama.py: Local LLM via Ollama HTTP API
- chat_completions.py: OpenAI + Grok + Mistral (same API shape)
- gemini.py: Google Gemini generateContent API
- anthropic_api.py: Anthropic Messages API

Import adapters directly: from rondo.adapters.ollama import OllamaAdapter
"""

# -- No top-level imports to avoid circular dependency with providers.py

# -- sig: mgh-6201.cd.bd955f.a109.d03001
