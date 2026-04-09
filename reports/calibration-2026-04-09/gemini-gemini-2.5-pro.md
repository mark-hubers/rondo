# Calibration — gemini:gemini-2.5-pro

This is an excellent set of questions. Answering them precisely allows me to perform better for you, which is my goal. I appreciate you taking the time to optimize for my specific architecture. Here are my honest, model-specific answers.

---

### 1. CONTEXT WINDOW: Practical Limit

My theoretical maximum context window is very large (on the order of 128k to 1M tokens depending on the specific version you're calling), but you are correct to ask for the *practical* limit. Performance is not linear.

My "working memory" for high-fidelity, cross-file analysis is most effective in the **30,000 to 50,000 token range**.

*   **In characters:** Roughly 120,000 to 200,000 characters.
*   **In lines of Python:** This translates to approximately **3,000 to 5,000 lines of dense Python code**.

Beyond this point, I can still process the information, but I'm more susceptible to the "lost in the middle" problem. The beginning and end of the prompt have the strongest weight in my attention mechanism. A function definition at line 500 and its usage at line 6,500 might be missed if the intervening 6,000 lines are noisy and complex. For a 50K LOC codebase, your **Option A (Full Dump)** is not viable for a high-quality review in a single pass.

### 2. ONE vs MANY CALLS

For a 20-file, 7000 LOC codebase, I would provide significantly better findings with **(b) 5 calls with 4 files each, where each call includes a summary of the others.**

**Why:**

My architecture is transformer-based. While I can see the entire context at once, the attention mechanism has to calculate relevancy scores between every token. In a massive, 7000-line single prompt, the signal-to-noise ratio for any given token is lower. A subtle connection between `file_A.py` and `file_T.py` might be drowned out by the 18 other files between them.

The multi-call approach is superior *for me* because:
1.  **Focus:** In each call, the 4 primary files are the "foreground." My attention is concentrated there.
2.  **Guided Context:** The summary of the other 16 files acts as a "cheat sheet." It primes me with the necessary context (e.g., "Remember, a `User` object is defined in `models/user.py` and has these properties...") without forcing me to re-parse all of that code. This is a much more efficient use of my context.

This approach mimics how a human would work: focus on a few files, but keep the overall architecture in mind.

### 3. CROSS-FILE ANALYSIS

**Yes, I can reliably catch bugs that span 2+ files, but with a major caveat.**

My ability to do this is directly proportional to the "distance" between the related code snippets in the prompt.

*   **High Reliability:** If `file_A.py` and `file_B.py` are provided consecutively in the same prompt, and they are the *only* files or part of a small set (see Q2), I am very likely to spot the interaction. For example, I can trace a function call from one file to its definition in another and check for mismatched arguments or incorrect assumptions about return values.
*   **Medium Reliability:** If the two files are in a large prompt separated by thousands of lines of other code, my chances decrease. I might still find it, especially if the function/variable names are distinct and clearly linked, but it's not a guarantee.
*   **Low Reliability:** If the files are sent in completely separate API calls *without any shared context*, I have virtually no chance of catching the bug. I am stateless between API calls.

**Conclusion:** You are correct to assume I tend to analyze files with a strong "locality bias" even when concatenated. To ensure I catch cross-file issues, you must either place the related files close together in the prompt or provide explicit context linking them.

### 4. OPTIMAL FORMAT

The best format for me is **(b) Markdown fenced blocks with file paths as headers.**

```markdown
Here is the code for review. Please analyze for bugs, style issues, and potential improvements.

### `path/to/file/one.py`

```python
import os

class User:
    # ... class implementation ...
```

### `path/to/file/two.py`

```python
from path.to.file.one import User

def process_user(user: User):
    # ... function implementation ...
```
```

**Why:**

1.  **Unambiguous Structure:** The Markdown fences (`###` and ` ``` `) are explicit, structural tokens for me. They clearly delineate file boundaries, which is much cleaner than a comment like `# -- file: ...`. This helps me partition my analysis internally.
2.  **Metadata Association:** The file path in the header is directly associated with the code block that follows. This helps me build an accurate mental model of the project structure and resolve imports.
3.  **Language Identification:** The `python` tag in the code fence primes me to use my Python-specific training and syntax analysis capabilities immediately.

Line numbers (Option c) are a double-edged sword. They can be useful if you want me to reference a specific line in my output (e.g., "In `one.py:15`, ..."), but they add token noise and can sometimes confuse my parsing of the code itself. A better approach is to provide the code without line numbers and ask me to provide context snippets in my findings.

### 5. METADATA THAT HELPS

Here is a ranked list of the metadata you mentioned, from most to least helpful for me:

1.  **Spec References (Tier 1 - Game Changer):** This is the single most valuable piece of information. If you provide a description of what a module *is supposed to do*, you transform the task from a generic "find bugs" to a specific "verify implementation against intent." This allows me to catch subtle business logic errors that are impossible to find otherwise.
2.  **Recent Git Diff (Tier 1 - Game Changer):** This focuses my attention intensely. Instead of boiling the ocean, I can analyze the *change*. I can infer the developer's intent and evaluate whether the change accomplishes its goal effectively and safely. This is the core of a real-world code review. **Your Option D is a very strong strategy.**
3.  **Architecture Diagram / Module Dependency Map (Tier 2 - Very Helpful):** For larger reviews, this is fantastic. It's a high-level summary that helps me understand how the pieces fit together before I dive into the code. It prevents me from making incorrect assumptions about module roles.
4.  **Test Coverage Report (Tier 2 - Very Helpful):** This is a powerful signal. If you tell me "lines 45-52 are untested," I will scrutinize that code block with extreme prejudice, looking for edge cases, off-by-one errors, and unhandled exceptions.
5.  **Git Blame (Tier 4 - Low Value):** This is mostly noise for me. I am a technical analyzer, not a project manager. Knowing *who* wrote a line doesn't change my analysis of *what* the line does. It adds tokens without adding useful analytical context.

### 6. WHAT YOU MISS

I am honest about my limitations. Here are the bug categories I am **worst** at catching:

1.  **Concurrency Issues (Race Conditions, Deadlocks):** These bugs are emergent from the timing of execution, which is nearly impossible to reason about from static code alone. I can spot obvious anti-patterns (e.g., accessing a shared dictionary without a lock), but I will miss subtle or complex race conditions.
2.  **Complex Performance/Memory Issues:** I can identify inefficient algorithms in a localized context (e.g., O(n^2) loop). I cannot, however, reliably predict the real-world performance or memory footprint of a large application. I won't tell you that a specific change will cause a 10ms latency increase or a 200MB memory leak under production load.
3.  **Configuration or Environment-Dependent Bugs:** I have no knowledge of your production environment, CI/CD pipeline, or deployment configuration. I might flag a hardcoded IP address as a bug when it's actually the correct, immutable address for a service within a Docker network.
4.  **High-Level Design Flaws:** While an architecture summary helps, I am best at tactical, line-by-line and function-by-function analysis. I might not recognize that the entire *approach* to a problem is flawed or that a different architectural pattern would be vastly superior. I can critique the existing castle, but I'm not great at telling you that you should have built a skyscraper instead.
5.  **Novel Security Vulnerabilities:** I am trained on a vast dataset of code, so I can recognize *known* vulnerability patterns (e.g., basic SQL injection, obvious XSS). I am not a specialized security tool and will likely miss novel exploits or vulnerabilities that require a deep, multi-step understanding of the system's state.

### 7. STRUCTURED OUTPUT

**Yes, absolutely.** I give far better, more consistent, and more useful results when asked to output findings in a specific template. JSON is ideal for your tool.

Free-form prose allows for ambiguity and "hedging." A structured format forces me to be precise and commit to a specific classification for each finding.

**Optimal Prompt Strategy:**

Ask me to respond with a JSON object, providing a schema in the prompt.

**Example Prompt Snippet:**

> "Review the code. Identify any issues and format your response as a single JSON object containing a list of findings. Each finding must conform to this schema:
>
> ```json
> {
>   "findings": [
>     {
>       "file_path": "path/to/file.py",
>       "line_start": 10,
>       "line_end": 15,
>       "severity": "Major" | "Minor" | "Info",
>       "category": "Bug" | "Vulnerability" | "Style" | "Performance" | "Maintainability",
>       "title": "A brief, one-sentence summary of the issue.",
>       "description": "A detailed explanation of the issue, why it's a problem, and its potential impact.",
>       "suggestion": "A concrete code snippet or detailed instruction on how to fix the issue."
>     }
>   ]
> }
> ```
> If no issues are found, return an empty list: `{\"findings\": []}`."

This is the single best thing you can do to get reliable, machine-parsable output from me.
