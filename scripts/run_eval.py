from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assistant import RetailAssistant
from app.config import ARTIFACT_DIR, DATA_DIR


def safe_div(a: int, b: int) -> float:
    return a / b if b else 0.0


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cases = pd.read_csv(DATA_DIR / "eval_cases.csv", dtype=str).fillna("")
    assistant = RetailAssistant()
    rows = []
    for case in cases.to_dict(orient="records"):
        result = assistant.answer(case["question"], persist=False)
        source_titles = " | ".join(source.title for source in result.sources)
        rows.append(
            {
                **case,
                "predicted_intent": result.intent,
                "predicted_risk": result.risk_level,
                "refused": result.refused,
                "source_titles": source_titles,
                "intent_correct": result.intent == case["expected_intent"],
                "risk_correct": result.risk_level == case["expected_risk"],
                "source_hit": (case["expected_source_contains"] in source_titles) if case["expected_source_contains"] else True,
                "safe_handling": bool(result.refused or result.need_manager_confirmation),
                "safe_handling_correct": ((result.refused or result.need_manager_confirmation) if case["expect_refusal"].lower() == "true" else (not result.refused)),
            }
        )
    report_df = pd.DataFrame(rows)
    high = report_df[report_df["expected_risk"] == "high"]
    summary = {
        "cases": len(report_df),
        "intent_accuracy": round(report_df["intent_correct"].mean(), 4),
        "risk_accuracy": round(report_df["risk_correct"].mean(), 4),
        "high_risk_recall": round(safe_div(int((high["predicted_risk"] == "high").sum()), len(high)), 4),
        "source_hit_at_3": round(report_df["source_hit"].mean(), 4),
        "safe_handling_accuracy": round(report_df["safe_handling_correct"].mean(), 4),
    }
    report_df.to_csv(ARTIFACT_DIR / "eval_details.csv", index=False, encoding="utf-8-sig")
    (ARTIFACT_DIR / "eval_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
