from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_after(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    store_name TEXT NOT NULL,
    region_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    opened_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    store_id TEXT NOT NULL,
    region_id TEXT NOT NULL DEFAULT 'R-SOUTH',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    FOREIGN KEY(store_id) REFERENCES stores(store_id)
);

CREATE TABLE IF NOT EXISTS questions (
    query_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    store_id TEXT NOT NULL,
    question TEXT NOT NULL,
    intent TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    suggested_script TEXT NOT NULL,
    warning TEXT NOT NULL,
    source_titles TEXT NOT NULL,
    need_manager_confirmation INTEGER NOT NULL,
    refused INTEGER NOT NULL,
    confidence_level TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(store_id) REFERENCES stores(store_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL UNIQUE,
    reviewer_id INTEGER,
    review_status TEXT NOT NULL DEFAULT 'pending_manager',
    review_level TEXT NOT NULL DEFAULT 'manager',
    priority INTEGER NOT NULL DEFAULT 2,
    due_at TEXT NOT NULL DEFAULT '',
    corrected_answer TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '',
    escalation_reason TEXT NOT NULL DEFAULT '',
    escalated_by INTEGER,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    FOREIGN KEY(query_id) REFERENCES questions(query_id),
    FOREIGN KEY(reviewer_id) REFERENCES users(user_id),
    FOREIGN KEY(escalated_by) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    related_id INTEGER,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL UNIQUE,
    feedback_type TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    issue_type TEXT NOT NULL DEFAULT '未分类',
    processing_status TEXT NOT NULL DEFAULT '待处理',
    assigned_to INTEGER,
    resolution_action TEXT NOT NULL DEFAULT '',
    linked_entity_type TEXT NOT NULL DEFAULT '',
    linked_doc_id TEXT NOT NULL DEFAULT '',
    optimized_version TEXT NOT NULL DEFAULT '',
    verification_note TEXT NOT NULL DEFAULT '',
    handled_by INTEGER,
    created_at TEXT NOT NULL,
    handled_at TEXT,
    FOREIGN KEY(query_id) REFERENCES questions(query_id),
    FOREIGN KEY(assigned_to) REFERENCES users(user_id),
    FOREIGN KEY(handled_by) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS knowledge_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER,
    store_id TEXT NOT NULL,
    submitted_by INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    suggested_content TEXT NOT NULL DEFAULT '',
    linked_entity_type TEXT NOT NULL DEFAULT '',
    linked_entity_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '待运营处理',
    assigned_to INTEGER,
    resolution TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(feedback_id) REFERENCES feedback(feedback_id),
    FOREIGN KEY(submitted_by) REFERENCES users(user_id),
    FOREIGN KEY(assigned_to) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS product_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_code TEXT NOT NULL,
    proposed_product_code TEXT NOT NULL DEFAULT '',
    product_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    fabric TEXT NOT NULL DEFAULT '',
    fit TEXT NOT NULL DEFAULT '',
    target_customer TEXT NOT NULL DEFAULT '',
    customer_tags TEXT NOT NULL DEFAULT '',
    aliases TEXT NOT NULL DEFAULT '',
    selling_points TEXT NOT NULL DEFAULT '',
    styling_tips TEXT NOT NULL DEFAULT '',
    size_notes TEXT NOT NULL DEFAULT '',
    common_objection TEXT NOT NULL DEFAULT '',
    suggested_script TEXT NOT NULL DEFAULT '',
    forbidden_claims TEXT NOT NULL DEFAULT '',
    photo_path TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    store_id TEXT NOT NULL,
    requested_by INTEGER NOT NULL,
    manager_id INTEGER,
    regional_reviewer_id INTEGER,
    status TEXT NOT NULL DEFAULT '待店长补充',
    rejection_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(scanned_code, store_id, status),
    FOREIGN KEY(store_id) REFERENCES stores(store_id),
    FOREIGN KEY(requested_by) REFERENCES users(user_id),
    FOREIGN KEY(manager_id) REFERENCES users(user_id),
    FOREIGN KEY(regional_reviewer_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS rule_acknowledgements (
    ack_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    doc_id TEXT NOT NULL,
    version TEXT NOT NULL,
    acknowledged_at TEXT NOT NULL,
    UNIQUE(user_id, doc_id, version),
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    actor_name TEXT NOT NULL DEFAULT '',
    actor_role TEXT NOT NULL DEFAULT '',
    store_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '',
    before_json TEXT NOT NULL DEFAULT '',
    after_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(actor_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    store_id TEXT NOT NULL,
    role TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active_seconds INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS complaint_logs (
    complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL,
    complaint_type TEXT NOT NULL,
    related_query_id INTEGER,
    occurred_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(store_id) REFERENCES stores(store_id),
    FOREIGN KEY(related_query_id) REFERENCES questions(query_id)
);

CREATE TABLE IF NOT EXISTS error_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    store_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    store_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS learning_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    store_id TEXT NOT NULL,
    question_key TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    selected_answer TEXT NOT NULL DEFAULT '',
    is_correct INTEGER NOT NULL DEFAULT 0,
    practice_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, question_key, practice_date),
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);
"""


@contextmanager
def connect(db_path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _column_names(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _seed_reference_data(conn: sqlite3.Connection) -> None:
    stores = [
        ("S001", "广州天河店", "R-SOUTH", "active", "2023-01-01"),
        ("S002", "广州番禺店", "R-SOUTH", "active", "2023-06-01"),
        ("S003", "佛山南海店", "R-SOUTH", "paused", "2024-03-01"),
        ("ALL", "区域运营", "R-SOUTH", "active", "2023-01-01"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO stores(store_id,store_name,region_id,status,opened_at) VALUES(?,?,?,?,?)",
        stores,
    )
    users = [
        (1, "导购-小林", "associate", "S001", "R-SOUTH", "active", "associate.s001@example.com", utc_now()),
        (2, "店长-周敏", "manager", "S001", "R-SOUTH", "active", "manager.s001@example.com", utc_now()),
        (3, "区域运营-陈经理", "regional_admin", "ALL", "R-SOUTH", "active", "regional@example.com", utc_now()),
        (4, "导购-小许", "associate", "S002", "R-SOUTH", "active", "associate.s002@example.com", utc_now()),
        (5, "店长-李岚", "manager", "S002", "R-SOUTH", "active", "manager.s002@example.com", utc_now()),
        (6, "导购-阿敏", "associate", "S003", "R-SOUTH", "active", "associate.s003@example.com", utc_now()),
        (7, "店长-赵颖", "manager", "S003", "R-SOUTH", "active", "manager.s003@example.com", utc_now()),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO users(user_id,name,role,store_id,region_id,status,email,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        users,
    )


def _seed_demo_operations(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] > 0:
        return
    now = datetime.now(timezone.utc)
    samples = [
        (1, "S001", "吊牌剪了但是没穿能换吗？", "售后规则", "high", "吊牌已剪属于特殊退换场景，需要核验商品状态。", "“我先帮您核验商品状态，并请店长确认处理口径。”", "不得直接承诺退换。", "商品退换货服务管理规则 V1.1", 1, 0, "high", now - timedelta(hours=31)),
        (1, "S001", "会员折扣和满减可以一起吗？", "活动会员", "medium", "当前活动不支持与会员折扣叠加。", "“两种优惠需要二选一，我帮您比较更划算的方案。”", "最终以收银系统核算为准。", "门店促销活动执行管理规则 V1.1", 1, 0, "high", now - timedelta(hours=5)),
        (4, "S002", "特价商品顾客坚持要退款怎么办？", "售后规则", "high", "需要核验质量问题、活动公示和购买凭证。", "“我先核对商品和购买记录，再请负责人给您明确处理方案。”", "不得生硬拒绝或私自承诺。", "商品退换货服务管理规则 V1.1", 1, 0, "medium", now - timedelta(hours=26)),
        (4, "S002", "白衬衫会不会透？", "商品知识", "low", "白色款建议搭配肤色内衣。", "“这款面料做了防透处理，建议搭配肤色内衣并现场试穿确认。”", "不得承诺任何内衣都完全不透。", "经典修身免烫白衬衫 V1.1", 0, 0, "high", now - timedelta(hours=3)),
        (6, "S003", "这件大衣绝对不起球吧？", "商品知识", "high", "羊毛类面料摩擦部位可能出现轻微起球。", "“羊毛面料在摩擦部位可能轻微起球，按洗标护理会更耐穿。”", "不得承诺绝对不起球。", "中长款双面呢羊毛大衣 V1.1", 1, 0, "high", now - timedelta(hours=2)),
        (1, "S001", "FS-KZ-001的M码有货吗？", "商品知识", "low", "S001门店M码当前断货。", "“本店M码暂时没有，我帮您查附近门店调货。”", "库存以系统实时状态为准。", "实时库存", 0, 0, "high", now - timedelta(hours=1)),
    ]
    for row in samples:
        cur = conn.execute(
            """INSERT INTO questions(user_id,store_id,question,intent,risk_level,conclusion,suggested_script,warning,
               source_titles,need_manager_confirmation,refused,confidence_level,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*row[:-1], row[-1].isoformat(timespec="seconds")),
        )
        qid = int(cur.lastrowid)
        if row[9]:
            priority = 1 if row[4] == "high" else 2
            due = row[-1] + timedelta(hours=24)
            conn.execute(
                """INSERT INTO reviews(query_id,review_status,review_level,priority,due_at,created_at)
                   VALUES(?, 'pending_manager', 'manager', ?, ?, ?)""",
                (qid, priority, due.isoformat(timespec="seconds"), row[-1].isoformat(timespec="seconds")),
            )
    # Feedback records for the management loop.
    feedback_rows = [
        (4, "答案不准确", "没有说明白色内衣的差异", "话术不准", "待处理"),
        (6, "来源不匹配", "库存更新时间不够醒目", "系统错误", "处理中"),
    ]
    for qid, ftype, comment, issue, status in feedback_rows:
        conn.execute(
            """INSERT INTO feedback(query_id,feedback_type,comment,issue_type,processing_status,created_at)
               VALUES(?,?,?,?,?,?)""",
            (qid, ftype, comment, issue, status, utc_now()),
        )


def init_db(db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        # Safe migrations for databases created by earlier project versions.
        for definition in [
            "review_level TEXT NOT NULL DEFAULT 'manager'",
            "priority INTEGER NOT NULL DEFAULT 2",
            "due_at TEXT NOT NULL DEFAULT ''",
            "escalation_reason TEXT NOT NULL DEFAULT ''",
            "escalated_by INTEGER",
        ]:
            _ensure_column(conn, "reviews", definition)
        for definition in [
            "assigned_to INTEGER",
            "resolution_action TEXT NOT NULL DEFAULT ''",
            "linked_entity_type TEXT NOT NULL DEFAULT ''",
            "verification_note TEXT NOT NULL DEFAULT ''",
            "due_at TEXT NOT NULL DEFAULT ''",
            "evidence_path TEXT NOT NULL DEFAULT ''",
            "cluster_key TEXT NOT NULL DEFAULT ''",
            "updated_at TEXT NOT NULL DEFAULT ''",
        ]:
            _ensure_column(conn, "feedback", definition)
        for definition in [
            "updated_at TEXT NOT NULL DEFAULT ''",
        ]:
            _ensure_column(conn, "reviews", definition)
        _ensure_column(conn, "users", "email TEXT NOT NULL DEFAULT ''")
        _seed_reference_data(conn)
        _seed_demo_operations(conn)


def get_user(user_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=? AND status='active'", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    normalized = email.strip().lower()
    if not normalized:
        return None
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email)=? AND status='active'",
            (normalized,),
        ).fetchone()
        return dict(row) if row else None


def list_users(role: str | None = None, store_id: str | None = None, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    clauses = ["status='active'"]
    params: list[Any] = []
    if role:
        clauses.append("role=?")
        params.append(role)
    if store_id and store_id != "ALL":
        clauses.append("store_id=?")
        params.append(store_id)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM users WHERE {' AND '.join(clauses)} ORDER BY role,name", params)]


def list_stores(region_id: str | None = None, include_inactive: bool = True, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    clauses = ["store_id!='ALL'"]
    params: list[Any] = []
    if region_id:
        clauses.append("region_id=?")
        params.append(region_id)
    if not include_inactive:
        clauses.append("status='active'")
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM stores WHERE {' AND '.join(clauses)} ORDER BY store_id", params)]


def audit_log(
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str = "",
    before: Any = None,
    after: Any = None,
    store_id: str = "",
    db_path: Path | str = DB_PATH,
) -> int:
    actor = get_user(actor_id, db_path) if actor_id else None
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO audit_logs(actor_id,actor_name,actor_role,store_id,action,entity_type,entity_id,before_json,after_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                actor_id,
                actor.get("name", "") if actor else "系统",
                actor.get("role", "system") if actor else "system",
                store_id or (actor.get("store_id", "") if actor else ""),
                action,
                entity_type,
                str(entity_id),
                json.dumps(before, ensure_ascii=False, default=str) if before is not None else "",
                json.dumps(after, ensure_ascii=False, default=str) if after is not None else "",
                utc_now(),
            ),
        )
        return int(cur.lastrowid)


def list_audit_logs(
    store_id: str | None = None,
    action: str | None = None,
    limit: int = 300,
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if store_id and store_id != "ALL":
        clauses.append("store_id=?")
        params.append(store_id)
    if action and action != "全部":
        clauses.append("action=?")
        params.append(action)
    params.append(limit)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM audit_logs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?", params
        )]


def record_question(payload: dict[str, Any], user_id: int, store_id: str, db_path: Path | str = DB_PATH) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO questions(user_id,store_id,question,intent,risk_level,conclusion,suggested_script,warning,
               source_titles,need_manager_confirmation,refused,confidence_level,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                store_id,
                payload["question"],
                payload["intent"],
                payload["risk_level"],
                payload["conclusion"],
                payload["suggested_script"],
                payload.get("warning", ""),
                " | ".join(payload.get("source_titles", [])),
                int(payload.get("need_manager_confirmation", False)),
                int(payload.get("refused", False)),
                payload.get("confidence_level", "medium"),
                utc_now(),
            ),
        )
        query_id = int(cur.lastrowid)
        if payload.get("need_manager_confirmation"):
            priority = 1 if payload.get("risk_level") == "high" else 2 if payload.get("risk_level") == "medium" else 3
            conn.execute(
                """INSERT OR IGNORE INTO reviews(query_id,review_status,review_level,priority,due_at,updated_at,created_at)
                   VALUES(?, 'pending_manager', 'manager', ?, ?, ?, ?)""",
                (query_id, priority, iso_after(24), utc_now(), utc_now()),
            )
            issue_type = "诱导违规" if any(x in payload.get("warning", "") for x in ["虚假", "绝对", "禁止"]) else "边界模糊"
            conn.execute(
                """INSERT OR IGNORE INTO feedback(query_id,feedback_type,comment,issue_type,processing_status,due_at,cluster_key,updated_at,created_at)
                   VALUES(?, '高风险自动入池', '系统自动沉淀高风险问题，供知识库与服务口径复盘。', ?, '待处理', ?, ?, ?, ?)""",
                (query_id, issue_type, iso_after(48), payload.get("intent", "其他"), utc_now(), utc_now()),
            )
        return query_id


def list_user_questions(user_id: int, limit: int = 100, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT q.*, r.review_status, r.corrected_answer, r.review_note, r.reviewed_at,
                      reviewer.name AS reviewer_name
               FROM questions q
               LEFT JOIN reviews r ON r.query_id=q.query_id
               LEFT JOIN users reviewer ON reviewer.user_id=r.reviewer_id
               WHERE q.user_id=? ORDER BY q.created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def create_notification(
    user_id: int,
    notification_type: str,
    title: str,
    content: str,
    related_id: int | None = None,
    db_path: Path | str = DB_PATH,
) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO notifications(user_id,notification_type,title,content,related_id,created_at)
               VALUES(?,?,?,?,?,?)""",
            (user_id, notification_type, title, content, related_id, utc_now()),
        )
        return int(cur.lastrowid)


def list_notifications(user_id: int, unread_only: bool = False, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    clause = "AND is_read=0" if unread_only else ""
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM notifications WHERE user_id=? {clause} ORDER BY created_at DESC LIMIT 100", (user_id,)
        )]


def mark_notifications_read(user_id: int, notification_ids: list[int] | None = None, db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        if notification_ids:
            placeholders = ",".join("?" for _ in notification_ids)
            conn.execute(
                f"UPDATE notifications SET is_read=1 WHERE user_id=? AND notification_id IN ({placeholders})",
                [user_id, *notification_ids],
            )
        else:
            conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))


def add_feedback(query_id: int, feedback_type: str, comment: str = "", db_path: Path | str = DB_PATH) -> int:
    issue_map = {
        "答案不准确": "答案错误",
        "来源不匹配": "来源不匹配",
        "规则已过期": "规则过期",
        "话术不适合": "话术不准",
        "没有解决问题": "知识库缺失",
        "应交由店长处理": "边界模糊",
        "有帮助": "未分类",
    }
    now = utc_now()
    with connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM feedback WHERE query_id=?", (query_id,)).fetchone()
        if existing:
            existing = dict(existing)
            # 自动入池的高风险问题允许被导购的真实反馈覆盖。
            if existing.get("feedback_type") == "高风险自动入池" or feedback_type != "有帮助":
                conn.execute(
                    """UPDATE feedback SET feedback_type=?,comment=?,issue_type=?,updated_at=? WHERE query_id=?""",
                    (feedback_type, comment, issue_map.get(feedback_type, existing.get("issue_type", "未分类")), now, query_id),
                )
            return int(existing["feedback_id"])
        cur = conn.execute(
            """INSERT INTO feedback(query_id,feedback_type,comment,issue_type,processing_status,due_at,updated_at,created_at)
               VALUES(?,?,?,?, '待处理', ?, ?, ?)""",
            (query_id, feedback_type, comment, issue_map.get(feedback_type, "未分类"), iso_after(48), now, now),
        )
        return int(cur.lastrowid)

def feedback_exists(query_id: int, db_path: Path | str = DB_PATH) -> bool:
    with connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM feedback WHERE query_id=? AND feedback_type!='高风险自动入池'", (query_id,)).fetchone() is not None


def _review_scope_clause(role: str, user_store: str, region_id: str = "R-SOUTH") -> tuple[str, list[Any]]:
    if role == "manager":
        return "q.store_id=? AND r.review_level='manager'", [user_store]
    if role == "regional_admin":
        return "s.region_id=?", [region_id]
    return "1=0", []


def list_pending_reviews(
    db_path: Path | str = DB_PATH,
    *,
    role: str = "regional_admin",
    user_store: str = "ALL",
    region_id: str = "R-SOUTH",
    store_id: str | None = None,
    risk_level: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    overdue_only: bool = False,
) -> list[dict[str, Any]]:
    scope, params = _review_scope_clause(role, user_store, region_id)
    statuses = "('pending_manager','pending_regional','processing_manager','processing_regional')"
    clauses = [f"r.review_status IN {statuses}", scope]
    if store_id and store_id != "ALL":
        clauses.append("q.store_id=?")
        params.append(store_id)
    if risk_level and risk_level != "全部":
        clauses.append("q.risk_level=?")
        params.append(risk_level)
    if date_from:
        clauses.append("substr(r.created_at,1,10)>=?")
        params.append(date_from)
    if date_to:
        clauses.append("substr(r.created_at,1,10)<=?")
        params.append(date_to)
    if overdue_only:
        clauses.append("r.due_at!='' AND r.due_at<?")
        params.append(utc_now())
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT r.review_id,r.query_id,r.review_status,r.review_level,r.priority,r.due_at,
                       r.created_at,r.escalation_reason,q.store_id,q.user_id,q.question,q.conclusion,
                       q.suggested_script,q.warning,q.source_titles,q.intent,q.risk_level,q.confidence_level,
                       u.name AS requester,s.store_name,
                       CASE WHEN r.due_at!='' AND r.due_at<? THEN 1 ELSE 0 END AS overdue
                FROM reviews r
                JOIN questions q ON q.query_id=r.query_id
                JOIN users u ON u.user_id=q.user_id
                JOIN stores s ON s.store_id=q.store_id
                WHERE {' AND '.join(clauses)}
                ORDER BY overdue DESC,
                         CASE r.review_level WHEN 'regional' THEN 1 ELSE 2 END,
                         CASE q.risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                         r.created_at ASC""",
            [utc_now(), *params],
        ).fetchall()
        return [dict(r) for r in rows]


def list_reviews_scope(
    *,
    role: str,
    user_store: str,
    store_id: str | None = None,
    risk_level: str | None = None,
    state_group: str = "待处理",
    date_from: str | None = None,
    date_to: str | None = None,
    region_id: str = "R-SOUTH",
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    scope, params = _review_scope_clause(role, user_store, region_id)
    groups = {
        "全部": ["pending_manager","pending_regional","processing_manager","processing_regional","confirmed","corrected","rejected"],
        "待处理": ["pending_manager","pending_regional"],
        "处理中": ["processing_manager","processing_regional"],
        "已完成": ["confirmed","corrected"],
        "已驳回": ["rejected"],
    }
    statuses = groups.get(state_group, groups["待处理"])
    placeholders = ",".join("?" for _ in statuses)
    clauses = [f"r.review_status IN ({placeholders})", scope]
    params = [*statuses, *params]
    if store_id and store_id != "ALL":
        clauses.append("q.store_id=?"); params.append(store_id)
    if risk_level and risk_level != "全部":
        clauses.append("q.risk_level=?"); params.append(risk_level)
    if date_from:
        clauses.append("substr(r.created_at,1,10)>=?"); params.append(date_from)
    if date_to:
        clauses.append("substr(r.created_at,1,10)<=?"); params.append(date_to)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT r.review_id,r.query_id,r.review_status,r.review_level,r.priority,r.due_at,r.updated_at,
                       r.created_at,r.reviewed_at,r.review_note,r.corrected_answer,r.escalation_reason,
                       q.store_id,q.user_id,q.question,q.conclusion,q.suggested_script,q.warning,q.source_titles,
                       q.intent,q.risk_level,q.confidence_level,u.name requester,s.store_name,
                       reviewer.name reviewer_name,
                       CASE WHEN r.due_at!='' AND r.due_at<? AND r.review_status IN ('pending_manager','pending_regional','processing_manager','processing_regional') THEN 1 ELSE 0 END overdue
                FROM reviews r JOIN questions q ON q.query_id=r.query_id JOIN users u ON u.user_id=q.user_id
                JOIN stores s ON s.store_id=q.store_id LEFT JOIN users reviewer ON reviewer.user_id=r.reviewer_id
                WHERE {' AND '.join(clauses)}
                ORDER BY overdue DESC,CASE r.review_level WHEN 'regional' THEN 1 ELSE 2 END,
                         CASE q.risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,r.created_at ASC""",
            [utc_now(), *params],
        ).fetchall()
        return [dict(r) for r in rows]


def count_pending_reviews(
    db_path: Path | str = DB_PATH,
    *,
    role: str = "regional_admin",
    user_store: str = "ALL",
    region_id: str = "R-SOUTH",
) -> int:
    return sum(count_pending_by_risk(db_path=db_path, role=role, user_store=user_store, region_id=region_id).values())


def count_pending_by_risk(
    db_path: Path | str = DB_PATH,
    *,
    role: str,
    user_store: str,
    region_id: str = "R-SOUTH",
) -> dict[str, int]:
    scope, params = _review_scope_clause(role, user_store, region_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT q.risk_level,COUNT(*) AS count FROM reviews r
                JOIN questions q ON q.query_id=r.query_id
                JOIN stores s ON s.store_id=q.store_id
                WHERE r.review_status IN ('pending_manager','pending_regional','processing_manager','processing_regional') AND {scope}
                GROUP BY q.risk_level""",
            params,
        ).fetchall()
    result = {"high": 0, "medium": 0, "low": 0}
    result.update({r["risk_level"]: int(r["count"]) for r in rows})
    return result


def get_review(review_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT r.*,q.store_id,q.user_id,q.question,q.risk_level,q.conclusion,q.suggested_script,q.warning,q.source_titles,
                      u.name requester FROM reviews r JOIN questions q ON q.query_id=r.query_id
                      JOIN users u ON u.user_id=q.user_id WHERE r.review_id=?""",
            (review_id,),
        ).fetchone()
        return dict(row) if row else None


def update_review(
    review_id: int,
    review_status: str,
    corrected_answer: str,
    review_note: str,
    reviewer_id: int,
    db_path: Path | str = DB_PATH,
) -> None:
    before = get_review(review_id, db_path)
    if not before:
        raise ValueError("Review not found")
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE reviews SET review_status=?,corrected_answer=?,review_note=?,reviewer_id=?,reviewed_at=?,updated_at=?
               WHERE review_id=?""",
            (review_status, corrected_answer, review_note, reviewer_id, utc_now(), utc_now(), review_id),
        )
    final_text = corrected_answer or before["conclusion"]
    create_notification(
        before["user_id"],
        "review_result",
        "店长已回复" if get_user(reviewer_id, db_path).get("role") == "manager" else "区域运营已回复",
        f"问题：{before['question']}\n回复：{final_text}\n备注：{review_note}",
        before["query_id"],
        db_path,
    )
    audit_log(reviewer_id, "审批工单", "review", str(review_id), before, {"status": review_status, "answer": final_text, "note": review_note}, before["store_id"], db_path)


def escalate_review(
    review_id: int,
    reason: str,
    actor_id: int,
    db_path: Path | str = DB_PATH,
) -> None:
    before = get_review(review_id, db_path)
    if not before:
        raise ValueError("Review not found")
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE reviews SET review_status='pending_regional',review_level='regional',escalation_reason=?,
               escalated_by=?,due_at=? WHERE review_id=?""",
            (reason, actor_id, iso_after(12), review_id),
        )
    for regional in list_users(role="regional_admin", db_path=db_path):
        create_notification(
            regional["user_id"], "escalated_review", "门店工单升级", f"{before['store_id']}：{before['question']}\n原因：{reason}", review_id, db_path
        )
    audit_log(actor_id, "升级工单", "review", str(review_id), before, {"level": "regional", "reason": reason}, before["store_id"], db_path)


def batch_update_reviews(
    review_ids: list[int],
    review_status: str,
    review_note: str,
    reviewer_id: int,
    corrected_answer: str = "",
    db_path: Path | str = DB_PATH,
) -> int:
    count = 0
    for review_id in review_ids:
        item = get_review(review_id, db_path)
        if not item or item["review_status"] not in {"pending_manager", "pending_regional", "processing_manager", "processing_regional"}:
            continue
        update_review(review_id, review_status, corrected_answer or item["conclusion"], review_note, reviewer_id, db_path)
        count += 1
    return count


def list_feedback(
    db_path: Path | str = DB_PATH,
    *,
    status: str | None = None,
    issue_type: str | None = None,
    store_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if status and status != "全部":
        clauses.append("f.processing_status=?")
        params.append(status)
    if issue_type and issue_type != "全部":
        clauses.append("f.issue_type=?")
        params.append(issue_type)
    if store_id and store_id != "ALL":
        clauses.append("q.store_id=?")
        params.append(store_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT f.*,q.query_id,q.store_id,q.user_id,q.question,q.conclusion,q.suggested_script,q.warning,
                       q.intent,q.risk_level,q.created_at AS question_created_at,u.name AS requester,
                       assignee.name AS assignee_name,handler.name AS handled_by_name,
                       CASE WHEN f.due_at!='' AND f.due_at<? AND f.processing_status IN ('待处理','处理中') THEN 1 ELSE 0 END AS overdue,
                       (SELECT COUNT(*) FROM feedback f2 WHERE f2.issue_type=f.issue_type AND f2.created_at>COALESCE(f.handled_at,'9999')) AS same_issue_after
                FROM feedback f JOIN questions q ON q.query_id=f.query_id
                JOIN users u ON u.user_id=q.user_id
                LEFT JOIN users assignee ON assignee.user_id=f.assigned_to
                LEFT JOIN users handler ON handler.user_id=f.handled_by
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE f.processing_status WHEN '待处理' THEN 1 WHEN '处理中' THEN 2 WHEN '已优化' THEN 3 ELSE 4 END,
                         f.created_at DESC""",
            [utc_now(), *params],
        ).fetchall()
        return [dict(r) for r in rows]


