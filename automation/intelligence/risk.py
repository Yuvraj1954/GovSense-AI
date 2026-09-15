"""Risk aggregation for members and states."""
import datetime
import json
from typing import Dict, Any, List
import asyncpg
from automation.intelligence.database import db2_pool


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _risk_level(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "MODERATE"
    return "LOW"


def _risk_confidence(total: int, signals: int) -> str:
    if total == 0:
        return "LOW"
    if total < 5:
        return "LOW"
    if signals >= 3 and total >= 15:
        return "HIGH"
    if signals >= 2 and total >= 10:
        return "MEDIUM"
    return "MEDIUM"


def _build_evidence(high_risk: int, overdue_1y: int, overdue_2y: int,
                    anomaly_level: str, flagged_rate: float, risk_flags: List[str]) -> List[Dict[str, Any]]:
    evidence = []
    if high_risk > 0:
        evidence.append({
            "type": "WORK_RISK",
            "severity": "HIGH",
            "description": f"{high_risk} work(s) flagged as high risk by deterministic analytics.",
            "count": high_risk,
        })
    if overdue_2y > 0:
        evidence.append({
            "type": "LONG_RUNNING",
            "severity": "CRITICAL",
            "description": f"{overdue_2y} ongoing work(s) older than 2 years.",
            "count": overdue_2y,
        })
    elif overdue_1y > 0:
        evidence.append({
            "type": "LONG_RUNNING",
            "severity": "HIGH",
            "description": f"{overdue_1y} ongoing work(s) older than 1 year.",
            "count": overdue_1y,
        })
    if anomaly_level == "HIGHLY_UNUSUAL":
        evidence.append({
            "type": "ANOMALY",
            "severity": "HIGH",
            "description": "Isolation Forest detected highly unusual work patterns.",
        })
    elif anomaly_level == "UNUSUAL":
        evidence.append({
            "type": "ANOMALY",
            "severity": "MEDIUM",
            "description": "Isolation Forest detected unusual work patterns.",
        })
    if flagged_rate >= 30:
        evidence.append({
            "type": "PORTFOLIO_RISK",
            "severity": "HIGH",
            "description": f"High flagged-work rate ({flagged_rate:.1f}%).",
            "rate_pct": round(flagged_rate, 2),
        })
    elif flagged_rate >= 15:
        evidence.append({
            "type": "PORTFOLIO_RISK",
            "severity": "MEDIUM",
            "description": f"Elevated flagged-work rate ({flagged_rate:.1f}%).",
            "rate_pct": round(flagged_rate, 2),
        })
    for flag in risk_flags[:3]:
        evidence.append({
            "type": "STATISTICAL_SIGNAL",
            "severity": "MEDIUM",
            "description": f"Signal: {flag}",
            "signal": flag,
        })
    return evidence


async def compute_member_risk() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM member_metrics")
            updates = []
            for r in rows:
                total = _safe_int(r["total_works"])
                if total == 0:
                    score = 0.0
                    level = "LOW"
                    conf = "LOW"
                    evidence = [{"type": "NO_DATA", "severity": "INFO", "description": "No works available for risk assessment."}]
                else:
                    high = _safe_int(r["high_risk_works"])
                    overdue_1y = _safe_int(r["overdue_over_1_year"])
                    overdue_2y = _safe_int(r["overdue_over_2_years"])
                    flagged_rate = _safe_float(r["flagged_rate_pct"])
                    anomaly_level = r["anomaly_level"] or "NORMAL"
                    anomaly_score = _safe_float(r["anomaly_score"])

                    # Composite risk score
                    score = 0.0
                    score += min(40.0, high / max(1, total) * 100.0 * 0.8)
                    score += min(25.0, overdue_1y / max(1, total) * 100.0 * 0.5)
                    score += min(20.0, flagged_rate * 0.4)
                    if anomaly_level == "HIGHLY_UNUSUAL":
                        score += 20.0
                    elif anomaly_level == "UNUSUAL":
                        score += 10.0
                    score += anomaly_score * 0.05
                    score = min(100.0, max(0.0, score))

                    level = _risk_level(score)
                    signals = sum(1 for x in [high, overdue_1y, overdue_2y] if x > 0)
                    if anomaly_level != "NORMAL":
                        signals += 1
                    conf = _risk_confidence(total, signals)
                    evidence = _build_evidence(high, overdue_1y, overdue_2y, anomaly_level, flagged_rate, [])

                updates.append((
                    r["member_id"], r["member_type"], score, level, conf,
                    json.dumps(evidence), total, datetime.datetime.now(datetime.timezone.utc)
                ))

            await conn.executemany("""
                UPDATE member_metrics
                SET risk_score = $3,
                    risk_level = $4,
                    risk_confidence = $5,
                    risk_evidence = $6,
                    sample_size = $7,
                    calculated_at = $8
                WHERE member_id = $1 AND member_type = $2
            """, updates)
            return len(updates)
    finally:
        await p2.close()


async def compute_state_risk() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM state_metrics")
            updates = []
            for r in rows:
                total = _safe_int(r["total_works"])
                if total == 0:
                    score = 0.0
                    level = "LOW"
                    conf = "LOW"
                    evidence = [{"type": "NO_DATA", "severity": "INFO", "description": "No works available for state risk assessment."}]
                else:
                    high = _safe_int(r["high_risk_works"])
                    overdue_1y = _safe_int(r["overdue_over_1_year"])
                    overdue_2y = _safe_int(r["overdue_over_2_years"])
                    risk_rate = _safe_float(r["risk_rate_pct"])
                    anomaly_level = r["anomaly_level"] or "NORMAL"
                    anomaly_score = _safe_float(r["anomaly_score"])

                    score = 0.0
                    score += min(40.0, high / max(1, total) * 100.0 * 0.8)
                    score += min(25.0, overdue_1y / max(1, total) * 100.0 * 0.5)
                    score += min(20.0, risk_rate * 0.4)
                    if anomaly_level == "HIGHLY_UNUSUAL":
                        score += 20.0
                    elif anomaly_level == "UNUSUAL":
                        score += 10.0
                    score += anomaly_score * 0.05
                    score = min(100.0, max(0.0, score))

                    level = _risk_level(score)
                    signals = sum(1 for x in [high, overdue_1y, overdue_2y] if x > 0)
                    if anomaly_level != "NORMAL":
                        signals += 1
                    conf = _risk_confidence(total, signals)
                    evidence = _build_evidence(high, overdue_1y, overdue_2y, anomaly_level, risk_rate, [])

                updates.append((
                    r["state_id"], score, level, conf,
                    json.dumps(evidence), total, datetime.datetime.now(datetime.timezone.utc)
                ))

            await conn.executemany("""
                UPDATE state_metrics
                SET risk_score = $2,
                    risk_level = $3,
                    risk_confidence = $4,
                    risk_evidence = $5,
                    sample_size = $6,
                    calculated_at = $7
                WHERE state_id = $1
            """, updates)
            return len(updates)
    finally:
        await p2.close()


async def run_all_risk() -> Dict[str, int]:
    m = await compute_member_risk()
    s = await compute_state_risk()
    return {"member_risk": m, "state_risk": s}
