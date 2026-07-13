from pathlib import Path

from app.db import (
    add_feedback,
    count_open_feedback,
    dashboard_metrics,
    feedback_exists,
    init_db,
    learning_progress,
    list_feedback,
    list_recent_questions,
    list_reviews_scope,
    record_question,
    submit_learning_result,
    track_event,
)


def make_db(tmp_path: Path) -> Path:
    db = tmp_path / "feature.db"
    init_db(db)
    return db


def test_high_risk_question_enters_review_and_badcase(tmp_path):
    db = make_db(tmp_path)
    query_id = record_question({
        "question": "能不能承诺这件羊毛大衣绝对不起球？",
        "intent": "商品知识",
        "risk_level": "high",
        "conclusion": "不能绝对承诺。",
        "suggested_script": "羊毛面料摩擦位置可能轻微起球。",
        "warning": "禁止绝对化承诺。",
        "source_titles": ["商品资料"],
        "need_manager_confirmation": True,
        "refused": False,
        "confidence_level": "high",
    }, 1, "S001", db)
    rows = list_feedback(store_id="S001", db_path=db)
    assert any(row["query_id"] == query_id and row["feedback_type"] == "高风险自动入池" for row in rows)
    assert count_open_feedback("manager", "S001", db_path=db) >= 1


def test_user_feedback_can_replace_auto_risk_feedback(tmp_path):
    db = make_db(tmp_path)
    query_id = record_question({
        "question": "吊牌剪了能不能直接退？",
        "intent": "售后规则", "risk_level": "high", "conclusion": "需核验",
        "suggested_script": "请到店核验。", "warning": "不得直接承诺", "source_titles": [],
        "need_manager_confirmation": True, "refused": False, "confidence_level": "high",
    }, 1, "S001", db)
    assert feedback_exists(query_id, db) is False
    add_feedback(query_id, "答案不准确", "规则没有说明清楚", db)
    assert feedback_exists(query_id, db) is True
    item = next(x for x in list_feedback(store_id="S001", db_path=db) if x["query_id"] == query_id)
    assert item["feedback_type"] == "答案不准确"


def test_recent_questions_returns_latest(tmp_path):
    db = make_db(tmp_path)
    rows = list_recent_questions(1, 3, db)
    assert len(rows) <= 3
    assert rows


def test_usage_events_enter_dashboard(tmp_path):
    db = make_db(tmp_path)
    track_event(1, "S001", "快捷算价", "calculator", "", {"items": ["FS-CS-001"]}, db)
    track_event(1, "S001", "连带推荐加入算价", "product", "FS-KZ-001", {}, db)
    metrics = dashboard_metrics(store_id="S001", db_path=db)
    assert metrics["calculator_uses"] >= 1
    assert metrics["recommendation_uses"] >= 1


def test_learning_progress_records_growth(tmp_path):
    db = make_db(tmp_path)
    submit_learning_result(1, "S001", "quiz-a", "售后规则", "A", True, db)
    rows = learning_progress("S001", 1, db)
    assert rows[0]["attempts"] == 1
    assert rows[0]["accuracy"] == 100.0


def test_manager_review_scope_is_single_store(tmp_path):
    db = make_db(tmp_path)
    rows = list_reviews_scope(role="manager", user_store="S001", state_group="全部", db_path=db)
    assert rows
    assert all(row["store_id"] == "S001" for row in rows)


def test_regional_review_scope_can_cross_stores(tmp_path):
    db = make_db(tmp_path)
    rows = list_reviews_scope(role="regional_admin", user_store="ALL", state_group="全部", db_path=db)
    assert {row["store_id"] for row in rows} >= {"S001", "S002"}


def test_dashboard_contains_business_value_metrics(tmp_path):
    db = make_db(tmp_path)
    metrics = dashboard_metrics(store_id="ALL", db_path=db)
    assert "knowledge_coverage_rate" in metrics
    assert "high_risk_interception_rate" in metrics
    assert all("综合得分" in row for row in metrics["store_rank"])
