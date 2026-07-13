from pathlib import Path

from app.db import (
    count_pending_by_risk,
    create_product_request,
    dashboard_metrics,
    escalate_review,
    get_product_request,
    init_db,
    list_notifications,
    list_pending_reviews,
    list_product_requests,
    track_user_session,
    update_product_request,
    update_review,
)


def test_manager_scope_and_regional_scope(tmp_path: Path):
    db = tmp_path / "scope.db"
    init_db(db)
    manager = list_pending_reviews(role="manager", user_store="S001", db_path=db)
    regional = list_pending_reviews(role="regional_admin", user_store="ALL", db_path=db)
    assert manager
    assert all(item["store_id"] == "S001" for item in manager)
    assert len(regional) > len(manager)


def test_risk_counts_are_split(tmp_path: Path):
    db = tmp_path / "counts.db"
    init_db(db)
    counts = count_pending_by_risk(role="manager", user_store="S001", db_path=db)
    assert counts["high"] >= 1
    assert counts["medium"] >= 1


def test_escalated_review_leaves_manager_queue(tmp_path: Path):
    db = tmp_path / "escalate.db"
    init_db(db)
    item = list_pending_reviews(role="manager", user_store="S001", db_path=db)[0]
    escalate_review(item["review_id"], "跨店争议，需要区域终审", 2, db)
    manager_ids = {x["review_id"] for x in list_pending_reviews(role="manager", user_store="S001", db_path=db)}
    regional = list_pending_reviews(role="regional_admin", user_store="ALL", db_path=db)
    assert item["review_id"] not in manager_ids
    assert any(x["review_id"] == item["review_id"] and x["review_level"] == "regional" for x in regional)


def test_review_reply_creates_associate_notification(tmp_path: Path):
    db = tmp_path / "notice.db"
    init_db(db)
    item = list_pending_reviews(role="manager", user_store="S001", db_path=db)[0]
    update_review(item["review_id"], "confirmed", "请按当前规则回复。", "已核验", 2, db)
    notices = list_notifications(item["user_id"], unread_only=True, db_path=db)
    assert any(n["related_id"] == item["query_id"] for n in notices)


def test_unknown_product_request_flow(tmp_path: Path):
    db = tmp_path / "product.db"
    init_db(db)
    request_id = create_product_request("6909999999999", "S001", 1, "新款外套", "外套", "门店新品", db_path=db)
    request = get_product_request(request_id, db)
    assert request["status"] == "待店长补充"
    update_product_request(request_id, 2, {"proposed_product_code": "FS-WT-099", "status": "待区域审核", "manager_id": 2}, db)
    request = get_product_request(request_id, db)
    assert request["status"] == "待区域审核"
    assert list_product_requests(store_id="S001", db_path=db)


def test_session_metrics_are_available(tmp_path: Path):
    db = tmp_path / "metrics.db"
    init_db(db)
    sid = track_user_session(1, "S001", "associate", db_path=db)
    track_user_session(1, "S001", "associate", sid, db)
    metrics = dashboard_metrics(store_id="S001", db_path=db)
    assert "associate_active_rate" in metrics
    assert "avg_session_minutes" in metrics
    assert "bad_case_resolution_rate" in metrics