ALLOWED_FEEDBACK_TRANSITIONS = {
    "待处理": {"待处理", "处理中", "已关闭"},
    "处理中": {"处理中", "已优化", "已关闭"},
    "已优化": {"已优化", "已关闭", "处理中"},
    "已关闭": {"已关闭", "处理中"},
}


def update_feedback(
    feedback_id: int,
    processing_status: str,
    issue_type: str,
    comment: str = "",
    linked_doc_id: str = "",
    optimized_version: str = "",
    handled_by: int = 2,
    assigned_to: int | None = None,
    resolution_action: str = "",
    linked_entity_type: str = "",
    verification_note: str = "",
    due_at: str = "",
    evidence_path: str = "",
    cluster_key: str = "",
    db_path: Path | str = DB_PATH,
) -> None:
    with connect(db_path) as conn:
        before_row = conn.execute("SELECT * FROM feedback WHERE feedback_id=?", (feedback_id,)).fetchone()
        if not before_row:
            raise ValueError("Feedback not found")
        before = dict(before_row)
        if processing_status not in ALLOWED_FEEDBACK_TRANSITIONS.get(before["processing_status"], set()):
            raise ValueError(f"不允许从{before['processing_status']}流转到{processing_status}")
        handled_at = utc_now() if processing_status in {"已优化", "已关闭"} else before.get("handled_at")
        conn.execute(
            """UPDATE feedback SET processing_status=?,issue_type=?,comment=?,assigned_to=?,resolution_action=?,
               linked_entity_type=?,linked_doc_id=?,optimized_version=?,verification_note=?,handled_by=?,handled_at=?,
               due_at=?,evidence_path=?,cluster_key=?,updated_at=? WHERE feedback_id=?""",
            (processing_status, issue_type, comment, assigned_to, resolution_action, linked_entity_type, linked_doc_id,
             optimized_version, verification_note, handled_by, handled_at, due_at or before.get("due_at") or iso_after(48),
             evidence_path or before.get("evidence_path", ""), cluster_key or before.get("cluster_key", ""), utc_now(), feedback_id),
        )
    audit_log(handled_by, "处理Bad Case", "feedback", str(feedback_id), before, {
        "processing_status": processing_status, "issue_type": issue_type, "assigned_to": assigned_to,
        "resolution_action": resolution_action, "linked_entity_type": linked_entity_type,
        "linked_doc_id": linked_doc_id, "optimized_version": optimized_version,
        "verification_note": verification_note, "due_at": due_at, "cluster_key": cluster_key,
    }, db_path=db_path)

