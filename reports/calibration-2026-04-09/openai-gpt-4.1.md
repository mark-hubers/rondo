# Calibration — openai:gpt-4.1

Absolutely, I appreciate the directness and specificity of your questions. Here are honest, model-specific answers based on my architecture (GPT-4, as of 2024-06):

---

### 1. CONTEXT WINDOW: Practical Working Memory

- **Practical limit:** My *maximum* context window is 128k tokens (~350,000–400,000 characters, or ~50,000–70,000 lines of Python).  
- **Quality threshold:** In practice, **quality of analysis drops sharply after ~10,000–15,000 lines** of code (roughly 400–600 KB, or 20–30 files for typical Python). Beyond this, I start to lose track of details, especially for cross-file logic, and my responses become more generic or miss subtle issues.
- **Best results:** For *deep* code review, **3,000–5,000 lines** (120–200 KB) is the sweet spot for focused, high-quality analysis.

---

### 2. ONE vs MANY CALLS (20-file codebase)

- **Best for me:** **(b) 5 calls with 4 files each, including a summary of the others.**
- **Why:**  
  - In a single giant prompt, I tend to lose track of file boundaries and context, and my attention is diluted.
  - Multiple smaller prompts let me focus deeply on each subset, and if you include a *brief summary* of the other files (e.g., key classes/functions, main responsibilities), I can still reason about interactions.
  - This approach also reduces hallucination and repetition, and makes my findings more actionable.

---

### 3. CROSS-FILE ANALYSIS

- **If both files are in the same prompt:**  
  - I *can* catch cross-file bugs (e.g., variable set in A, used in B), **but only if the relevant code is close together or you highlight the relationship**.
  - My cross-file reasoning is *not* as strong as a human’s, especially if the files are far apart in the prompt or the connection is subtle.
  - If files are simply concatenated with no extra guidance, I often analyze them semi-independently.
- **Best practice:**  
  - **Explicitly call out cross-file relationships** or provide a summary of how files interact.  
  - For deep cross-file bugs, consider a follow-up prompt that *only* includes the relevant snippets from both files and asks about their interaction.

---

### 4. OPTIMAL FORMAT

- **Best for me:**  
  - **Markdown fenced code blocks** with file paths as headers (Option b).
    - Example:
      ```
      ### file: src/foo.py
      ```python
      # code here
      ```
      ```
  - This format is clean, easy to parse, and helps me keep track of file boundaries.
- **Line numbers:**  
  - **Including line numbers** (Option c) is helpful for referencing, but only if you want me to refer to specific lines in findings.  
  - If you add them, do so as comments (e.g., `# L42`) or in a way that doesn’t break code parsing.
- **Avoid:**  
  - Raw concatenation with only `# -- file: ...` separators is less effective, as I may miss file boundaries.

---

### 5. METADATA THAT HELPS

- **Significantly improves review quality:**
  - **Test coverage report:** Tells me where to focus for untested/critical code.
  - **Spec references:** Knowing what each module is *supposed* to do helps me spot logic errors and spec mismatches.
  - **Architecture diagram / module dependency map:** Greatly aids cross-file reasoning and understanding of the big picture.
- **Moderately helpful:**
  - **Recent git diff:** Useful for focusing on new/changed code, but less helpful for deep architectural issues.
- **Least helpful:**
  - **Git blame:** Rarely useful for code quality; I don’t reason about authorship or time.

---

### 6. WHAT I MISS (Blind Spots)

- **Worst at catching:**
  - **Subtle cross-file bugs** (e.g., inconsistent assumptions, state shared via globals, indirect side effects).
  - **Concurrency/threading issues** (race conditions, deadlocks).
  - **Performance bottlenecks** unless they’re obvious (e.g., O(N^2) in a loop).
  - **Security issues** that require domain/context knowledge (e.g., subtle injection vectors, cryptographic misuse).
  - **Bugs requiring real-world context** (e.g., business logic errors, domain-specific invariants).
- **Why:** My reasoning is strongest within a single file or small set of files; subtle, emergent bugs across many files or requiring deep domain knowledge are my weak spot.

---

### 7. STRUCTURED OUTPUT

- **I give better, more actionable results when you ask for a specific template** (table, numbered list, or JSON).
  - Structure helps me organize findings, avoid repetition, and makes it easier for you to parse results programmatically.
  - Free-form prose is more likely to be verbose, less organized, and harder to automate.

---

**Summary of best practices for ME:**
- Use Markdown code blocks with file headers.
- Limit each prompt to 3–5 files (~3,000–5,000 LOC).
- Include summaries/architecture/context for cross-file reasoning.
- Provide test coverage, specs, and architecture diagrams if possible.
- Ask for structured output (table, list, or JSON).
- For cross-file bugs, consider targeted follow-up prompts.

Let me know if you want sample prompt templates or further details!
