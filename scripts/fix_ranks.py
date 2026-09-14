#!/usr/bin/env python3
"""
Recompute member and state ranks from authoritative performance_score_100.

Rules:
  - Only rows with a non-null performance_score_100 are ranked.
  - national_rank: global descending rank across all ranked members.
  - peer_rank:     descending rank within member_type (MP / MLA).
  - national_percentile: (1 - national_rank / N) * 100, where N = total ranked.
  - peer_percentile:     (1 - peer_rank / N_type) * 100.
  - Ties: dense / standard competition ranking (same score → same rank;
    next distinct score gets the next integer rank).  This is deterministic.
  - state rank: global descending rank across all 36 states.

Also re-derives performance_label from performance_score_100 for any row
where the label does not match the authoritative score.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


def competition_rank(scores_desc):
    """Assign competition (1224) ranks to a list of scores already sorted DESC."""
    ranks = []
    current_rank = 1
    for i, s in enumerate(scores_desc):
        if i > 0 and s != scores_desc[i - 1]:
            current_rank = i + 1
        ranks.append(current_rank)
    return ranks


async def main():
    P("=" * 70)
    P("RANK RECONCILIATION")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")

    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)

    # ------------------------------------------------------------------
    # Backup current intelligence ranks
    # ------------------------------------------------------------------
    await db2.execute("""
        DROP TABLE IF EXISTS public.govsense_backup_member_intelligence_ranks;
        CREATE TABLE public.govsense_backup_member_intelligence_ranks AS
        SELECT member_id, member_type, national_rank, national_percentile, peer_rank, peer_percentile
        FROM public.member_intelligence;
    """)
    await db2.execute("""
        DROP TABLE IF EXISTS public.govsense_backup_state_intelligence_ranks;
        CREATE TABLE public.govsense_backup_state_intelligence_ranks AS
        SELECT state_id, rank, national_percentile
        FROM public.state_intelligence;
    """)
    P("Backups created.")

    # ------------------------------------------------------------------
    # Recompute member ranks
    # ------------------------------------------------------------------
    P("\n--- Recomputing member ranks ---")
    rows = await db2.fetch("""
        SELECT member_id, member_type, performance_score_100
        FROM public.member_intelligence
        WHERE performance_score_100 IS NOT NULL
        ORDER BY performance_score_100 DESC, member_id ASC
    """)
    P(f"Ranking-qualified members: {len(rows)}")

    # Global national ranks
    scores = [r["performance_score_100"] for r in rows]
    national_ranks = competition_rank(scores)
    total = len(rows)

    # Derive authoritative label from score
    def label_from_score(score):
        if score is None:
            return None
        if score >= 85:
            return "EXCEPTIONAL"
        if score >= 70:
            return "PERFORMER"
        if score >= 50:
            return "STABLE"
        if score >= 35:
            return "NEEDS_ATTENTION"
        return "UNDERPERFORMER"

    # Build lookup including score and derived label
    member_lookup = {}
    for r, nr in zip(rows, national_ranks):
        score = r["performance_score_100"]
        member_lookup[(r["member_id"], r["member_type"])] = {
            "score": score,
            "performance_label": label_from_score(score),
            "national_rank": nr,
            "national_percentile": round((1 - (nr - 1) / total) * 100, 2) if total > 1 else 100.0,
        }

    # Peer ranks within type
    for mtype in ("MP", "MLA"):
        type_rows = [r for r in rows if r["member_type"] == mtype]
        type_scores = [r["performance_score_100"] for r in type_rows]
        peer_ranks = competition_rank(type_scores)
        type_total = len(type_rows)
        P(f"  {mtype}: {type_total} ranked")
        for r, pr in zip(type_rows, peer_ranks):
            member_lookup[(r["member_id"], r["member_type"])]["peer_rank"] = pr
            member_lookup[(r["member_id"], r["member_type"])]["peer_percentile"] = (
                round((1 - (pr - 1) / type_total) * 100, 2) if type_total > 1 else 100.0
            )

    # Update member_intelligence (ranks + labels)
    args = []
    for (mid, mtype), v in member_lookup.items():
        args.append((
            v["national_rank"],
            v["national_percentile"],
            v["peer_rank"],
            v["peer_percentile"],
            v["performance_label"],
            mid,
            mtype,
        ))

    await db2.executemany(
        """
        UPDATE public.member_intelligence
        SET national_rank = $1,
            national_percentile = $2,
            peer_rank = $3,
            peer_percentile = $4,
            performance_label = $5,
            calculated_at = NOW()
        WHERE member_id = $6 AND member_type = $7
        """,
        args,
    )
    P(f"Updated {len(args)} member intelligence rows.")

    # ------------------------------------------------------------------
    # Recompute state ranks
    # ------------------------------------------------------------------
    P("\n--- Recomputing state ranks ---")
    state_rows = await db2.fetch("""
        SELECT state_id, performance_score_100
        FROM public.state_intelligence
        WHERE performance_score_100 IS NOT NULL
        ORDER BY performance_score_100 DESC, state_id ASC
    """)
    P(f"Ranking-qualified states: {len(state_rows)}")

    state_scores = [r["performance_score_100"] for r in state_rows]
    state_ranks = competition_rank(state_scores)
    state_total = len(state_rows)

    state_args = []
    for r, sr in zip(state_rows, state_ranks):
        score = r["performance_score_100"]
        state_args.append((
            sr,
            round((1 - (sr - 1) / state_total) * 100, 2) if state_total > 1 else 100.0,
            label_from_score(score),
            r["state_id"],
        ))

    await db2.executemany(
        """
        UPDATE public.state_intelligence
        SET rank = $1,
            national_percentile = $2,
            performance_label = $3,
            calculated_at = NOW()
        WHERE state_id = $4
        """,
        state_args,
    )
    P(f"Updated {len(state_args)} state intelligence rows.")

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------
    P("\n--- Verification ---")

    member_inv = await db2.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT a.performance_score_100, a.national_rank,
                   b.performance_score_100 as b_score, b.national_rank as b_rank
            FROM public.member_intelligence a
            JOIN public.member_intelligence b
              ON a.performance_score_100 < b.performance_score_100
            WHERE a.national_rank < b.national_rank
              AND a.performance_score_100 IS NOT NULL
              AND b.performance_score_100 IS NOT NULL
        ) t
    """)
    P(f"Member national_rank inversions: {member_inv}")

    peer_inv = await db2.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT a.member_type, a.performance_score_100, a.peer_rank,
                   b.performance_score_100 as b_score, b.peer_rank as b_rank
            FROM public.member_intelligence a
            JOIN public.member_intelligence b
              ON a.member_type = b.member_type
              AND a.performance_score_100 < b.performance_score_100
            WHERE a.peer_rank < b.peer_rank
              AND a.performance_score_100 IS NOT NULL
              AND b.performance_score_100 IS NOT NULL
        ) t
    """)
    P(f"Member peer_rank inversions: {peer_inv}")

    state_inv = await db2.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT a.performance_score_100, a.rank,
                   b.performance_score_100 as b_score, b.rank as b_rank
            FROM public.state_intelligence a
            JOIN public.state_intelligence b
              ON a.performance_score_100 < b.performance_score_100
            WHERE a.rank < b.rank
              AND a.performance_score_100 IS NOT NULL
              AND b.performance_score_100 IS NOT NULL
        ) t
    """)
    P(f"State rank inversions: {state_inv}")

    # Label-to-score consistency
    P("\n--- Label consistency check ---")
    rows = await db2.fetch("""
        SELECT performance_label, MIN(performance_score_100) as mn, MAX(performance_score_100) as mx, COUNT(*) as c
        FROM public.member_intelligence
        WHERE performance_score_100 IS NOT NULL
        GROUP BY performance_label
        ORDER BY mx DESC
    """)
    for r in rows:
        P(f"  {r['performance_label']}: min={r['mn']}, max={r['mx']}, count={r['c']}")

    rows = await db2.fetch("""
        SELECT performance_label, MIN(performance_score_100) as mn, MAX(performance_score_100) as mx, COUNT(*) as c
        FROM public.state_intelligence
        WHERE performance_score_100 IS NOT NULL
        GROUP BY performance_label
        ORDER BY mx DESC
    """)
    for r in rows:
        P(f"  STATE {r['performance_label']}: min={r['mn']}, max={r['mx']}, count={r['c']}")

    await db2.close()

    P(f"\nFinished: {datetime.now(timezone.utc).isoformat()}")
    P("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
