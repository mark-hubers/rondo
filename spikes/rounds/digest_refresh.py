#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Digest Refresh Round — keep spec digests current.

Reads current spec → reads current digest → checks for staleness →
regenerates if needed. Designed for overnight batch across all specs.

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

from rondo.engine import Gate, Round, Task


def _check_spec_exists(**kwargs: object) -> tuple[bool, str]:
   """Verify spec file exists."""
   from pathlib import Path
   spec_path = str(kwargs.get("spec_path", ""))
   if not spec_path:
      return False, "No spec_path provided"
   return Path(spec_path).exists(), f"{'Found' if Path(spec_path).exists() else 'MISSING'}: {spec_path}"


def build_digest_round(spec_id: str, spec_path: str) -> Round:
   """Build a digest refresh round for any spec.

   Args:
      spec_id: Spec identifier (e.g., "OB-REQ-001", "R027")
      spec_path: Path to the spec markdown file
   """
   ## -- Guess digest path from spec
   from pathlib import Path
   spec_name = Path(spec_path).stem
   ## -- R27-tiered-ai-processing → R27-digest.md
   ## -- OB-REQ-001-orbital-database → OB-REQ-001-digest.md
   parts = spec_name.split("-")
   if parts[0].startswith("OB"):
      digest_name = f"{parts[0]}-{parts[1]}-digest.md"
   else:
      digest_name = f"{parts[0]}-digest.md"
   digest_path = str(Path(spec_path).parent.parent / "digests" / digest_name)

   return Round(
      name="digest-refresh",
      round_num=0,
      description=f"Digest refresh for {spec_id}",

      pre_gates=[
         Gate(
            name="Spec exists",
            description=f"{spec_id} spec file exists",
            check_fn=_check_spec_exists,
            blocking=True,
         ),
      ],

      tasks=[
         ## -- 1. Compare spec vs digest (sonnet — pattern matching)
         Task(
            name=f"{spec_id}: Staleness Check",
            description="Compare spec content to existing digest",
            instruction="Read the spec file and its digest. "
                        "Compare: does the digest accurately summarize the spec? "
                        "Flag any sections in the spec that are NOT reflected in the digest. "
                        "Flag any digest content that contradicts the spec.",
            context_files=[spec_path, digest_path],
            done_when="Staleness assessment: FRESH (digest matches), STALE (gaps found), or MISSING (no digest)",
            model="sonnet",
         ),

         ## -- 2. Generate refreshed digest (opus — needs good summarization)
         Task(
            name=f"{spec_id}: Generate Digest",
            description="Write a fresh digest from current spec",
            instruction="Read the full spec. Write a concise digest (max 50 lines) that captures: "
                        "1) What this spec is (1-2 sentences) "
                        "2) Key requirements (numbered list, max 10) "
                        "3) Architecture decisions (if any) "
                        "4) Dependencies and cross-references "
                        "5) Current status. "
                        "Format as markdown. This digest replaces reading the full spec.",
            context_files=[spec_path],
            done_when="Complete digest that captures spec essence in under 50 lines",
            model="opus",
         ),

         ## -- 3. Verify digest quality (sonnet — structured check)
         Task(
            name=f"{spec_id}: Digest Quality Check",
            description="Verify digest is complete and accurate",
            instruction="Read the spec and the digest you just generated. "
                        "Check: 1) Does digest mention ALL key requirements? "
                        "2) Are any important details lost? "
                        "3) Is the digest under 50 lines? "
                        "4) Could someone understand the spec from just the digest?",
            context_files=[spec_path, digest_path],
            done_when="Quality check: PASS (digest is sufficient) or FAIL (what's missing)",
            model="sonnet",
         ),
      ],

      post_gates=[
         Gate(
            name="Digest checked",
            description="All digest tasks complete",
            check_fn=lambda **_kw: (True, "Manual verification"),
         ),
      ],
   )
