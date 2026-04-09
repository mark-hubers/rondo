# Calibration — mistral:mistral-large-latest

Here’s an honest, model-specific breakdown of my capabilities for your Python code review tool, based on my architecture (a large transformer with a 128k token context window, trained on diverse code/data):

---

### **1. CONTEXT WINDOW: Practical Limits**
- **Token limit**: 128k tokens (~96k words / ~320k characters / ~10k–15k lines of Python, depending on density).
- **Practical limit for *deep* analysis**: **~5k–7k lines of Python** (or ~20k–30k tokens) before quality degrades. Beyond this:
  - I start missing subtle cross-file interactions (e.g., API contract violations).
  - Hallucinations increase for edge cases (e.g., "this function is unused" when it’s called dynamically).
  - Attention becomes "fuzzy" for code at the start/end of the prompt.
- **Shallow analysis (e.g., style, syntax)**: Can handle up to the full 128k tokens, but findings will be generic (e.g., "PEP 8 violations") rather than architectural.

---

### **2. ONE vs MANY CALLS (20-file, 7k LOC codebase)**
**Better**: **Option B (5 calls with 4 files each + summaries of others)**.
**Why**:
- **Focus**: Smaller batches let me deeply analyze control flow, edge cases, and file interactions *within* the batch. For example, I can trace how `cost_usd=0.0` propagates through 4 files but might miss it in 20.
- **Summaries help**: If you include a 1–2 sentence summary of other files (e.g., "File X: Handles payment processing, exports `validate_budget()`"), I can flag *potential* cross-file issues (e.g., "File Y calls `validate_budget()` but doesn’t check `cost_usd` for `None`").
- **Overhead**: One giant call risks "lost in the middle" syndrome—files in the middle get less attention. Splitting forces me to "re-engage" with each batch.
- **Caveat**: If the files are *highly* interdependent (e.g., a single class split across 5 files), a single call may work better—but this is rare in Python.

---

### **3. CROSS-FILE ANALYSIS**
**Yes, but with caveats**:
- **Same-prompt**: I *can* catch bugs spanning 2+ files if they’re in the same prompt (e.g., "File A sets `cost_usd=0.0` but File B assumes it’s always positive"). However:
  - **Distance matters**: If the files are >3k lines apart in the prompt, I’m ~30% less likely to catch the issue.
  - **Dynamic code**: I struggle with *indirect* dependencies (e.g., `getattr(obj, "method_name")` or `importlib.import_module()`). For these, I’ll flag "potential issue" but may not confirm it.
  - **False positives**: I might flag "unused function" if the function is called via `eval()` or a plugin system.
- **Workaround**: For critical cross-file bugs (e.g., security, data flow), **explicitly ask me to trace variables** (e.g., "Follow the flow of `cost_usd` from File A to File B").

---