def submit_knowledge_request(
    feedback_id: int | None,
    store_id: str,
    submitted_by: int,
    title: str,
    description: str,
    suggested_content: str = "",
    linked_entity_type: str = "",
    linked_entity_id: str = "",
    db_path: Path | str = DB_PATH,
) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO knowledge_requests(feedback_id,store_id,submitted_by,title,description,suggested_content,
               linked_entity_type,linked_entity_id,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (feedback_id, store_id, submitted_by, title, description, suggested_content, linked_entity_type, linked_entity_id, utc_now(), utc_now()),
        )
        request_id = int(cur.lastrowid)
    for regional in list_users(role="regional_admin", db_path=db_path):
        create_notification(regional["user_id"], "knowledge_request", "知识库优化申请", f"{store_id}：{title}", request_id, db_path)
    audit_log(submitted_by, "提交知识优化申请", "knowledge_request", str(request_id), after={"title": title, "store_id": store_id}, store_id=store_id, db_path=db_path)
    return request_id


def list_knowledge_requests(store_id: str | None = None, status: str | None = None, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if store_id and store_id != "ALL":
        clauses.append("k.store_id=?")
        params.append(store_id)
    if status and status != "全部":
        clauses.append("k.status=?")
        params.append(status)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            f"""SELECT k.*,u.name AS submitter,a.name AS assignee_name FROM knowledge_requests k
                JOIN users u ON u.user_id=k.submitted_by LEFT JOIN users a ON a.user_id=k.assigned_to
                WHERE {' AND '.join(clauses)} ORDER BY k.created_at DESC""", params
        )]


