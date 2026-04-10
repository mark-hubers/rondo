"""Rondo Scripted Prompting: Find → Fix → Verify Pipeline.

The core prompt-coding pattern: chain AI calls where each
step's output feeds the next step's input.

Step 1: Find bugs (returns structured issues list)
Step 2: For each bug, generate a fix
Step 3: Verify each fix works

This is WHY structured returns matter — you can't script
this with text blobs. You need {"issues": [...]} to loop.
"""

from rondo.smart_return import normalize_response


def dispatch_mock(prompt: str, step: str) -> dict:
    """Mock dispatch that returns different results per step."""
    if step == "find":
        return {
            "passed": False,
            "confidence": 0.95,
            "issues": ["SQL injection on line 42", "XSS on line 88", "Missing auth on /admin"],
            "result": "Found 3 security issues",
            "_meta": {"quality": 9, "complete": True, "limitations": ""},
        }
    if step == "fix":
        return {
            "passed": True,
            "confidence": 0.9,
            "result": f"Fixed: {prompt.split(': ', 1)[-1][:40]}",
            "issues": [],
            "_meta": {"quality": 8, "complete": True, "limitations": ""},
        }
    return {
        "passed": True,
        "confidence": 0.85,
        "result": "Fix verified",
        "issues": [],
        "_meta": {"quality": 7, "complete": True, "limitations": "Static analysis only"},
    }


def find_fix_verify(code_description: str) -> dict:
    """Three-step pipeline: find bugs, fix each one, verify fixes.

    This shows the power of structured returns:
    - Step 1 returns issues[] — Python loops through them
    - Step 2 returns result per fix — collected into a list
    - Step 3 verifies — any failure triggers human review
    """
    ## Step 1: Find bugs
    findings = normalize_response(dispatch_mock(code_description, "find"))
    print(f"  FIND: {len(findings['issues'])} issues found")

    if findings["passed"]:
        print("  No issues — code is clean")
        return {"status": "clean", "fixes": []}

    ## Step 2: Fix each issue
    fixes = []
    for issue in findings["issues"]:
        fix = normalize_response(dispatch_mock(f"Fix this: {issue}", "fix"))
        fixes.append({"issue": issue, "fix": fix["result"], "confidence": fix["confidence"]})
        print(f"  FIX: {issue[:30]}... → confidence={fix['confidence']}")

    ## Step 3: Verify each fix
    verified = []
    for fix_record in fixes:
        verify = normalize_response(dispatch_mock(f"Verify: {fix_record['fix']}", "verify"))
        fix_record["verified"] = verify["passed"]
        fix_record["verify_confidence"] = verify["confidence"]
        verified.append(fix_record)

        if not verify["passed"]:
            print(f"  VERIFY FAILED: {fix_record['issue'][:30]}... → needs human review")

    ## Summary
    all_verified = all(f["verified"] for f in verified)
    print(f"  RESULT: {len(verified)} fixes, all_verified={all_verified}")

    return {"status": "fixed" if all_verified else "needs_review", "fixes": verified}


def main() -> None:
    """Demonstrate the find-fix-verify pipeline."""
    print("=== Find → Fix → Verify Pipeline ===")
    result = find_fix_verify("Login handler with user input")
    print(f"Final status: {result['status']}")
    for fix in result["fixes"]:
        print(f"  {fix['issue'][:40]:40s} verified={fix['verified']}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea12.1ea4b2
