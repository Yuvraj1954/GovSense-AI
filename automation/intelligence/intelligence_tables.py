"""Build member_intelligence and state_intelligence tables from metrics."""
import datetime
from typing import List, Dict, Any
import asyncpg
from automation.intelligence.database import db2_pool
from automation.intelligence.performance import performance_label, performance_confidence


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _rank(items: List[Dict[str, Any]], score_key: str, ascending: bool = False) -> List[int]:
    """Return 1-based ranks. Higher score = better rank (1) if ascending=False."""
    indexed = [(i, _safe_float(item[score_key])) for i, item in enumerate(items)]
    indexed.sort(key=lambda x: (x[1] if ascending else -x[1], x[0]))
    ranks = [0] * len(items)
    for rank, (idx, _) in enumerate(indexed, start=1):
        ranks[idx] = rank
    return ranks


def _percentile_from_rank(rank: int, n: int) -> float:
    if n <= 1:
        return 100.0
    return 100.0 * (1.0 - (rank - 1) / (n - 1))


async def build_member_intelligence() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("""
                SELECT m.*, c.cluster_meta
                FROM member_metrics m
                LEFT JOIN (
                    SELECT cluster_id, MAX(cluster_meta) AS cluster_meta FROM (
                        SELECT cluster_id, cluster_label AS cluster_meta FROM member_metrics
                    ) sub GROUP BY cluster_id
                ) c ON c.cluster_id = m.cluster_id
            """)
            if not rows:
                return 0

            # National ranking SEPARATELY within each member_type (MP and MLA)
            qualifying = [r for r in rows if r["total_works"] > 0]
            non_qualifying = [r for r in rows if r["total_works"] == 0]

            by_type: Dict[str, List[Dict[str, Any]]] = {}
            for r in qualifying:
                by_type.setdefault(r["member_type"], []).append(r)

            national_ranks_map = {}
            for mtype, group in by_type.items():
                ranks = _rank(group, "performance_score_weighted", ascending=False)
                for i, r in enumerate(group):
                    national_ranks_map[(r["member_id"], mtype)] = ranks[i]

            # Peer ranking by member_type
            peer_ranks_map = {}
            for mtype, group in by_type.items():
                ranks = _rank(group, "performance_score_weighted", ascending=False)
                for i, r in enumerate(group):
                    peer_ranks_map[(r["member_id"], mtype)] = ranks[i]

            # Build member_intelligence records
            records = []
            for r in qualifying:
                score = _safe_float(r["performance_score_weighted"])
                sample = _safe_int(r["total_works"])
                label = performance_label(score, sample, zero_work=False)
                conf = performance_confidence(sample)
                national_rank = national_ranks_map[(r["member_id"], r["member_type"])]
                n_qual_type = len(by_type[r["member_type"]])
                national_pct = _percentile_from_rank(national_rank, n_qual_type)
                peer_rank = peer_ranks_map[(r["member_id"], r["member_type"])]
                peer_group_n = len(by_type[r["member_type"]])
                peer_pct = _percentile_from_rank(peer_rank, peer_group_n)

                cluster_label = r.get("cluster_label") or f"Cluster {r['cluster_id']}"

                records.append((
                    r["member_id"], r["member_type"], score, label, conf,
                    national_rank, national_pct, peer_rank, peer_pct,
                    r["cluster_id"], cluster_label,
                    _safe_float(r["risk_score"]), r["risk_level"], r["risk_confidence"], r["risk_evidence"],
                    sample, datetime.datetime.now(datetime.timezone.utc)
                ))

            for r in non_qualifying:
                records.append((
                    r["member_id"], r["member_type"], None, "NO_DATA", "NONE",
                    None, None, None, None,
                    r["cluster_id"], "NO_DATA",
                    _safe_float(r["risk_score"]), r["risk_level"], r["risk_confidence"], r["risk_evidence"],
                    0, datetime.datetime.now(datetime.timezone.utc)
                ))

            await conn.execute("TRUNCATE TABLE member_intelligence RESTART IDENTITY CASCADE")
            if records:
                columns = [
                    "member_id", "member_type", "performance_score_100", "performance_label",
                    "performance_confidence", "national_rank", "national_percentile", "peer_rank",
                    "peer_percentile", "cluster_id", "cluster_label", "risk_score", "risk_level",
                    "risk_confidence", "risk_evidence", "sample_size", "calculated_at"
                ]
                batch_size = 500
                for i in range(0, len(records), batch_size):
                    await conn.copy_records_to_table(
                        "member_intelligence",
                        records=records[i:i + batch_size],
                        columns=columns,
                    )
            return len(records)
    finally:
        await p2.close()


async def build_state_intelligence() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM state_metrics")
            if not rows:
                return 0

            qualifying = [r for r in rows if r["total_works"] > 0]
            non_qualifying = [r for r in rows if r["total_works"] == 0]
            n = len(qualifying)

            ranks = _rank(qualifying, "performance_score_weighted", ascending=False)

            records = []
            for i, r in enumerate(qualifying):
                score = _safe_float(r["performance_score_weighted"])
                sample = _safe_int(r["total_works"])
                label = performance_label(score, sample, zero_work=False)
                conf = performance_confidence(sample)
                rank = ranks[i]
                pct = _percentile_from_rank(rank, n)

                cluster_label = r.get("cluster_label") or f"Cluster {r['cluster_id']}"
                records.append((
                    r["state_id"], score, label, conf, rank, pct,
                    r["cluster_id"], cluster_label,
                    _safe_float(r["risk_score"]), r["risk_level"], r["risk_confidence"], r["risk_evidence"],
                    sample, datetime.datetime.now(datetime.timezone.utc)
                ))

            for r in non_qualifying:
                records.append((
                    r["state_id"], 0.0, "NO_DATA", "NONE", None, None,
                    r["cluster_id"], "NO_DATA",
                    _safe_float(r["risk_score"]), r["risk_level"], r["risk_confidence"], r["risk_evidence"],
                    0, datetime.datetime.now(datetime.timezone.utc)
                ))

            await conn.execute("TRUNCATE TABLE state_intelligence RESTART IDENTITY CASCADE")
            if records:
                columns = [
                    "state_id", "performance_score_100", "performance_label", "performance_confidence",
                    "rank", "national_percentile", "cluster_id", "cluster_label", "risk_score",
                    "risk_level", "risk_confidence", "risk_evidence", "sample_size", "calculated_at"
                ]
                batch_size = 500
                for i in range(0, len(records), batch_size):
                    await conn.copy_records_to_table(
                        "state_intelligence",
                        records=records[i:i + batch_size],
                        columns=columns,
                    )
            return len(records)
    finally:
        await p2.close()


async def build_all_intelligence() -> Dict[str, int]:
    m = await build_member_intelligence()
    s = await build_state_intelligence()
    return {"member_intelligence": m, "state_intelligence": s}