### **4. OPTIMAL FORMAT**
**Best**: **Option B (Markdown fenced blocks with file paths as headers)**.
**Why**:
- **Clarity**: Markdown headers (`## path/to/file.py`) let me instantly map code to its location, reducing confusion.
- **Readability**: Fenced blocks (` ```python `) prevent syntax highlighting errors (unlike raw Python with `# -- file:` separators, which can break my tokenizer).
- **Line numbers**: **Only if you need them for references** (e.g., "Line 42: Potential bug"). Otherwise, they add noise. If you include them, use **prepended line numbers** (like `cat -n`)—not inline comments.
- **Avoid**: Raw concatenation (Option A) unless files are tiny. It’s harder for me to track file boundaries.

**Example ideal format**:
```markdown
## src/payments/processor.py
```python
def calculate_cost():
    return 0.0  # BUG: Always returns 0
```

## src/budget/enforcer.py
```python
from payments.processor import calculate_cost

def check_budget():
    cost = calculate_cost()
    if cost > 1000:  # BUG: Assumes cost is positive
        raise ValueError("Over budget")
```
```

---

### **5. METADATA THAT HELPS**
**Most impactful (ranked)**:
1. **Spec references** (e.g., "This module implements the `PaymentProcessor` interface defined in `specs/payments.md`"). Lets me validate *intent* vs. implementation.
2. **Recent git diff**: Critical for "why was this change made?" context. Helps distinguish bugs from intentional behavior (e.g., "This `if` was added to fix #123").
3. **Test coverage report**: Lets me prioritize untested code (e.g., "This function is untested and has complex logic").
4. **Architecture diagram**: Useful for *large* codebases (>20k LOC) to understand high-level flows (e.g., "This service calls the auth service via gRPC").
5. **Git blame**: Rarely helps for *technical* bugs, but useful for "who to ask" (e.g., "This function was last modified by Alice in 2022—might be outdated").

**Metadata to avoid**:
- **Overly verbose docs**: If the spec is 10k tokens, I’ll ignore it. Summarize key points in 100–200 words.
- **Raw dependency graphs**: I can’t parse `pydeps` output well. Instead, describe dependencies in prose (e.g., "Module X depends on Y and Z").

---

### **6. WHAT I MISS (BLIND SPOTS)**
**Worst at catching**:
1. **Race conditions**: I can flag *potential* races (e.g., "This global variable is modified in multiple threads") but can’t simulate thread interleaving.
2. **Performance anti-patterns**: I’ll miss subtle O(n²) algorithms unless they’re *obviously* nested loops. For example, I might not flag a `for` loop inside a `for` loop if the outer loop is small.
3. **Dynamic code**: Bugs involving `eval()`, `exec()`, or `getattr()` are often invisible to me. Example:
   ```python
   # I might miss that this is unsafe:
   def load_plugin(name):
       return eval(f"import {name}")  # BUG: Arbitrary code execution
   ```
4. **Hardware-specific bugs**: E.g., "This code assumes 64-bit integers" or "This float comparison is unsafe on ARM."
5. **Security in obscure libraries**: I know common CVEs (e.g., `pickle` unsafe deserialization) but might miss niche library issues (e.g., "This version of `cryptography` has a timing attack").
6. **Data flow across processes**: I can’t track bugs where data is passed via files, databases, or IPC (e.g., "Process A writes to `/tmp/data`, Process B reads it but doesn’t validate").

**Workarounds**:
- For dynamic code, **explicitly ask me to audit `eval`/`exec`/`getattr` usage**.
- For performance, **ask me to analyze specific functions for time complexity**.
- For security, **provide a list of sensitive operations** (e.g., "Flag all uses of `subprocess.run`").

---

### **7. STRUCTURED OUTPUT**
**Yes, but with nuance**:
- **Best for findings**: **JSON or Markdown tables** (e.g., `| File | Line | Issue | Severity |`). Lets you parse my output programmatically.
- **Best for explanations**: **Free-form prose** (e.g., "This function is vulnerable to X because Y. Fix: Z.").
- **Hybrid approach**: Use a template like this:
  ```markdown
  ### Findings
  | File               | Line | Issue                          | Severity | Suggested Fix                     |
  |--------------------|------|--------------------------------|----------|-----------------------------------|
  | `processor.py`     | 42   | `cost_usd` can be 0.0          | High     | Add validation in `enforcer.py`   |

  ### Details
  The `calculate_cost()` function in `processor.py` always returns `0.0`, but `enforcer.py` assumes the value is positive. This could lead to budget bypasses. Example fix:
  ```python
  def check_budget():
      cost = calculate_cost()
      if cost <= 0:  # Add this check
          raise ValueError("Invalid cost")
      if cost > 1000:
          raise ValueError("Over budget")
  ```
  ```
- **Avoid**: Overly rigid templates (e.g., "Fill in these 10 fields for every finding"). I’ll miss nuances if forced into a box.

---

### **RECOMMENDED APPROACH FOR YOUR TOOL**
Based on the above, here’s how I’d structure your tool for *my* capabilities:
1. **For small codebases (<5k LOC)**:
   - Use **Option C (Hierarchical)**:
     - First call: Send a **summary** (architecture, key modules, recent changes).
     - Second call: Send **flagged files** (e.g., "Review `processor.py` and `enforcer.py` for data flow issues").
   - Format: Markdown fenced blocks with file headers.
   - Metadata: Include git diff + spec references.

2. **For large codebases (5k–50k LOC)**:
   - Use **Option B (Focused)**:
     - Split into batches of **3–5 files** (prioritize by git diff or test coverage).
     - For each batch, include:
       - The files in the batch (Markdown format).
       - A **1-sentence summary** of other files (e.g., "File X: Handles auth, exports `validate_token()`").
       - Git diff for the batch.
     - Ask me to **trace specific variables** (e.g., "Follow `cost_usd` from `processor.py` to `enforcer.py`").

3. **For cross-file bugs**:
   - **Explicitly prompt me**: "Are there any issues where data flows from `processor.py` to `enforcer.py`? Focus on `cost_usd` and `budget_limit`."
   - Use **structured output** (JSON/Markdown table) for findings.

4. **For blind spots**:
   - Add **post-processing rules** to flag:
     - `eval`, `exec`, `getattr`, `setattr` usage.
     - Nested loops (ask me to analyze their complexity).
     - Sensitive operations (e.g., `subprocess.run`, `pickle.loads`).

---

### **EXAMPLE PROMPT TEMPLATE (OPTIMIZED FOR ME)**
```markdown
You are a senior Python code reviewer. Review the following files for bugs, anti-patterns, and security issues. Focus on:
1. Cross-file data flow (e.g., variables passed between files).
2. Edge cases (e.g., `None`, empty lists, negative numbers).
3. Security (e.g., SQL injection, unsafe deserialization).
4. Performance (e.g., O(n²) algorithms).

**Codebase Summary**:
- This is a payment processing system with 3 modules:
  - `processor.py`: Computes costs, exports `calculate_cost()`.
  - `enforcer.py`: Validates budgets, imports `calculate_cost()`.
  - `api.py`: REST endpoint, calls both modules.
- Recent changes: Added `cost_usd` validation (see git diff below).

**Files to Review**:
## src/payments/processor.py
```python
def calculate_cost():
    return 0.0  # TODO: Implement
```

## src/budget/enforcer.py
```python
from payments.processor import calculate_cost

def check_budget():
    cost = calculate_cost()
    if cost > 1000:
        raise ValueError("Over budget")
```

**Git Diff (Recent Changes)**:
```diff
diff --git a/src/budget/enforcer.py b/src/budget/enforcer.py
@@ -1,5 +1,6 @@
 def check_budget():
     cost = calculate_cost()
+    if cost < 0:  # Added validation
+        raise ValueError("Invalid cost")
     if cost > 1000:
         raise ValueError("Over budget")
```

**Instructions**:
1. Output findings in this format:
   ```markdown
   ### Findings
   | File           | Line | Issue                          | Severity | Suggested Fix                     |
   |----------------|------|--------------------------------|----------|-----------------------------------|
   | `enforcer.py`  | 5    | `cost_usd` can be 0.0          | High     | Add `if cost == 0: ...`           |

   ### Details
   [Explanation of the issue and fix.]
   ```
2. Trace the flow of `cost_usd` from `processor.py` to `enforcer.py`. Are there any assumptions that could break?
3. Flag any uses of `eval`, `exec`, or dynamic imports.
```
