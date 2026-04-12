# rondo-meta: mode=subprocess provider=anthropic category=observability value="Provider scoring and comparison from run outputs"

"""Rondo API: Provider Scoring.

Computes quality scores per provider from dispatch history.
Score = success_rate * 0.5 + cost_efficiency * 0.3 + speed * 0.2
"""

import json
import tempfile
import time
from pathlib import Path

from rondo.scoring import compute_provider_scores, load_scores_cache, save_scores_cache


def main() -> None:
    """Compute and cache provider scores from mock audit data."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "audit.jsonl"
        records = []
        for i in range(20):
            records.append(
                json.dumps(
                    {
                        "model": "gemini:flash",
                        "status": "done" if i < 18 else "error",
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "cost_usd": 0.003,
                        "duration_sec": 2.1,
                        "json_valid": i < 17,
                        "fields_complete": i < 15,
                    }
                )
            )
        jsonl.write_text("\n".join(records))

        scores = compute_provider_scores(tmp)
        for name, s in scores.items():
            print(f"{name}: score={s['score']:.3f} success={s['success_rate']:.0%}")

        cache_dir = Path(tmp) / "cache"
        save_scores_cache(scores, str(cache_dir))
        loaded = load_scores_cache(str(cache_dir))
        print(f"Cached {len(loaded)} providers")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e004.a10400