def update_knowledge_request(request_id: int, status: str, assigned_to: int | None, resolution: str, actor_id: int, db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        before = conn.execute("SELECT * FROM knowledge_requests WHERE request_id=?", (request_id,)).fetchone()
        if not before:
            raise ValueError("Request not found")
        conn.execute(
            "UPDATE knowledge_requests SET status=?,assigned_to=?,resolution=?,updated_at=? WHERE request_id=?",
            (status, assigned_to, resolution, utc_now(), request_id),
        )
    audit_log(actor_id, "处理知识优化申请", "knowledge_request", str(request_id), dict(before), {"status": status, "resolution": resolution}, before["store_id"], db_path)


def create_product_request(
    scanned_code: str,
    store_id: str,
    requested_by: int,
    product_name: str = "",
    category: str = "",
    note: str = "",
    photo_path: str = "",
    db_path: Path | str = DB_PATH,
) -> int:
    with connect(db_path) as conn:
        existing = conn.execute(
            """SELECT request_id FROM product_requests WHERE scanned_code=? AND store_id=?
               AND status NOT IN ('已发布','已驳回') ORDER BY request_id DESC LIMIT 1""",
            (scanned_code, store_id),
        ).fetchone()
        if existing:
            return int(existing[0])
        cur = conn.execute(
            """INSERT INTO product_requests(scanned_code,product_name,category,note,photo_path,store_id,requested_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (scanned_code, product_name, category, note, photo_path, store_id, requested_by, utc_now(), utc_now()),
        )
        request_id = int(cur.lastrowid)
    managers = list_users(role="manager", store_id=store_id, db_path=db_path)
    for manager in managers:
        create_notification(manager["user_id"], "new_product", "发现未建档商品", f"扫码：{scanned_code}", request_id, db_path)
    audit_log(requested_by, "提交新品建档", "product_request", str(request_id), after={"scanned_code": scanned_code}, store_id=store_id, db_path=db_path)
    return request_id


def list_product_requests(status: str | None = None, store_id: str | None = None, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if status and status != "全部":
        clauses.append("p.status=?")
        params.append(status)
    if store_id and store_id != "ALL":
        clauses.append("p.store_id=?")
        params.append(store_id)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            f"""SELECT p.*,u.name AS requester,m.name AS manager_name,rr.name AS regional_name,s.store_name
                FROM product_requests p JOIN users u ON u.user_id=p.requested_by
                JOIN stores s ON s.store_id=p.store_id
                LEFT JOIN users m ON m.user_id=p.manager_id
                LEFT JOIN users rr ON rr.user_id=p.regional_reviewer_id
                WHERE {' AND '.join(clauses)} ORDER BY p.created_at DESC""", params
        )]


def update_product_request(request_id: int, actor_id: int, fields: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    allowed = {
        "proposed_product_code", "product_name", "category", "fabric", "fit", "target_customer",
        "customer_tags", "aliases", "selling_points", "styling_tips", "size_notes", "common_objection",
        "suggested_script", "forbidden_claims", "note", "status", "rejection_reason", "manager_id",
        "regional_reviewer_id", "published_at",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    with connect(db_path) as conn:
        before = conn.execute("SELECT * FROM product_requests WHERE request_id=?", (request_id,)).fetchone()
        if not before:
            raise ValueError("Product request not found")
        clean["updated_at"] = utc_now()
        assignments = ",".join(f"{k}=?" for k in clean)
        conn.execute(f"UPDATE product_requests SET {assignments} WHERE request_id=?", [*clean.values(), request_id])
    audit_log(actor_id, "处理新品建档", "product_request", str(request_id), dict(before), clean, before["store_id"], db_path)


def get_product_request(request_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM product_requests WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None


def acknowledge_rules(user_id: int, rules: list[dict], db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO rule_acknowledgements(user_id,doc_id,version,acknowledged_at) VALUES(?,?,?,?)",
            [(user_id, r["doc_id"], r["version"], utc_now()) for r in rules],
        )


def unacknowledged_rules(user_id: int, active_rules: list[dict], db_path: Path | str = DB_PATH) -> list[dict]:
    if not active_rules:
        return []
    with connect(db_path) as conn:
        acknowledged = {(r["doc_id"], r["version"]) for r in conn.execute(
            "SELECT doc_id,version FROM rule_acknowledgements WHERE user_id=?", (user_id,)
        )}
    return [r for r in active_rules if (r["doc_id"], r["version"]) not in acknowledged]


def track_user_session(
    user_id: int,
    store_id: str,
    role: str,
    session_id: str | None = None,
    db_path: Path | str = DB_PATH,
) -> str:
    sid = session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM user_sessions WHERE session_id=?", (sid,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO user_sessions(session_id,user_id,store_id,role,started_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                (sid, user_id, store_id, role, now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")),
            )
        else:
            last = datetime.fromisoformat(row["last_seen_at"])
            delta = max(0, min(300, int((now - last).total_seconds())))
            conn.execute(
                "UPDATE user_sessions SET user_id=?,store_id=?,role=?,last_seen_at=?,active_seconds=active_seconds+? WHERE session_id=?",
                (user_id, store_id, role, now.isoformat(timespec="seconds"), delta, sid),
            )
    return sid


def dashboard_metrics(
    db_path: Path | str = DB_PATH,
    *,
    store_id: str | None = None,
    region_id: str = "R-SOUTH",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    qclauses = ["s.region_id=?"]
    params: list[Any] = [region_id]
    if store_id and store_id != "ALL":
        qclauses.append("q.store_id=?")
        params.append(store_id)
    if date_from:
        qclauses.append("substr(q.created_at,1,10)>=?")
        params.append(date_from)
    if date_to:
        qclauses.append("substr(q.created_at,1,10)<=?")
        params.append(date_to)
    qwhere = " AND ".join(qclauses)
    with connect(db_path) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE {qwhere}", params).fetchone()[0])
        pending = int(conn.execute(
            f"SELECT COUNT(*) FROM reviews r JOIN questions q ON q.query_id=r.query_id JOIN stores s ON s.store_id=q.store_id WHERE r.review_status IN ('pending_manager','pending_regional') AND {qwhere}", params
        ).fetchone()[0])
        high = int(conn.execute(f"SELECT COUNT(*) FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE q.risk_level='high' AND {qwhere}", params).fetchone()[0])
        intercepted = int(conn.execute(f"SELECT COUNT(*) FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE q.risk_level='high' AND q.need_manager_confirmation=1 AND {qwhere}", params).fetchone()[0])
        zero = int(conn.execute(f"SELECT COUNT(*) FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE q.refused=1 AND {qwhere}", params).fetchone()[0])
        helpful, feedback_total = conn.execute(
            f"""SELECT SUM(CASE WHEN f.feedback_type='有帮助' THEN 1 ELSE 0 END),COUNT(*)
                FROM feedback f JOIN questions q ON q.query_id=f.query_id JOIN stores s ON s.store_id=q.store_id WHERE f.feedback_type!='高风险自动入池' AND {qwhere}""", params
        ).fetchone()
        resolved, bad_total = conn.execute(
            f"""SELECT SUM(CASE WHEN f.processing_status IN ('已优化','已关闭') THEN 1 ELSE 0 END),COUNT(*)
                FROM feedback f JOIN questions q ON q.query_id=f.query_id JOIN stores s ON s.store_id=q.store_id WHERE {qwhere}""", params
        ).fetchone()
        associate_scope = "u.role='associate' AND u.status='active' AND u.region_id=?"
        associate_params: list[Any] = [region_id]
        if store_id and store_id != "ALL":
            associate_scope += " AND u.store_id=?"
            associate_params.append(store_id)
        total_associates = int(conn.execute(f"SELECT COUNT(*) FROM users u WHERE {associate_scope}", associate_params).fetchone()[0])
        active_associates = int(conn.execute(
            f"""SELECT COUNT(DISTINCT q.user_id) FROM questions q JOIN users u ON u.user_id=q.user_id JOIN stores s ON s.store_id=q.store_id
                WHERE {qwhere} AND u.role='associate'""", params
        ).fetchone()[0])
        session_scope = ["u.region_id=?", "us.role='associate'"]
        session_params: list[Any] = [region_id]
        if store_id and store_id != "ALL":
            session_scope.append("us.store_id=?")
            session_params.append(store_id)
        if date_from:
            session_scope.append("substr(us.started_at,1,10)>=?")
            session_params.append(date_from)
        if date_to:
            session_scope.append("substr(us.started_at,1,10)<=?")
            session_params.append(date_to)
        avg_session = conn.execute(
            f"""SELECT AVG(active_seconds/60.0) FROM user_sessions us JOIN users u ON u.user_id=us.user_id
                WHERE {' AND '.join(session_scope)}""", session_params
        ).fetchone()[0]
        intents = [dict(r) for r in conn.execute(
            f"SELECT q.intent,COUNT(*) count FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE {qwhere} GROUP BY q.intent ORDER BY count DESC", params
        )]
        intent_by_store = [dict(r) for r in conn.execute(
            f"SELECT q.store_id,q.intent,COUNT(*) count FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE {qwhere} GROUP BY q.store_id,q.intent ORDER BY q.store_id,count DESC", params
        )]
        top_questions = [dict(r) for r in conn.execute(
            f"SELECT q.intent,q.question,COUNT(*) count FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE {qwhere} GROUP BY q.intent,q.question ORDER BY count DESC LIMIT 10", params
        )]
        zero_questions = [dict(r) for r in conn.execute(
            f"SELECT q.intent,q.question,COUNT(*) count FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE q.refused=1 AND {qwhere} GROUP BY q.intent,q.question ORDER BY count DESC LIMIT 10", params
        )]
        risk_trend = [dict(r) for r in conn.execute(
            f"SELECT substr(q.created_at,1,10) day,COUNT(*) count FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE q.risk_level='high' AND {qwhere} GROUP BY day ORDER BY day", params
        )]
        high_by_store = [dict(r) for r in conn.execute(
            f"SELECT q.store_id,COUNT(*) high_risk FROM questions q JOIN stores s ON s.store_id=q.store_id WHERE q.risk_level='high' AND {qwhere} GROUP BY q.store_id ORDER BY high_risk DESC", params
        )]
        high_by_user = [dict(r) for r in conn.execute(
            f"""SELECT u.name,q.store_id,COUNT(*) high_risk FROM questions q JOIN users u ON u.user_id=q.user_id
                JOIN stores s ON s.store_id=q.store_id WHERE q.risk_level='high' AND {qwhere}
                GROUP BY u.name,q.store_id ORDER BY high_risk DESC""", params
        )]
        store_rank = [dict(r) for r in conn.execute(
            """SELECT q.store_id,s.store_name,s.status,COUNT(*) queries,
                      SUM(CASE WHEN q.risk_level='high' THEN 1 ELSE 0 END) high_risk,
                      SUM(CASE WHEN q.refused=1 THEN 1 ELSE 0 END) zero_results,
                      COUNT(DISTINCT q.user_id) active_users
               FROM questions q JOIN stores s ON s.store_id=q.store_id
               WHERE s.region_id=? GROUP BY q.store_id,s.store_name,s.status ORDER BY queries DESC""", (region_id,)
        )]
        helpful_trend_rows = conn.execute(
            f"""SELECT substr(f.created_at,1,10) day,SUM(CASE WHEN f.feedback_type='有帮助' THEN 1 ELSE 0 END) helpful,COUNT(*) total
                FROM feedback f JOIN questions q ON q.query_id=f.query_id JOIN stores s ON s.store_id=q.store_id
                WHERE {qwhere} GROUP BY day ORDER BY day""", params
        ).fetchall()
        complaint_count = int(conn.execute(
            """SELECT COUNT(*) FROM complaint_logs c JOIN stores s ON s.store_id=c.store_id
               WHERE s.region_id=? AND (?='ALL' OR c.store_id=?)""", (region_id, store_id or "ALL", store_id or "ALL")
        ).fetchone()[0])
        event_scope = ["1=1"]
        event_params: list[Any] = []
        if store_id and store_id != "ALL":
            event_scope.append("store_id=?")
            event_params.append(store_id)
        if date_from:
            event_scope.append("substr(created_at,1,10)>=?")
            event_params.append(date_from)
        if date_to:
            event_scope.append("substr(created_at,1,10)<=?")
            event_params.append(date_to)
        event_rows = [dict(r) for r in conn.execute(
            f"SELECT event_type,COUNT(*) count FROM usage_events WHERE {' AND '.join(event_scope)} GROUP BY event_type ORDER BY count DESC",
            event_params,
        )]
        learning_rows = [dict(r) for r in conn.execute(
            f"""SELECT lr.user_id,u.name,lr.store_id,COUNT(*) attempts,SUM(lr.is_correct) correct,
                         ROUND(AVG(lr.is_correct)*100,1) accuracy
                  FROM learning_results lr JOIN users u ON u.user_id=lr.user_id
                  WHERE {('lr.store_id=?' if store_id and store_id != 'ALL' else '1=1')}
                  GROUP BY lr.user_id,u.name,lr.store_id ORDER BY accuracy DESC,attempts DESC""",
            [store_id] if store_id and store_id != "ALL" else [],
        )]
        action_effects = [dict(r) for r in conn.execute(
            """SELECT action,entity_type,entity_id,created_at,actor_name,store_id,after_json
               FROM audit_logs WHERE action IN ('发布规则','更新商品','处理Bad Case') ORDER BY created_at DESC LIMIT 20"""
        )]
        for action in action_effects:
            try:
                after = json.loads(action.get("after_json") or "{}")
            except json.JSONDecodeError:
                after = {}
            intent_filters: list[str] = []
            doc_type = str(after.get("doc_type", ""))
            if "活动" in doc_type:
                intent_filters = ["活动会员"]
            elif "售后" in doc_type:
                intent_filters = ["售后规则", "投诉处理"]
            elif action.get("entity_type") in {"product_catalog", "feedback"}:
                intent_filters = ["商品知识", "搭配话术"] if action.get("entity_type") == "product_catalog" else []
            action_time = datetime.fromisoformat(action["created_at"])
            before_start = (action_time - timedelta(days=7)).isoformat(timespec="seconds")
            after_end = (action_time + timedelta(days=7)).isoformat(timespec="seconds")
            if intent_filters:
                placeholders = ",".join("?" for _ in intent_filters)
                scope_clause = "" if not action.get("store_id") or action["store_id"] == "ALL" else " AND store_id=?"
                scope_params = [] if not scope_clause else [action["store_id"]]
                action["queries_before_7d"] = int(conn.execute(
                    f"SELECT COUNT(*) FROM questions WHERE created_at>=? AND created_at<? AND intent IN ({placeholders}){scope_clause}",
                    [before_start, action["created_at"], *intent_filters, *scope_params],
                ).fetchone()[0])
                action["queries_after_7d"] = int(conn.execute(
                    f"SELECT COUNT(*) FROM questions WHERE created_at>=? AND created_at<=? AND intent IN ({placeholders}){scope_clause}",
                    [action["created_at"], after_end, *intent_filters, *scope_params],
                ).fetchone()[0])
            else:
                action["queries_before_7d"] = None
                action["queries_after_7d"] = None
            action.pop("after_json", None)
    event_map = {row["event_type"]: int(row["count"]) for row in event_rows}
    for row in store_rank:
        queries = int(row.get("queries", 0) or 0)
        high_count = int(row.get("high_risk", 0) or 0)
        zero_count = int(row.get("zero_results", 0) or 0)
        row["人均查询量"] = round(queries / max(1, int(row.get("active_users", 0) or 0)), 2)
        row["高风险占比"] = round(high_count / queries, 3) if queries else 0.0
        row["知识覆盖率"] = round(1 - zero_count / queries, 3) if queries else 0.0
        row["综合得分"] = round(min(100, (row["知识覆盖率"] * 45 + min(1, row["人均查询量"] / 5) * 35 + (1-row["高风险占比"]) * 20) * 100), 1)

    return {
        "total_questions": total,
        "pending_reviews": pending,
        "high_risk_count": high,
        "high_risk_rate": round(high / total, 3) if total else 0.0,
        "zero_result_count": zero,
        "zero_result_rate": round(zero / total, 3) if total else 0.0,
        "helpful_rate": round((helpful or 0) / feedback_total, 3) if feedback_total else None,
        "bad_case_resolution_rate": round((resolved or 0) / bad_total, 3) if bad_total else None,
        "associate_active_rate": round(active_associates / total_associates, 3) if total_associates else 0.0,
        "active_associates": active_associates,
        "total_associates": total_associates,
        "avg_session_minutes": round(float(avg_session or 0), 1),
        "per_user_daily_queries": round(total / max(1, active_associates), 2),
        "complaint_count": complaint_count,
        "intent_counts": intents,
        "intent_by_store": intent_by_store,
        "top_questions": top_questions,
        "zero_questions": zero_questions,
        "risk_trend": risk_trend,
        "high_by_store": high_by_store,
        "high_by_user": high_by_user,
        "store_rank": store_rank,
        "helpful_trend": [
            {"day": r["day"], "helpful_rate": round(r["helpful"] / r["total"], 3) if r["total"] else 0}
            for r in helpful_trend_rows
        ],
        "knowledge_coverage_rate": round(1 - zero / total, 3) if total else 0.0,
        "high_risk_interception_rate": round(intercepted / high, 3) if high else 1.0,
        "usage_events": event_rows,
        "recommendation_uses": event_map.get("连带推荐加入算价", 0),
        "calculator_uses": event_map.get("快捷算价", 0),
        "learning_progress": learning_rows,
        "action_effects": action_effects,
    }


def mark_review_processing(review_id: int, actor_id: int, db_path: Path | str = DB_PATH) -> None:
    before = get_review(review_id, db_path)
    if not before:
        raise ValueError("Review not found")
    actor = get_user(actor_id, db_path) or {}
    status = "processing_regional" if actor.get("role") == "regional_admin" else "processing_manager"
    with connect(db_path) as conn:
        conn.execute("UPDATE reviews SET review_status=?,reviewer_id=?,updated_at=? WHERE review_id=?", (status, actor_id, utc_now(), review_id))
    audit_log(actor_id, "开始处理工单", "review", str(review_id), before, {"status": status}, before.get("store_id", ""), db_path)


def count_open_feedback(role: str, store_id: str, region_id: str = "R-SOUTH", db_path: Path | str = DB_PATH) -> int:
    clauses = ["f.processing_status IN ('待处理','处理中')"]
    params: list[Any] = []
    if role == "manager":
        clauses.append("q.store_id=?")
        params.append(store_id)
    elif role == "regional_admin":
        clauses.append("s.region_id=?")
        params.append(region_id)
    else:
        return 0
    with connect(db_path) as conn:
        return int(conn.execute(
            f"SELECT COUNT(*) FROM feedback f JOIN questions q ON q.query_id=f.query_id JOIN stores s ON s.store_id=q.store_id WHERE {' AND '.join(clauses)}",
            params,
        ).fetchone()[0])


def list_recent_questions(user_id: int, limit: int = 5, db_path: Path | str = DB_PATH) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT question FROM questions WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
        return [str(r[0]) for r in rows]


def track_event(user_id: int | None, store_id: str, event_type: str, entity_type: str = "", entity_id: str = "", metadata: Any = None, db_path: Path | str = DB_PATH) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO usage_events(user_id,store_id,event_type,entity_type,entity_id,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, store_id, event_type, entity_type, str(entity_id), json.dumps(metadata or {}, ensure_ascii=False, default=str), utc_now()),
        )
        return int(cur.lastrowid)


def submit_learning_result(user_id: int, store_id: str, question_key: str, category: str, selected_answer: str, is_correct: bool, db_path: Path | str = DB_PATH) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT OR REPLACE INTO learning_results(user_id,store_id,question_key,category,selected_answer,is_correct,practice_date,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (user_id, store_id, question_key, category, selected_answer, int(is_correct), datetime.now(timezone.utc).date().isoformat(), utc_now()),
        )
        return int(cur.lastrowid)


def learning_progress(store_id: str = "ALL", user_id: int | None = None, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if store_id != "ALL":
        clauses.append("lr.store_id=?")
        params.append(store_id)
    if user_id is not None:
        clauses.append("lr.user_id=?")
        params.append(user_id)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT lr.user_id,u.name,lr.store_id,COUNT(*) attempts,SUM(lr.is_correct) correct,
                       ROUND(AVG(lr.is_correct)*100,1) accuracy,MAX(lr.created_at) last_practice
                FROM learning_results lr JOIN users u ON u.user_id=lr.user_id
                WHERE {' AND '.join(clauses)} GROUP BY lr.user_id,u.name,lr.store_id ORDER BY accuracy DESC,attempts DESC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def record_error(
    source: str,
    message: str,
    details: str = "",
    user_id: int | None = None,
    store_id: str = "",
    db_path: Path | str = DB_PATH,
) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO error_logs(source,message,details,user_id,store_id,created_at) VALUES(?,?,?,?,?,?)",
            (source, message[:500], details[:5000], user_id, store_id, utc_now()),
        )
        return int(cur.lastrowid)


def list_questions_scope(
    role: str,
    user_id: int,
    store_id: str,
    selected_store: str | None = None,
    limit: int = 300,
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if role == "associate":
        clauses.append("q.user_id=?")
        params.append(user_id)
    elif role == "manager":
        clauses.append("q.store_id=?")
        params.append(store_id)
    elif role == "regional_admin" and selected_store and selected_store != "ALL":
        clauses.append("q.store_id=?")
        params.append(selected_store)
    elif role not in {"regional_admin"}:
        clauses.append("1=0")
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT q.*,u.name requester,r.review_status,r.corrected_answer,r.review_note,r.reviewed_at,
                       reviewer.name reviewer_name FROM questions q JOIN users u ON u.user_id=q.user_id
                       LEFT JOIN reviews r ON r.query_id=q.query_id
                       LEFT JOIN users reviewer ON reviewer.user_id=r.reviewer_id
                       WHERE {' AND '.join(clauses)} ORDER BY q.created_at DESC LIMIT ?""", params
        ).fetchall()
        return [dict(r) for r in rows]


def reassign_reviews_to_store_managers(
    review_ids: list[int], actor_id: int, db_path: Path | str = DB_PATH
) -> int:
    count = 0
    for review_id in review_ids:
        before = get_review(review_id, db_path)
        if not before or before["review_status"] not in {"pending_manager", "pending_regional"}:
            continue
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE reviews SET review_status='pending_manager',review_level='manager',escalation_reason='' WHERE review_id=?",
                (review_id,),
            )
        managers = list_users(role="manager", store_id=before["store_id"], db_path=db_path)
        for manager in managers:
            create_notification(manager["user_id"], "review_assignment", "区域运营分配工单", before["question"], review_id, db_path)
        audit_log(actor_id, "分配门店工单", "review", str(review_id), before, {"review_level": "manager"}, before["store_id"], db_path)
        count += 1
    return count
