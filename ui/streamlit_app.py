from __future__ import annotations

import difflib
import html
import hmac
import io
import json
import re
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assistant import RetailAssistant
from app.catalog import (
    BarcodeService,
    PRODUCT_COLUMNS,
    publish_product_request,
    publish_rule,
    save_products,
    save_recommendations,
)
from app.config import DATA_DIR, ensure_demo_runtime_fresh, reset_demo_runtime, settings
from app.db import (
    acknowledge_rules,
    add_feedback,
    batch_update_reviews,
    count_pending_by_risk,
    count_open_feedback,
    create_notification,
    create_product_request,
    escalate_review,
    feedback_exists,
    get_user_by_email,
    init_db,
    iso_after,
    list_audit_logs,
    list_feedback,
    list_knowledge_requests,
    list_notifications,
    list_recent_questions,
    list_pending_reviews,
    list_reviews_scope,
    list_product_requests,
    list_questions_scope,
    list_stores,
    list_users,
    mark_notifications_read,
    mark_review_processing,
    record_error,
    track_event,
    submit_learning_result,
    learning_progress,
    reassign_reviews_to_store_managers,
    submit_knowledge_request,
    track_user_session,
    unacknowledged_rules,
    update_feedback,
    update_knowledge_request,
    update_product_request,
    update_review,
    dashboard_metrics,
)
from app.inventory import InventoryService
from app.logging_utils import get_logger

try:
    from streamlit_mic_recorder import speech_to_text
except Exception:
    speech_to_text = None

try:
    import zxingcpp
except Exception:
    zxingcpp = None

try:
    from pypinyin import lazy_pinyin
except Exception:
    lazy_pinyin = None

logger = get_logger(__name__)

st.set_page_config(page_title="门店智伴", page_icon="🧥", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
    <style>
    :root {--brand:#155eef;--safe:#137333;--warn:#b06000;--danger:#b3261e;--surface:#f7f9fc;}
    .script-card {background:#eef6ff;border:1px solid #b9d9ff;border-radius:14px;padding:18px;margin:6px 0 8px;}
    .script-text {font-size:1.24rem;font-weight:750;line-height:1.75;color:#102a43;}
    .risk-high {background:#fff0f0;border-left:6px solid #d93025;padding:10px;border-radius:8px;}
    .risk-medium {background:#fff8e1;border-left:6px solid #f9ab00;padding:10px;border-radius:8px;}
    .overdue {background:#ffe9e7;border:1px solid #d93025;border-radius:10px;padding:10px;margin-bottom:8px;}
    .urgent {background:#fff8e1;border:1px solid #f9ab00;border-radius:10px;padding:8px;margin-bottom:8px;}
    .stock-pill {display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:.88rem;}
    .stock-ok {background:#e6f4ea;color:#137333}.stock-low {background:#fef7e0;color:#b06000}.stock-out {background:#fce8e6;color:#b3261e}
    .risk-pill {display:inline-block;padding:2px 9px;border-radius:999px;font-weight:700;font-size:.82rem;margin-left:6px;}
    .risk-pill-high {background:#fce8e6;color:#b3261e}.risk-pill-medium {background:#fef7e0;color:#b06000}.risk-pill-low {background:#e6f4ea;color:#137333}
    .new-pill {display:inline-block;padding:2px 8px;border-radius:999px;background:#155eef;color:white;font-weight:700;font-size:.78rem;}
    .highlight {background:#fff3a3;padding:0 2px;border-radius:3px;}
    .empty-guide {border:1px dashed #aac1e8;background:#f7faff;padding:22px;border-radius:14px;text-align:center;}
    .metric-section {background:#f7f9fc;border-radius:16px;padding:10px 12px;margin-bottom:10px;}
    .busy-box input {font-size:1.3rem!important;min-height:58px!important;}
    div[data-testid="stMetricValue"] {font-size:1.55rem;}
    div[data-testid="stSidebar"] .stButton button {width:100%;}
    @media (max-width:768px) {
      .block-container {padding:1rem .55rem 5rem;}
      .script-text {font-size:1.15rem;line-height:1.62;}
      .stButton button {min-height:48px;font-size:1rem;border-radius:12px;}
      h1 {font-size:1.55rem!important;} h2 {font-size:1.25rem!important;}
      [data-testid="column"] {min-width:0!important;}
      div[data-testid="stHorizontalBlock"] {gap:.35rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if ensure_demo_runtime_fresh():
    st.cache_data.clear()
    st.cache_resource.clear()
init_db()


@st.cache_resource
def get_assistant() -> RetailAssistant:
    return RetailAssistant()


@st.cache_resource
def get_inventory_service() -> InventoryService:
    return InventoryService()


@st.cache_resource
def get_barcode_service() -> BarcodeService:
    return BarcodeService()


@st.cache_data(show_spinner=False, ttl=60)
def load_products() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "products.csv", dtype=str).fillna("")


@st.cache_data(show_spinner=False, ttl=60)
def load_recommendations() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "product_recommendations.csv", dtype=str).fillna("")


@st.cache_data(show_spinner=False, ttl=60)
def load_rules() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "knowledge_docs.csv", dtype=str).fillna("")


@st.cache_data(show_spinner=False, ttl=60)
def load_promotions() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "promotions.csv", dtype=str).fillna("")


def refresh_services() -> None:
    load_products.clear()
    load_recommendations.clear()
    load_rules.clear()
    load_promotions.clear()
    get_assistant.clear()
    get_inventory_service.clear()
    get_barcode_service.clear()


def assistant_service() -> RetailAssistant:
    return get_assistant()


def inventory_service() -> InventoryService:
    return get_inventory_service()


def barcode_service() -> BarcodeService:
    return get_barcode_service()


def safe_load(loader, label: str) -> pd.DataFrame:
    skeleton = st.empty()
    skeleton.markdown(
        '<div style="height:64px;border-radius:12px;background:linear-gradient(90deg,#f1f3f6 25%,#e4e8ee 50%,#f1f3f6 75%);background-size:200% 100%;"></div>',
        unsafe_allow_html=True,
    )
    try:
        data = loader()
        return data
    except Exception as exc:
        logger.exception("load %s failed", label)
        record_error("ui.data", f"{label}读取失败", traceback.format_exc(), st.session_state.get("current_user_id"), st.session_state.get("current_store_id", ""))
        st.error("资料读取失败，请稍后重试或联系负责人。")
        return pd.DataFrame()
    finally:
        skeleton.empty()

def active_rule_rows() -> list[dict[str, Any]]:
    docs = safe_load(load_rules, "规则")
    if docs.empty:
        return []
    current = date.fromisoformat(settings.business_date)
    effective = pd.to_datetime(docs["effective_date"], errors="coerce").dt.date
    expiry = pd.to_datetime(docs["expiry_date"], errors="coerce").dt.date
    return docs[(effective <= current) & (expiry >= current)].to_dict(orient="records")


def demo_access_gate() -> None:
    """Optional lightweight gate for a public portfolio demo."""
    if not settings.is_demo or not settings.demo_access_code:
        return
    if st.session_state.get("demo_access_granted"):
        return
    st.title("🧥 门店智伴")
    st.caption("作品演示环境")
    code = st.text_input("访问口令", type="password", placeholder="请输入演示口令")
    if st.button("进入演示", type="primary", width="stretch"):
        if hmac.compare_digest(code.strip(), settings.demo_access_code):
            st.session_state.demo_access_granted = True
            st.rerun()
        else:
            st.error("访问口令不正确。")
    st.stop()


def resolve_signed_in_user(users: list[dict[str, Any]]) -> dict[str, Any]:
    """Use optional OIDC in controlled deployments; default to demo personas."""
    if settings.auth_mode == "oidc":
        try:
            logged_in = bool(st.user.is_logged_in)
        except Exception:
            logged_in = False
        if not logged_in:
            st.title("🧥 门店智伴")
            st.write("请使用授权账号登录。")
            st.button("登录", on_click=st.login, type="primary")
            st.stop()
        email = str(getattr(st.user, "email", "")).strip().lower()
        user = get_user_by_email(email)
        if not user:
            st.error("当前账号未配置门店角色，请联系管理员。")
            st.button("退出登录", on_click=st.logout)
            st.stop()
        st.sidebar.caption(f"已登录：{email}")
        if st.sidebar.button("退出登录", width="stretch"):
            st.logout()
        return user

    user_options = {f"{u['name']}｜{role_name(u['role'])}｜{u['store_id']}": u for u in users}
    selected_label = st.sidebar.selectbox("演示角色", list(user_options))
    return user_options[selected_label]


def render_demo_banner() -> None:
    if not settings.is_demo:
        return
    reset_text = (
        f"数据约每 {settings.demo_reset_minutes} 分钟自动恢复"
        if settings.demo_reset_minutes > 0
        else "数据会在应用重启后恢复"
    )
    st.warning(
        "作品演示环境：商品、库存、价格、门店、经营指标与人员均为模拟数据；"
        f"操作仅写入临时演示空间，{reset_text}，不用于真实交易或经营决策。",
        icon="🧪",
    )


def catalog_write_allowed() -> bool:
    if settings.is_demo and not settings.demo_allow_catalog_writes:
        st.info("公开演示环境已关闭商品、规则和推荐配置的永久写入；其他问答、审批与反馈流程仍可体验。")
        return False
    return True


def role_name(role: str) -> str:
    return {"associate": "导购", "manager": "店长", "regional_admin": "区域运营"}.get(role, role)


def clear_context_state() -> None:
    for key in ["messages", "pending_prompt", "scanned_code", "selected_product_code", "last_voice_text", "unknown_scan_bytes"]:
        st.session_state.pop(key, None)
    st.session_state.messages = []


def require_roles(role: str, allowed: set[str]) -> bool:
    if role not in allowed:
        st.error("无权限访问该页面。")
        return False
    return True


def risk_name(value: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(value, value)


def role_status_name(value: str) -> str:
    return {"active": "营业", "paused": "暂停", "closed": "已关闭"}.get(value, value)


def render_copy_card(text: str, key: str) -> None:
    safe = html.escape(text or "")
    st.markdown("**顾客沟通话术**")
    st.markdown(f'<div class="script-card"><div class="script-text">{safe}</div></div>', unsafe_allow_html=True)
    component_key = re.sub(r"[^a-zA-Z0-9_-]", "-", str(key))[:80]
    components.html(
        f"""<button id="copy-{component_key}" style="width:100%;border:1px solid #a8c7fa;background:white;border-radius:10px;padding:9px;font-weight:700;cursor:pointer">复制话术</button>
        <script>
        const btn=document.getElementById('copy-{component_key}');
        btn.onclick=async()=>{{
          try {{ await navigator.clipboard.writeText({json.dumps(text or '', ensure_ascii=False)}); btn.innerText='已复制'; setTimeout(()=>btn.innerText='复制话术',1400); }}
          catch(e) {{ btn.innerText='请长按话术复制'; }}
        }};
        </script>""",
        height=48,
    )


def browser_notification(title: str, body: str, tag: str = "retail-floor-copilot") -> None:
    components.html(
        f"""<script>
        (async function(){{
          if (!('Notification' in window)) return;
          let permission=Notification.permission;
          if(permission==='default') permission=await Notification.requestPermission();
          if(permission==='granted') new Notification({json.dumps(title, ensure_ascii=False)}, {{body:{json.dumps(body, ensure_ascii=False)}, tag:{json.dumps(tag)}}});
        }})();
        </script>""",
        height=0,
    )


def stock_badge(status: str) -> str:
    css = "stock-ok" if status == "充足" else "stock-low" if status == "紧张" else "stock-out"
    return f'<span class="stock-pill {css}">{status}</span>'


def risk_badge(level: str) -> str:
    return f'<span class="risk-pill risk-pill-{level}">{risk_name(level)}风险</span>'


def highlight_text(text: str, keyword: str) -> str:
    escaped = html.escape(str(text))
    if not keyword:
        return escaped
    pattern = re.compile(re.escape(html.escape(keyword)), re.I)
    return pattern.sub(lambda m: f'<span class="highlight">{m.group(0)}</span>', escaped)


def cart_add(product_code: str) -> None:
    cart = st.session_state.setdefault("price_cart", [])
    if product_code not in cart:
        cart.append(product_code)


def jump_to(page: str) -> None:
    st.session_state["nav_page"] = page
    st.rerun()


def elapsed_hours(timestamp: str) -> float:
    try:
        value = datetime.fromisoformat(timestamp)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - value).total_seconds() / 3600)
    except Exception:
        return 0.0

def render_inventory(product_code: str, store_id: str, compact: bool = False) -> None:
    data = inventory_service().stock_summary(product_code, store_id)
    if not data.get("found"):
        st.caption("暂无库存数据")
        return
    stock_label = "模拟库存" if settings.simulated_inventory else "库存"
    st.markdown(
        f"本店{stock_label}：{stock_badge(data['local_status'])} · 共 **{data['local_total']}** 件 · 更新时间 {data['updated_at']}",
        unsafe_allow_html=True,
    )
    if compact:
        return
    local = data.get("local", [])
    nearby = [x for x in data.get("nearby", []) if x["stock_qty"] > 0]
    if local:
        st.dataframe(pd.DataFrame(local)[["size", "stock_qty", "status", "price", "promo_price"]], width="stretch", hide_index=True)
    if nearby:
        st.caption("附近门店可调库存")
        st.dataframe(pd.DataFrame(nearby[:8])[["store_id", "size", "stock_qty", "transfer_days"]], width="stretch", hide_index=True)


def render_product_card(row: dict[str, Any], store_id: str, compact: bool = False) -> None:
    summary = inventory_service().stock_summary(row["product_code"], store_id)
    status = summary.get("local_status", "断货")
    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        c1.subheader(f"{row['product_name']}｜{row['product_code']}")
        c2.markdown(stock_badge(status), unsafe_allow_html=True)
        render_copy_card(row["suggested_script"], f"product-{row['product_code']}")
        st.error(f"禁语提醒：{row['forbidden_claims']}")
        core1, core2 = st.columns(2)
        core1.markdown(f"**尺码提示**：{row['size_notes']}")
        core2.markdown(f"**库存**：本店 {summary.get('local_total', 0)} 件｜附近可调 {summary.get('nearby_total', 0)} 件")
        if compact:
            return
        with st.expander("查看商品详情、库存与搭配", expanded=False):
            render_inventory(row["product_code"], store_id, compact=False)
            c3, c4 = st.columns(2)
            c3.markdown(f"**面料**：{row['fabric']}")
            c3.markdown(f"**版型**：{row['fit']}")
            c3.markdown(f"**适合人群**：{row['target_customer']}")
            c4.markdown(f"**顾客标签**：{row['customer_tags'].replace('|', ' · ')}")
            c4.markdown(f"**别名**：{row['aliases'].replace('|', '、')}")
            st.markdown(f"**核心卖点**：{row['selling_points']}")
            st.markdown(f"**搭配建议**：{row['styling_tips']}")
            if st.button("加入快捷算价", key=f"product-cart-{row['product_code']}", width="stretch"):
                cart_add(row["product_code"])
                track_event(st.session_state.get("current_user_id"), store_id, "商品卡加入算价", "product", row["product_code"])
                st.toast("已加入快捷算价")

def render_answer(payload, busy_mode: bool = False) -> None:
    if payload.need_manager_confirmation:
        st.warning(f"需店长确认：{payload.manager_reason or '业务风险需人工判断'}")
    elif payload.refused:
        st.warning("当前资料或系统数据不足，未生成确定性答复。")
    elif not busy_mode:
        st.success(f"意图：{payload.intent}｜风险：{risk_name(payload.risk_level)}｜置信度：{payload.confidence_level}")
    render_copy_card(payload.suggested_script, f"answer-{payload.query_id or id(payload)}")
    if payload.warning:
        st.error(f"禁语提醒：{payload.warning}")
    if not busy_mode:
        st.markdown("**核心结论**")
        st.write(payload.conclusion)
        if payload.conditions:
            st.markdown("**适用条件 / 下一步动作**")
            st.write(payload.conditions)
        if payload.sources:
            with st.expander("查看规则与商品依据"):
                for source in payload.sources:
                    st.markdown(f"- **{source.title}**｜{source.section}｜{source.version}｜相关度 {source.score:.3f}")
        if payload.product_code:
            with st.expander("查看库存与商品卡"):
                product = inventory_service().product_row(payload.product_code)
                if product:
                    render_product_card(product, st.session_state.current_store_id, compact=True)
                    if st.button("加入快捷算价", key=f"answer-cart-{payload.query_id}-{payload.product_code}", width="stretch"):
                        cart_add(payload.product_code)
                        track_event(st.session_state.get("current_user_id"), st.session_state.current_store_id, "问答加入算价", "product", payload.product_code)
                        st.toast("已加入快捷算价")
    if payload.query_id:
        submitted = feedback_exists(payload.query_id)
        if submitted:
            st.caption("该问题已经进入反馈或风险闭环。")
        c1, c2, c3 = st.columns(3)
        if c1.button("有帮助", key=f"helpful-{payload.query_id}", disabled=submitted, width="stretch"):
            add_feedback(payload.query_id, "有帮助")
            st.toast("反馈已记录")
            st.rerun()
        if c2.button("答案不准确", key=f"wrong-{payload.query_id}", disabled=submitted, width="stretch"):
            add_feedback(payload.query_id, "答案不准确")
            st.toast("已进入问题闭环")
            st.rerun()
        if c3.button("需要店长处理", key=f"manager-{payload.query_id}", disabled=submitted, width="stretch"):
            add_feedback(payload.query_id, "应交由店长处理")
            st.toast("已记录")
            st.rerun()

def decode_barcode(uploaded) -> str | None:
    if not uploaded or not zxingcpp:
        return None
    try:
        image = Image.open(uploaded).convert("RGB")
        results = zxingcpp.read_barcodes(image)
        return results[0].text.strip() if results else None
    except Exception:
        logger.exception("barcode decode failed")
        return None


def save_scan_photo(uploaded, raw_code: str) -> str:
    if not uploaded:
        return ""
    folder = DATA_DIR / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    safe_code = "".join(ch for ch in raw_code if ch.isalnum() or ch in "-_ ").strip() or "unknown"
    path = folder / f"{safe_code}-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
    path.write_bytes(uploaded.getvalue())
    return str(path.relative_to(ROOT))


def normalized_search_text(text: str) -> str:
    q = text.strip().lower()
    if lazy_pinyin and any("\u4e00" <= ch <= "\u9fff" for ch in q):
        py = lazy_pinyin(q)
        return q + " " + "".join(py) + " " + "".join(x[0] for x in py if x)
    return q


def search_products(products: pd.DataFrame, keyword: str) -> pd.DataFrame:
    if not keyword.strip():
        return products
    q = keyword.lower().strip()
    ranked: list[tuple[float, int]] = []
    for idx, row in products.iterrows():
        code = row["product_code"].lower()
        name = row["product_name"].lower()
        aliases = [x.strip().lower() for x in row["aliases"].split("|") if x.strip()]
        score = 0.0
        if q == code:
            score += 100
        elif q in code:
            score += 70
        if q in name:
            score += 55
        if any(q in alias for alias in aliases):
            score += 50
        if lazy_pinyin:
            for term in [name, *aliases]:
                py = "".join(lazy_pinyin(term))
                initials = "".join(x[0] for x in lazy_pinyin(term) if x)
                if q in py or q in initials:
                    score += 35
        if q in " ".join(row.astype(str).tolist()).lower():
            score += 8
        if score:
            ranked.append((score, idx))
    ranked.sort(reverse=True)
    return products.loc[[idx for _, idx in ranked]] if ranked else products.iloc[0:0]


def recommendation_codes(source_code: str, store_id: str, max_items: int = 6) -> list[tuple[str, str]]:
    products = safe_load(load_products, "商品")
    recs = safe_load(load_recommendations, "推荐")
    if products.empty:
        return []
    source_rows = products[products["product_code"] == source_code]
    if source_rows.empty:
        return []
    source = source_rows.iloc[0]
    fixed = recs[recs["source_code"] == source_code].sort_values("rank")
    result = [(r["target_code"], r["logic"]) for _, r in fixed.iterrows()]
    source_tags = set(source["customer_tags"].split("|"))
    existing = {source_code, *(x[0] for x in result)}
    scored = []
    for _, row in products.iterrows():
        code = row["product_code"]
        if code in existing:
            continue
        overlap = len(source_tags & set(row["customer_tags"].split("|")))
        category_bonus = 2 if row["category"] != source["category"] else 0
        if overlap or category_bonus:
            scored.append((overlap * 2 + category_bonus, code))
    for _, code in sorted(scored, reverse=True):
        result.append((code, "标签动态匹配"))
        if len(result) >= max_items:
            break
    ordered = inventory_service().rank_by_availability([x[0] for x in result], store_id)
    logic_map = dict(result)
    return [(code, logic_map[code]) for code in ordered[:max_items]]


def show_rule_notice(user_id: int) -> None:
    pending = unacknowledged_rules(user_id, active_rule_rows())
    if not pending:
        return
    titles = sorted({r["title"].split("·")[0] for r in pending})
    versions = sorted({r["version"] for r in pending})

    @st.dialog("规则更新提醒")
    def dialog() -> None:
        st.write("以下规则已生效，请阅读后确认：")
        for title in titles:
            st.markdown(f"- {title}")
        st.caption("版本：" + "、".join(versions))
        if st.button("确认已读", type="primary", width="stretch"):
            acknowledge_rules(user_id, pending)
            st.rerun()

    dialog()


def render_notifications(user_id: int) -> None:
    notices = list_notifications(user_id, unread_only=True)
    if not notices:
        return
    with st.container(border=True):
        st.markdown(f"#### 🔔 待查看通知（{len(notices)}）")
        for item in notices[:5]:
            st.info(f"**{item['title']}**\n\n{item['content']}")
        if st.button("全部标记为已读", key="read-all-notifications"):
            mark_notifications_read(user_id)
            st.rerun()


def render_unknown_product(raw_code: str, camera_file, user_id: int, store_id: str) -> None:
    st.warning(f"未找到条码/编码 **{raw_code}** 对应的商品档案。")
    st.caption("系统不会自动生成商品卖点或库存承诺。提交后由店长补充资料，再由区域运营审核发布。")
    with st.form(f"unknown-{raw_code}"):
        c1, c2 = st.columns(2)
        product_name = c1.text_input("商品名称（可暂填吊牌名称）")
        category = c2.selectbox("商品类别", ["未分类", "衬衫", "裤装", "外套", "T恤", "针织", "连衣裙", "裙装", "羽绒服", "其他"])
        note = st.text_area("现场备注", placeholder="例如：新品刚到店、系统尚未同步；顾客正在询问尺码和卖点。")
        submit = st.form_submit_button("提交新品建档", type="primary", width="stretch")
    if submit:
        photo_path = save_scan_photo(camera_file, raw_code) if camera_file else ""
        request_id = create_product_request(raw_code, store_id, user_id, product_name, category, note, photo_path)
        st.success(f"已提交建档申请 #{request_id}，店长可在“新品建档”中补充资料。")


def page_chat(user_id: int, store_id: str, role: str) -> None:
    st.title("导购AI知识助手")
    render_notifications(user_id)
    busy_mode = st.toggle("旺场简洁模式", value=st.session_state.get("busy_mode", False), key="busy_mode")
    if busy_mode:
        st.info("旺场模式仅保留语音/文字提问、顾客话术和禁语提醒。")
    else:
        with st.container(border=True):
            st.markdown("#### 扫码、编码与自然语言查询")
            c1, c2, c3 = st.columns([5, 1, 1])
            merged_input = c1.text_input("查询入口", placeholder="输入商品编码、吊牌条码或问题", label_visibility="collapsed", key="merged_query")
            if c2.button("查询", type="primary", width="stretch", key="merged_query_submit") and merged_input:
                if barcode_service().resolve(merged_input.strip()) or inventory_service().extract_product_code(merged_input.strip()):
                    st.session_state.scanned_code = merged_input.strip()
                else:
                    st.session_state.pending_prompt = merged_input.strip()
            scan_open = c3.toggle("扫码", key="scan_toggle")
            camera = None
            if scan_open:
                if zxingcpp is None:
                    st.info("扫码组件未加载，可手动输入商品编码或条码。")
                else:
                    camera = st.camera_input("扫描吊牌条码/二维码", label_visibility="collapsed")
                    if camera:
                        decoded = decode_barcode(camera)
                        if decoded:
                            st.session_state.scanned_code = decoded
                            st.session_state.unknown_scan_bytes = camera.getvalue()
                            st.success(f"识别结果：{decoded}")
                        else:
                            st.warning("未识别到条码，请调整距离或改用手动输入。")
            raw = st.session_state.get("scanned_code", "")
            if raw:
                resolved = barcode_service().resolve(raw) or inventory_service().extract_product_code(raw)
                if resolved:
                    row = inventory_service().product_row(resolved)
                    if row:
                        render_product_card(row, store_id, compact=False)
                    else:
                        render_unknown_product(raw, camera, user_id, store_id)
                else:
                    render_unknown_product(raw, camera, user_id, store_id)
        quick_questions = ["白衬衫会不会透？", "FS-KZ-001的M码有货吗？", "会员折扣和满减能一起用吗？", "吊牌剪了还能换吗？"]
        st.markdown("#### 常见问题")
        cols = st.columns(len(quick_questions))
        for i, question in enumerate(quick_questions):
            if cols[i].button(question, key=f"quick-{i}", width="stretch"):
                st.session_state.pending_prompt = question
        recent = list_recent_questions(user_id, 5)
        if recent:
            c1, c2 = st.columns([4, 1])
            selected_recent = c1.selectbox("最近查询", ["选择历史问题", *recent], label_visibility="collapsed")
            if c2.button("再次查询", disabled=selected_recent == "选择历史问题", width="stretch"):
                st.session_state.pending_prompt = selected_recent
    # 语音入口固定在输入区上方，避免藏在折叠面板中。
    voice_text = None
    if speech_to_text:
        try:
            voice_text = speech_to_text(language="zh-CN", start_prompt="🎙️ 语音提问", stop_prompt="停止并识别", just_once=True, use_container_width=True, key="voice_front")
            if voice_text and voice_text != st.session_state.get("last_voice_text"):
                st.session_state.last_voice_text = voice_text
                st.session_state.pending_prompt = voice_text
                st.toast(f"已识别：{voice_text}")
        except Exception:
            logger.exception("speech recognition failed")
            st.caption("语音识别暂时不可用，可继续使用文字输入。")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"]) if msg["role"] == "user" else render_answer(msg["content"], busy_mode)
    prompt = st.chat_input("旺场可直接说或输入问题") or st.session_state.pop("pending_prompt", None)
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            try:
                with st.spinner("正在查询商品、库存和当前生效规则..."):
                    payload = assistant_service().answer(prompt, user_id=user_id, store_id=store_id, persist=True)
                render_answer(payload, busy_mode)
                track_event(user_id, store_id, "导购查询", "question", payload.query_id or "", {"intent": payload.intent, "risk": payload.risk_level, "busy_mode": busy_mode})
            except Exception as exc:
                logger.exception("chat render failed")
                record_error("ui.chat", str(exc), traceback.format_exc(), user_id, store_id)
                st.error("系统繁忙，请稍后再试，或联系店长处理。")
                return
        st.session_state.messages.append({"role": "assistant", "content": payload})
        st.rerun()

def page_question_records(user_id: int, role: str, store_id: str) -> None:
    st.title("问答记录")
    selected_store = "ALL"
    if role == "regional_admin":
        stores = list_stores()
        selected_store = st.selectbox("门店", ["ALL", *[x["store_id"] for x in stores]], format_func=lambda x: "全部门店" if x == "ALL" else x)
    if st.button("刷新记录", key="refresh-question-records"):
        st.rerun()
    rows = list_questions_scope(role, user_id, store_id, selected_store)
    if not rows:
        st.markdown('<div class="empty-guide">暂无问答记录，完成一次商品或规则查询后会在这里显示。</div>', unsafe_allow_html=True)
        return
    for item in rows:
        status = item.get("review_status") or "无需审批"
        with st.expander(f"{item['created_at']}｜{item['store_id']}｜{item['requester']}｜{item['question']}"):
            st.markdown(f"**AI话术**：{item['suggested_script']}")
            st.caption(f"意图：{item['intent']}｜风险：{item['risk_level']}｜状态：{status}")
            if item.get("corrected_answer"):
                st.success(f"最终回复：{item['corrected_answer']}")
                if item.get("review_note"):
                    st.info(f"处理备注：{item['review_note']}")
                st.caption(f"处理人：{item.get('reviewer_name') or '-'}｜处理时间：{item.get('reviewed_at') or '-'}")


def page_notifications(user_id: int) -> None:
    st.title("通知中心")
    if st.button("刷新通知", key="refresh-notifications"):
        st.rerun()
    notices = list_notifications(user_id, unread_only=False)
    if not notices:
        st.markdown('<div class="empty-guide">暂无通知。工单处理、规则更新和任务分配结果会在这里显示。</div>', unsafe_allow_html=True)
        return
    unread = [n for n in notices if not n["is_read"]]
    c1, c2 = st.columns([3, 1])
    c1.caption(f"未读 {len(unread)} 条，共 {len(notices)} 条")
    if c2.button("全部标记已读", disabled=not unread, width="stretch"):
        mark_notifications_read(user_id)
        st.rerun()
    for item in notices:
        icon = "🔔" if not item["is_read"] else "✓"
        with st.expander(f"{icon} {item['title']}｜{item['created_at']}"):
            st.write(item["content"])
            if not item["is_read"] and st.button("标记已读", key=f"notice-read-{item['notification_id']}"):
                mark_notifications_read(user_id, [item["notification_id"]])
                st.rerun()


def page_customer_match(store_id: str) -> None:
    st.title("顾客需求匹配")
    products = safe_load(load_products, "商品")
    if products.empty:
        return
    all_tags = sorted({tag for s in products["customer_tags"] for tag in s.split("|") if tag})
    groups = {"身形特征": [], "场景需求": [], "风格偏好": [], "人群属性": []}
    shape_words = ["梨形", "微胖", "假胯", "腿型", "小腿", "腰腹", "身材", "小个子"]
    scene_words = ["通勤", "日常", "约会", "办公室", "秋冬", "休闲", "正装", "外搭"]
    style_words = ["轻熟", "甜酷", "经典", "百搭", "懒人", "温柔", "英伦"]
    for tag in all_tags:
        if any(w in tag for w in shape_words): groups["身形特征"].append(tag)
        elif any(w in tag for w in scene_words): groups["场景需求"].append(tag)
        elif any(w in tag for w in style_words): groups["风格偏好"].append(tag)
        else: groups["人群属性"].append(tag)
    selected = set(st.session_state.get("match_tags", []))
    hot = [x for x in ["梨形身材", "职场女性", "小个子友好", "通勤正装", "经典百搭"] if x in all_tags]
    st.markdown("#### 热门标签")
    cols = st.columns(max(1, len(hot)))
    for i, tag in enumerate(hot):
        if cols[i].button(("✓ " if tag in selected else "") + tag, key=f"hot-tag-{tag}", width="stretch"):
            selected.symmetric_difference_update({tag})
            st.session_state.match_tags = sorted(selected)
            st.rerun()
    for group_name, tags in groups.items():
        chosen = st.multiselect(group_name, tags, default=[t for t in selected if t in tags], key=f"match-{group_name}")
        selected.update(chosen)
        selected.difference_update(set(tags) - set(chosen))
    st.session_state.match_tags = sorted(selected)
    c1, c2 = st.columns([4, 1])
    c1.caption("系统按匹配度、当前门店库存和可调库存排序。")
    if c2.button("一键清空", width="stretch"):
        st.session_state.match_tags = []
        for group_name in groups:
            st.session_state.pop(f"match-{group_name}", None)
        st.rerun()
    if not selected:
        st.markdown('<div class="empty-guide">选择顾客的身形、场景、风格或人群标签后，将优先推荐有货商品。</div>', unsafe_allow_html=True)
        return
    scored = []
    for _, row in products.iterrows():
        overlap = set(row["customer_tags"].split("|")) & selected
        score = len(overlap)
        summary = inventory_service().stock_summary(row["product_code"], store_id)
        local = summary.get("local_total", 0)
        nearby = summary.get("nearby_total", 0)
        if score:
            scored.append((local > 0, local, nearby, score, row.to_dict(), sorted(overlap)))
    for _, local, nearby, score, row, matched in sorted(scored, key=lambda x: (x[0], x[3], x[1], x[2]), reverse=True):
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.subheader(row["product_name"])
            c1.caption(f"匹配标签：{'、'.join(matched)}｜匹配 {score}/{len(selected)}")
            c2.markdown(stock_badge("充足" if local > 3 else "紧张" if local > 0 else "断货"), unsafe_allow_html=True)
            st.write(row["selling_points"])
            if st.button("查看知识卡", key=f"match-view-{row['product_code']}", width="stretch"):
                st.session_state[f"match-open-{row['product_code']}"] = not st.session_state.get(f"match-open-{row['product_code']}", False)
            if st.session_state.get(f"match-open-{row['product_code']}", False):
                render_product_card(row, store_id)

def page_products(store_id: str) -> None:
    st.title("商品知识卡")
    products = safe_load(load_products, "商品")
    c1, c2 = st.columns([4, 1])
    keyword = c1.text_input("搜索商品", placeholder="商品编码、名称、别名、拼音首字母、类别或标签")
    if c2.button("刷新商品", width="stretch"):
        load_products.clear(); get_inventory_service.clear(); st.rerun()
    categories = ["全部", "衬衫", "裤装", "外套", "配饰"]
    category = st.radio("品类快捷筛选", categories, horizontal=True)
    filtered = search_products(products, keyword)
    if category != "全部":
        if category == "裤装": mask = filtered["category"].str.contains("裤", na=False)
        elif category == "外套": mask = filtered["category"].str.contains("外套|西装|风衣|大衣|羽绒", regex=True, na=False)
        elif category == "配饰": mask = filtered["category"].str.contains("配饰|包|鞋|腰带", regex=True, na=False)
        else: mask = filtered["category"].str.contains(category, na=False)
        filtered = filtered[mask]
    st.caption(f"找到 {len(filtered)} 个商品")
    if filtered.empty:
        st.markdown('<div class="empty-guide">没有找到匹配商品，可尝试商品编码、俗称或拼音首字母。</div>', unsafe_allow_html=True)
    for _, row in filtered.iterrows():
        render_product_card(row.to_dict(), store_id)

def page_recommendations(store_id: str) -> None:
    st.title("连带推荐")
    products = safe_load(load_products, "商品")
    options = {f"{r.product_name}｜{r.product_code}": r.product_code for r in products.itertuples()}
    selected = st.selectbox("顾客已选主品", list(options))
    code = options[selected]
    logic_names = {
        "基础品类互补": "上下装互补搭配",
        "场景统一": "同场景成套搭配",
        "季节递进": "同季节叠穿搭配",
        "身形适配": "同身形优化搭配",
        "标签动态匹配": "同风格与同客群搭配",
    }
    source = products[products["product_code"] == code].iloc[0].to_dict()
    st.info(f"围绕「{source['product_name']}」推荐同场景、同风格且优先有货的商品。")
    for rec_code, logic in recommendation_codes(code, store_id):
        row = products[products["product_code"] == rec_code].iloc[0].to_dict()
        summary = inventory_service().stock_summary(rec_code, store_id)
        human_logic = logic_names.get(logic, logic_names["标签动态匹配"])
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.subheader(row["product_name"])
            c1.caption(f"{row['product_code']}｜推荐理由：{human_logic}")
            c2.markdown(stock_badge(summary.get("local_status", "断货")), unsafe_allow_html=True)
            st.write(f"**导购可解释理由**：{row['styling_tips']}")
            render_copy_card(row["suggested_script"], f"rec-{code}-{rec_code}")
            if summary.get("local_total", 0) == 0:
                nearby = [x for x in summary.get("nearby", []) if x.get("stock_qty", 0) > 0]
                if nearby:
                    fastest = min(nearby, key=lambda x: x.get("transfer_days", 99))
                    st.warning(f"本店断货，可从 {fastest['store_id']} 调货，预计 {max(1, fastest['transfer_days'])} 天到店。")
                    st.info("应对话术：“这款本店暂时没有现货，附近门店可以调货，预计几天内到店，我先帮您确认尺码和到货时间。”")
                else:
                    st.error("本店及附近门店均无库存，暂不建议继续主推。")
            if st.button("加入快捷算价", key=f"rec-cart-{code}-{rec_code}", width="stretch"):
                cart_add(rec_code)
                track_event(st.session_state.get("current_user_id"), store_id, "连带推荐加入算价", "product", rec_code, {"source": code, "logic": human_logic})
                st.toast("已加入快捷算价")

def page_price_calculator(store_id: str) -> None:
    st.title("快捷算价")
    products = safe_load(load_products, "商品")
    promos = safe_load(load_promotions, "促销")
    labels = {f"{r.product_name}｜{r.product_code}": r.product_code for r in products.itertuples()}
    reverse = {v: k for k, v in labels.items()}
    cart = [code for code in st.session_state.setdefault("price_cart", []) if code in reverse]
    active_date = date.fromisoformat(settings.business_date)
    promo_eff = pd.to_datetime(promos["effective_date"], errors="coerce").dt.date
    promo_exp = pd.to_datetime(promos["expiry_date"], errors="coerce").dt.date
    active_promos = promos[(promo_eff <= active_date) & (promo_exp >= active_date)].sort_values("priority")
    default_promo_names = active_promos["promotion_name"].tolist()
    c1, c2 = st.columns([5, 1])
    selected_labels = c1.multiselect("选择商品", list(labels), default=[reverse[x] for x in cart], key="calculator_items")
    if c2.button("一键清空", width="stretch"):
        st.session_state.price_cart = []
        st.session_state.pop("calculator_items", None)
        st.rerun()
    st.session_state.price_cart = [labels[x] for x in selected_labels]
    selected_promos = st.multiselect("当前生效活动", active_promos["promotion_name"].tolist(), default=default_promo_names)
    if not selected_labels:
        st.markdown('<div class="empty-guide">选择商品或从商品卡、连带推荐中加入商品，即可开始算价。</div>', unsafe_allow_html=True)
        return
    lines = []
    subtotal = 0.0
    line_prices: dict[str, float] = {}
    for label in selected_labels:
        code = labels[label]
        lookup = inventory_service().lookup(code, store_id)
        item = (lookup.get("local") or lookup.get("nearby") or [{}])[0]
        price = float(item.get("promo_price") or item.get("price") or 0)
        subtotal += price
        line_prices[code] = price
        lines.append({"商品": label, "金额": price, "库存": inventory_service().stock_summary(code, store_id).get("local_status", "断货")})
    payable = subtotal
    details = []
    for _, promo in active_promos[active_promos["promotion_name"].isin(selected_promos)].iterrows():
        excluded = set(str(promo["excluded_codes"]).split("|")) if str(promo["excluded_codes"]).strip() else set()
        eligible = sum(price for code, price in line_prices.items() if code not in excluded)
        amount = 0.0
        if promo["rule_type"] == "threshold":
            threshold = float(promo["threshold"] or 0)
            cut = float(promo["discount"] or 0)
            amount = cut if eligible >= threshold else 0
            details.append({"优惠": promo["promotion_name"], "参与金额": eligible, "优惠金额": -amount, "说明": f"满¥{threshold:.0f}减¥{cut:.0f}" if amount else f"还差¥{max(0, threshold-eligible):.0f}"})
        elif promo["rule_type"] == "rate":
            rate = float(promo["discount_rate"] or 1)
            amount = payable * (1-rate)
            details.append({"优惠": promo["promotion_name"], "参与金额": payable, "优惠金额": -amount, "说明": f"{rate*10:.1f}折"})
        payable = max(0.0, payable - amount)
    st.dataframe(pd.DataFrame(lines), width="stretch", hide_index=True)
    c1, c2, c3 = st.columns(3)
    discount = subtotal - payable
    c1.metric("商品小计", f"¥{subtotal:.2f}")
    c2.metric("优惠合计", f"-¥{discount:.2f}")
    c3.metric("参考实付", f"¥{payable:.2f}")
    if details:
        st.markdown("#### 优惠明细")
        st.dataframe(pd.DataFrame(details), width="stretch", hide_index=True)
    threshold_promos = active_promos[(active_promos["rule_type"] == "threshold") & active_promos["promotion_name"].isin(selected_promos)]
    for _, promo in threshold_promos.iterrows():
        threshold = float(promo["threshold"] or 0)
        excluded = set(str(promo["excluded_codes"]).split("|")) if str(promo["excluded_codes"]).strip() else set()
        eligible = sum(price for code, price in line_prices.items() if code not in excluded)
        gap = threshold - eligible
        if 0 < gap <= 150:
            candidates = []
            for _, row in products.iterrows():
                code = row["product_code"]
                if code in line_prices or code in excluded: continue
                summary = inventory_service().stock_summary(code, store_id)
                if summary.get("local_total", 0) <= 0: continue
                lookup = inventory_service().lookup(code, store_id)
                item = (lookup.get("local") or [{}])[0]
                price = float(item.get("promo_price") or item.get("price") or 0)
                if price > 0: candidates.append((abs(price-gap), price, row.to_dict()))
            if candidates:
                _, price, row = sorted(candidates, key=lambda x: x[0])[0]
                st.info(f"还差 ¥{gap:.0f} 可享满减，建议凑单：{row['product_name']}（参考价 ¥{price:.0f}）。")
                if st.button("加入推荐凑单", key=f"gap-add-{row['product_code']}"):
                    cart_add(row["product_code"]); st.rerun()
    st.warning("⚠️ 此处为活动参考价，最终金额以收银系统、会员账户、券码和商品实时状态核验结果为准。")
    track_event(st.session_state.get("current_user_id"), store_id, "快捷算价", "calculator", "", {"items": list(line_prices), "subtotal": subtotal, "payable": payable, "promotions": selected_promos})

def page_rules(user_id: int, role: str) -> None:
    st.title("规则中心")
    docs = safe_load(load_rules, "规则")
    c1, c2 = st.columns([5, 1])
    q = c1.text_input("全文搜索", placeholder="输入活动、退换货、折扣权限等关键词")
    if c2.button("刷新规则", width="stretch"):
        load_rules.clear(); st.rerun()
    types = st.multiselect("规则类型", sorted(docs["doc_type"].unique()), default=sorted(docs["doc_type"].unique()))
    current_date = date.fromisoformat(settings.business_date)
    effective = pd.to_datetime(docs["effective_date"], errors="coerce").dt.date
    expiry = pd.to_datetime(docs["expiry_date"], errors="coerce").dt.date
    active = docs[(effective <= current_date) & (expiry >= current_date) & docs["doc_type"].isin(types)].copy()
    history = docs[(~((effective <= current_date) & (expiry >= current_date))) & docs["doc_type"].isin(types)].copy()
    if q:
        active = active[active.astype(str).apply(lambda c: c.str.contains(q, case=False, na=False)).any(axis=1)]
        history = history[history.astype(str).apply(lambda c: c.str.contains(q, case=False, na=False)).any(axis=1)]
    unread = {(r["doc_id"], r["version"]) for r in unacknowledged_rules(user_id, active.to_dict(orient="records"))}
    tabs = ["当前生效", "历史版本", "版本对比"] + (["发布规则"] if role == "regional_admin" else [])
    tab_objects = st.tabs(tabs)
    with tab_objects[0]:
        if active.empty:
            st.markdown('<div class="empty-guide">没有匹配的当前生效规则。</div>', unsafe_allow_html=True)
        for _, row in active.sort_values("risk_level", ascending=False).iterrows():
            is_new = (row["doc_id"], row["version"]) in unread
            title_html = f"{html.escape(row['title'])}｜{row['version']} {risk_badge(row['risk_level'])}"
            if is_new: title_html += ' <span class="new-pill">新</span>'
            st.markdown(title_html, unsafe_allow_html=True)
            with st.expander("查看规则正文"):
                st.caption(f"有效期：{row['effective_date']} 至 {row['expiry_date']}｜风险：{risk_name(row['risk_level'])}")
                st.markdown(highlight_text(row["content"], q), unsafe_allow_html=True)
    with tab_objects[1]:
        if history.empty:
            st.info("暂无历史版本。")
        for _, row in history.sort_values(["title", "version"], ascending=False).iterrows():
            with st.expander(f"{row['title']}｜{row['version']}｜{risk_name(row['risk_level'])}风险"):
                st.caption(f"历史有效期：{row['effective_date']} 至 {row['expiry_date']}")
                st.markdown(highlight_text(row["content"], q), unsafe_allow_html=True)
    with tab_objects[2]:
        versionable = [title for title, g in docs.groupby("title") if g["version"].nunique() >= 2]
        if not versionable:
            st.info("暂无可对比的多版本规则。")
        else:
            title = st.selectbox("选择规则", versionable)
            group = docs[docs["title"] == title].sort_values("version")
            versions = list(group["version"].unique())
            c1, c2 = st.columns(2)
            left = c1.selectbox("旧版本", versions, index=0)
            right = c2.selectbox("新版本", versions, index=len(versions)-1)
            old = group[group["version"] == left].iloc[0]["content"].splitlines()
            new = group[group["version"] == right].iloc[0]["content"].splitlines()
            diff = difflib.ndiff(old, new)
            html_lines = []
            for line in diff:
                if line.startswith("+ "): html_lines.append(f'<div style="background:#e6f4ea;padding:4px 8px">新增：{html.escape(line[2:])}</div>')
                elif line.startswith("- "): html_lines.append(f'<div style="background:#fce8e6;padding:4px 8px">删除：{html.escape(line[2:])}</div>')
                elif line.startswith("  "): html_lines.append(f'<div style="padding:4px 8px">{html.escape(line[2:])}</div>')
            st.markdown("".join(html_lines) or "两个版本内容一致", unsafe_allow_html=True)
    if role == "regional_admin":
        with tab_objects[3]:
            with st.form("publish-rule"):
                c1, c2, c3 = st.columns(3)
                title = c1.text_input("规则标题")
                doc_type = c2.selectbox("规则类型", ["活动规则", "售后规则", "销售SOP", "其他"])
                version = c3.text_input("版本", value="V1.2")
                c4, c5, c6 = st.columns(3)
                effective_date = c4.date_input("生效日期", value=date.fromisoformat(settings.business_date))
                expiry_date = c5.date_input("失效日期", value=date.fromisoformat(settings.business_date) + timedelta(days=365))
                risk = c6.selectbox("风险等级", ["低", "中", "高"])
                keywords = st.text_input("关键词")
                source_section = st.text_input("来源章节")
                content = st.text_area("规则正文", height=280)
                publish = st.form_submit_button("发布并推送已读提醒", type="primary", width="stretch")
            if publish:
                if not catalog_write_allowed():
                    return
                if not title or not content:
                    st.error("规则标题和正文不能为空。")
                else:
                    publish_rule({"title": title, "doc_type": doc_type, "version": version, "effective_date": effective_date.isoformat(), "expiry_date": expiry_date.isoformat(), "store_scope": "ALL", "risk_level": {"低":"low","中":"medium","高":"high"}[risk], "source_section": source_section, "keywords": keywords, "content": content}, user_id)
                    refresh_services(); st.success("规则已发布并推送已读提醒。"); st.rerun()

def review_status_label(status: str) -> str:
    return {
        "pending_manager": "待店长处理", "pending_regional": "待区域运营处理",
        "processing_manager": "店长处理中", "processing_regional": "区域运营处理中",
        "confirmed": "已确认", "corrected": "已修改回复", "rejected": "已驳回/转线下",
    }.get(status, status)

def page_reviews(user_id: int, role: str, user_store: str) -> None:
    if not require_roles(role, {"manager", "regional_admin"}):
        return
    st.title("高风险问题确认" if role == "manager" else "区域工单中心")
    counts = count_pending_by_risk(role=role, user_store=user_store)
    st.markdown(f"🔴 **高风险 {counts['high']}**　🟡 **中风险 {counts['medium']}**　🟢 **低风险 {counts['low']}**")
    if st.button("刷新工单", key="refresh-reviews"):
        st.rerun()
    stores = list_stores()
    c1, c2, c3, c4 = st.columns(4)
    risk_cn = c1.selectbox("风险等级", ["全部", "高", "中", "低"])
    risk_filter = {"全部":"全部","高":"high","中":"medium","低":"low"}[risk_cn]
    if role == "regional_admin":
        store_filter = c2.selectbox("门店", ["ALL", *[s["store_id"] for s in stores]], format_func=lambda x: "全部门店" if x == "ALL" else next((f"{s['store_id']}｜{s['store_name']}｜{role_status_name(s['status'])}" for s in stores if s['store_id']==x), x))
    else:
        store_filter = user_store
        c2.text_input("门店", value=user_store, disabled=True)
    state_group = c3.selectbox("处理状态", ["待处理", "处理中", "已完成", "已驳回", "全部"])
    day_filter = c4.selectbox("提交时间", ["全部", "今天", "近7天", "近30天"])
    date_from = date_to = None
    if day_filter == "今天": date_from = date_to = settings.business_date
    elif day_filter == "近7天": date_to = settings.business_date; date_from = (date.fromisoformat(settings.business_date)-timedelta(days=6)).isoformat()
    elif day_filter == "近30天": date_to = settings.business_date; date_from = (date.fromisoformat(settings.business_date)-timedelta(days=29)).isoformat()
    rows = list_reviews_scope(role=role, user_store=user_store, store_id=store_filter, risk_level=risk_filter, state_group=state_group, date_from=date_from, date_to=date_to)
    if not rows:
        st.markdown('<div class="empty-guide">当前筛选条件下没有工单。</div>', unsafe_allow_html=True)
        return
    unresolved = [x for x in rows if x["review_status"] in {"pending_manager","pending_regional","processing_manager","processing_regional"}]
    if unresolved:
        ids = [x["review_id"] for x in unresolved]
        high_ids = [x["review_id"] for x in unresolved if x["risk_level"] == "high"]
        s1, s2 = st.columns(2)
        select_all = s1.checkbox("全选当前页")
        select_high = s2.checkbox("全选高风险")
        default_ids = ids if select_all else high_ids if select_high else []
        selected_ids = st.multiselect("批量选择", ids, default=default_ids, placeholder="选择需要批量处理的工单")
        templates = {
            "按售后规则正常办理": "已核对当前生效的售后规则，请按规则正常办理，并向顾客说明适用条件。",
            "请引导顾客到店核实后处理": "请引导顾客携带商品和购买凭证到店，由负责人核验后处理。",
            "不同意特殊退换，请安抚顾客": "当前情况不符合特殊退换条件，请先共情说明并按规则提供可行替代方案。",
            "同意特殊处理，仅限本次": "经负责人确认，同意本次特殊处理；仅适用于当前订单，不作为常规政策。",
            "自定义": "",
        }
        with st.form("batch-review"):
            c1, c2 = st.columns(2)
            template = c1.selectbox("批量批复模板", list(templates))
            action_options = ["确认回复", "转线下处理"] + (["分派对应门店店长"] if role == "regional_admin" else [])
            action = c2.selectbox("批量处理方式", action_options)
            batch_note = st.text_area("统一备注", value=templates[template])
            confirm_batch = st.checkbox(f"确认对选中的 {len(selected_ids)} 条工单执行以上操作")
            do_batch = st.form_submit_button("执行批量处理", disabled=not selected_ids, type="primary", width="stretch", help="请先在上方选择待处理工单")
        if do_batch:
            if not confirm_batch:
                st.error("请勾选二次确认。")
            elif action == "分派对应门店店长":
                processed = reassign_reviews_to_store_managers(selected_ids, user_id); st.success(f"已分派 {processed} 条工单。"); st.rerun()
            else:
                status = "confirmed" if action == "确认回复" else "rejected"
                processed = batch_update_reviews(selected_ids, status, batch_note, user_id); st.success(f"已处理 {processed} 条工单。"); st.rerun()
    grouped = {}
    for item in rows:
        grouped.setdefault(item["store_id"], []).append(item)
    groups_to_render = grouped.items() if role == "regional_admin" and store_filter == "ALL" else [(store_filter, rows)]
    for group_store, items in groups_to_render:
        if role == "regional_admin" and store_filter == "ALL":
            store_name = items[0].get("store_name", group_store)
            st.markdown(f"### {group_store}｜{store_name}（{len(items)}）")
        for item in items:
            hours = elapsed_hours(item["created_at"])
            overdue = bool(item.get("overdue"))
            urgent = not overdue and hours >= 2 and item["review_status"] in {"pending_manager","pending_regional","processing_manager","processing_regional"}
            if overdue:
                st.markdown(f'<div class="overdue">⏰ 工单 #{item["review_id"]} 已超过24小时，请立即处理。</div>', unsafe_allow_html=True)
            elif urgent:
                st.markdown(f'<div class="urgent">⚠️ 工单 #{item["review_id"]} 已等待 {hours:.1f} 小时，建议加急。</div>', unsafe_allow_html=True)
            escalation = "｜升级工单" if item.get("review_level") == "regional" else ""
            label = f"#{item['review_id']}｜{risk_name(item['risk_level'])}风险{escalation}｜{item['requester']}｜{item['question']}"
            with st.expander(label):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("提问导购", item["requester"])
                c2.metric("所属门店", item["store_id"])
                c3.metric("已等待", f"{hours:.1f}h")
                c4.metric("状态", review_status_label(item["review_status"]))
                st.caption(f"提交时间：{item['created_at']}｜处理时限：{item['due_at']}｜置信度：{item['confidence_level']}")
                if item.get("escalation_reason"): st.warning(f"升级原因：{item['escalation_reason']}")
                st.markdown(f"**AI参考结论**：{item['conclusion']}")
                render_copy_card(item["suggested_script"], f"review-{item['review_id']}")
                st.error(f"风险依据：{item['warning']}")
                if item.get("source_titles"): st.info(f"对应规则依据：{item['source_titles']}")
                if item["review_status"] in {"confirmed","corrected","rejected"}:
                    st.success(f"最终处理：{item.get('corrected_answer') or '-'}")
                    st.caption(f"处理人：{item.get('reviewer_name') or '-'}｜处理时间：{item.get('reviewed_at') or '-'}｜备注：{item.get('review_note') or '-'}")
                    continue
                corrected = st.text_area("审批回复", value=item["suggested_script"], key=f"correct-{item['review_id']}")
                note = st.text_area("处理备注", placeholder="例如：已核验订单；该顾客为VIP；仅限本次特殊处理。", key=f"note-{item['review_id']}")
                if item["review_status"].startswith("pending") and st.button("标记为处理中", key=f"processing-{item['review_id']}"):
                    mark_review_processing(item["review_id"], user_id); st.rerun()
                buttons = st.columns(4 if role == "manager" else 3)
                if buttons[0].button("确认回复", key=f"confirm-{item['review_id']}", width="stretch"):
                    update_review(item["review_id"], "confirmed", corrected, note, user_id); st.rerun()
                if buttons[1].button("修改后回复", key=f"corrected-{item['review_id']}", width="stretch"):
                    update_review(item["review_id"], "corrected", corrected, note, user_id); st.rerun()
                if buttons[2].button("转线下处理", key=f"offline-{item['review_id']}", width="stretch"):
                    update_review(item["review_id"], "rejected", "请由负责人线下核验处理。", note, user_id); st.rerun()
                if role == "manager":
                    reason = st.text_input("升级区域运营原因", key=f"escalate-reason-{item['review_id']}")
                    if buttons[3].button("升级区域运营", key=f"escalate-{item['review_id']}", width="stretch"):
                        if not reason: st.error("请填写升级原因。")
                        else: escalate_review(item["review_id"], reason, user_id); st.rerun()

def page_bad_cases(user_id: int, role: str, store_id: str) -> None:
    if not require_roles(role, {"manager", "regional_admin"}):
        return
    st.title("Bad Case闭环")
    issue_types = ["未分类", "知识库缺失", "答案错误", "边界模糊", "话术不准", "来源不匹配", "规则过期", "诱导违规", "系统错误"]
    statuses = ["待处理", "处理中", "已优化", "已关闭"]
    tabs = st.tabs(["问题闭环", "知识优化申请"])
    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        status_filter = c1.selectbox("处理状态", ["全部", *statuses])
        issue_filter = c2.selectbox("问题类型", ["全部", *issue_types])
        if role == "regional_admin":
            store_filter = c3.selectbox("门店", ["ALL", *[x["store_id"] for x in list_stores()]], format_func=lambda x: "全部门店" if x == "ALL" else x)
        else:
            store_filter = store_id; c3.text_input("门店", value=store_id, disabled=True)
        overdue_only = c4.toggle("仅看超时")
        if st.button("刷新反馈", key="refresh-badcase"):
            st.rerun()
        items = list_feedback(status=status_filter, issue_type=issue_filter, store_id=store_filter)
        if overdue_only: items = [x for x in items if x.get("overdue")]
        if not items:
            st.markdown('<div class="empty-guide"><b>暂无反馈记录</b><br>导购在问答页点击“答案不准确”或高风险问题触发后，将自动进入此处。</div>', unsafe_allow_html=True)
        else:
            summary_rows = [{"问题摘要": x["question"][:30], "门店": x["store_id"], "导购": x["requester"], "问题类型": x["issue_type"], "提交时间": x["created_at"], "处理状态": x["processing_status"], "责任人": x.get("assignee_name") or "未分配", "是否超时": "是" if x.get("overdue") else "否"} for x in items]
            st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)
            cluster_rows = []
            for x in items:
                q = x["question"]
                scene = next((k for k in ["起球", "退换", "退款", "折扣", "活动", "库存", "尺码", "洗涤", "客诉", "显瘦", "掉色"] if k in q), x.get("cluster_key") or "其他")
                cluster_rows.append({"同类场景": scene, "问题类型": x["issue_type"], "数量": 1})
            clustered = pd.DataFrame(cluster_rows).groupby(["同类场景", "问题类型"], as_index=False)["数量"].sum().sort_values("数量", ascending=False)
            st.markdown("#### 同类问题聚合")
            st.dataframe(clustered, width="stretch", hide_index=True)
        for item in items:
            title = f"#{item['feedback_id']}｜{item['processing_status']}｜{item['store_id']}｜{item['question']}"
            if item.get("overdue"): title = "⏰ 超时｜" + title
            with st.expander(title):
                if item.get("overdue"):
                    st.error(f"该问题已超过处理时限（{item.get('due_at') or '-'}），请优先处理。")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("提交门店", item["store_id"])
                c2.metric("提交导购", item["requester"])
                c3.metric("问题类型", item["issue_type"])
                c4.metric("责任人", item.get("assignee_name") or "未分配")
                st.caption(f"问题时间：{item['question_created_at']}｜反馈时间：{item['created_at']}｜处理时限：{item.get('due_at') or '-'}")
                st.markdown(f"**原始提问**：{item['question']}")
                st.markdown(f"**AI原结论**：{item['conclusion']}")
                st.markdown(f"**AI原话术**：{item['suggested_script']}")
                st.markdown(f"**导购反馈**：{item['comment'] or item['feedback_type']}")
                if item.get("evidence_path"):
                    evidence_file = ROOT / item["evidence_path"]
                    if evidence_file.exists(): st.image(str(evidence_file), caption="提交凭证", width=320)
                c1, c2, c3 = st.columns(3)
                allowed_statuses = statuses if role == "regional_admin" else ["待处理", "处理中", "已关闭"]
                current_status = item["processing_status"] if item["processing_status"] in allowed_statuses else "处理中"
                status = c1.selectbox("状态", allowed_statuses, index=allowed_statuses.index(current_status), key=f"bc-status-{item['feedback_id']}")
                issue = c2.selectbox("问题类型", issue_types, index=issue_types.index(item["issue_type"] if item["issue_type"] in issue_types else "未分类"), key=f"bc-issue-{item['feedback_id']}")
                eligible_users = list_users() if role == "regional_admin" else [u for u in list_users(store_id=store_id) if u["role"] == "manager"]
                options = {"未分配": None, **{f"{u['name']}｜{role_name(u['role'])}": u["user_id"] for u in eligible_users if u["role"] in {"manager", "regional_admin"}}}
                current_assignee = next((k for k, v in options.items() if v == item.get("assigned_to")), "未分配")
                assigned_label = c3.selectbox("责任人", list(options), index=list(options).index(current_assignee), key=f"bc-assignee-{item['feedback_id']}")
                c4, c5 = st.columns(2)
                default_due = date.fromisoformat((item.get("due_at") or iso_after(48))[:10])
                due_date = c4.date_input("处理时限", value=default_due, key=f"bc-due-{item['feedback_id']}")
                cluster_key = c5.text_input("同类问题标签", value=item.get("cluster_key") or "", placeholder="例如：起球判定", key=f"bc-cluster-{item['feedback_id']}")
                evidence = st.file_uploader("补充凭证（图片）", type=["png","jpg","jpeg"], key=f"bc-evidence-{item['feedback_id']}")
                resolution = st.text_area("优化动作记录", value=item.get("resolution_action", ""), placeholder="例如：补充退换货规则第4条；新增吊牌已剪场景话术。", key=f"bc-resolution-{item['feedback_id']}")
                c6, c7, c8 = st.columns(3)
                entity_options = ["", "规则", "商品卡", "话术", "系统"]
                entity_type = c6.selectbox("关联对象", entity_options, index=entity_options.index(item.get("linked_entity_type", "") if item.get("linked_entity_type", "") in entity_options else ""), key=f"bc-entity-{item['feedback_id']}")
                linked_id = c7.text_input("关联规则/商品ID", value=item.get("linked_doc_id", ""), key=f"bc-doc-{item['feedback_id']}")
                version = c8.text_input("优化版本", value=item.get("optimized_version", ""), key=f"bc-ver-{item['feedback_id']}")
                verification = st.text_area("效果验证", value=item.get("verification_note", ""), placeholder="记录复测问题、结果及后续同类问题是否再次出现。", key=f"bc-verify-{item['feedback_id']}")
                st.caption(f"优化后再次出现的同类型反馈：{item.get('same_issue_after', 0)} 条。")
                epath = item.get("evidence_path", "")
                if evidence:
                    folder = DATA_DIR / "uploads"; folder.mkdir(parents=True, exist_ok=True)
                    target = folder / f"badcase-{item['feedback_id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}.{evidence.name.split('.')[-1]}"
                    target.write_bytes(evidence.getvalue()); epath = str(target.relative_to(ROOT))
                action_cols = st.columns(3)
                if action_cols[0].button("保存处理结果", key=f"bc-save-{item['feedback_id']}", type="primary", width="stretch"):
                    update_feedback(item["feedback_id"], status, issue, item["comment"], linked_id, version, user_id, assigned_to=options[assigned_label], resolution_action=resolution, linked_entity_type=entity_type, verification_note=verification, due_at=due_date.isoformat()+"T23:59:59+00:00", evidence_path=epath, cluster_key=cluster_key)
                    st.rerun()
                if entity_type == "规则" and action_cols[1].button("进入规则中心", key=f"bc-rule-{item['feedback_id']}", width="stretch"):
                    jump_to("规则中心")
                if entity_type == "商品卡" and role == "regional_admin" and action_cols[2].button("进入商品维护", key=f"bc-product-{item['feedback_id']}", width="stretch"):
                    jump_to("商品与推荐配置")
                if role == "manager":
                    with st.form(f"knowledge-request-{item['feedback_id']}"):
                        kr_title = st.text_input("知识库优化申请标题", value=f"{issue}：{item['question']}")
                        kr_desc = st.text_area("问题说明", value=resolution or item["comment"])
                        kr_suggestion = st.text_area("建议口径/规则")
                        send = st.form_submit_button("提交区域运营")
                    if send:
                        submit_knowledge_request(item["feedback_id"], store_id, user_id, kr_title, kr_desc, kr_suggestion, entity_type, linked_id)
                        st.success("已提交区域运营。")
    with tabs[1]:
        requests = list_knowledge_requests(store_id="ALL" if role == "regional_admin" else store_id)
        if not requests:
            st.markdown('<div class="empty-guide">暂无知识优化申请。门店店长可从Bad Case详情提交规则或商品知识优化建议。</div>', unsafe_allow_html=True)
        regional_users = [u for u in list_users() if u["role"] in {"manager", "regional_admin"}]
        for item in requests:
            with st.expander(f"#{item['request_id']}｜{item['status']}｜{item['store_id']}｜{item['title']}"):
                st.write(item["description"])
                if item["suggested_content"]: st.info(item["suggested_content"])
                st.caption(f"提交人：{item['submitter']}｜关联：{item['linked_entity_type']} {item['linked_entity_id']}")
                if role == "regional_admin":
                    c1, c2 = st.columns(2)
                    state_options = ["待运营处理", "处理中", "已完成", "已驳回"]
                    status = c1.selectbox("状态", state_options, index=state_options.index(item["status"]), key=f"kr-status-{item['request_id']}")
                    assignee_options = {"未分配": None, **{u["name"]: u["user_id"] for u in regional_users}}
                    assignee = c2.selectbox("处理人", list(assignee_options), key=f"kr-assignee-{item['request_id']}")
                    resolution = st.text_area("处理结果", value=item["resolution"], key=f"kr-resolution-{item['request_id']}")
                    if st.button("保存", key=f"kr-save-{item['request_id']}"):
                        update_knowledge_request(item["request_id"], status, assignee_options[assignee], resolution, user_id); st.rerun()

def make_dashboard_excel(metrics: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary = pd.DataFrame([{
            "累计提问": metrics["total_questions"], "导购活跃率": metrics["associate_active_rate"],
            "平均使用时长(分钟)": metrics["avg_session_minutes"], "高风险占比": metrics["high_risk_rate"],
            "知识库覆盖率": metrics.get("knowledge_coverage_rate", 0), "高风险拦截率": metrics.get("high_risk_interception_rate", 0),
            "零结果率": metrics["zero_result_rate"], "Bad Case解决率": metrics["bad_case_resolution_rate"],
            "答案有帮助率": metrics["helpful_rate"], "连带推荐加入算价": metrics.get("recommendation_uses", 0),
            "快捷算价使用次数": metrics.get("calculator_uses", 0), "客诉记录": metrics["complaint_count"],
        }])
        summary.to_excel(writer, sheet_name="核心指标", index=False)
        for key, title in [
            ("intent_counts", "意图分布"), ("intent_by_store", "门店意图对比"), ("top_questions", "高频问题"),
            ("zero_questions", "零结果问题"), ("high_by_store", "门店高风险"), ("high_by_user", "导购高风险"),
            ("store_rank", "门店排行"), ("action_effects", "运营动作"), ("usage_events", "功能使用"),
            ("learning_progress", "导购成长"),
        ]:
            pd.DataFrame(metrics.get(key, [])).to_excel(writer, sheet_name=title, index=False)
    return buffer.getvalue()

def make_dashboard_png(metrics: dict[str, Any], title: str) -> bytes:
    image = Image.new("RGB", (1400, 920), "white")
    draw = ImageDraw.Draw(image)
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)
    except Exception:
        font_big = font = ImageFont.load_default()
    draw.text((60, 45), title, fill="black", font=font_big)
    bad_case_resolution_rate = metrics.get("bad_case_resolution_rate")
    bad_case_resolution_text = (
        "暂无"
        if bad_case_resolution_rate is None
        else f"{bad_case_resolution_rate:.1%}"
    )
    lines = [
        f"累计提问: {metrics['total_questions']}",
        f"导购活跃率: {metrics['associate_active_rate']:.1%}",
        f"知识库覆盖率: {metrics.get('knowledge_coverage_rate', 0):.1%}",
        f"高风险拦截率: {metrics.get('high_risk_interception_rate', 0):.1%}",
        f"平均使用时长: {metrics['avg_session_minutes']} 分钟",
        f"高风险占比: {metrics['high_risk_rate']:.1%}",
        f"Bad Case解决率: {bad_case_resolution_text}",
        f"待确认工单: {metrics['pending_reviews']}",
    ]
    y = 135
    for line in lines:
        draw.text((80, y), line, fill="black", font=font); y += 78
    buffer = io.BytesIO(); image.save(buffer, format="PNG"); return buffer.getvalue()

def page_dashboard(role: str, store_id: str) -> None:
    if not require_roles(role, {"manager", "regional_admin"}):
        return
    st.title("门店数据看板" if role == "manager" else "区域运营看板")
    stores = list_stores()
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        if role == "regional_admin":
            selected_store = c1.selectbox("门店", ["ALL", *[s["store_id"] for s in stores]], format_func=lambda x: "全部门店" if x == "ALL" else next((f"{s['store_id']}｜{s['store_name']}｜{role_status_name(s['status'])}" for s in stores if s['store_id']==x), x))
        else:
            selected_store = store_id; c1.text_input("门店", value=store_id, disabled=True)
        date_from = c2.date_input("开始日期", value=date.fromisoformat(settings.business_date)-timedelta(days=30))
        date_to = c3.date_input("结束日期", value=date.fromisoformat(settings.business_date))
        if c4.button("刷新数据", width="stretch"):
            st.rerun()
    metrics = dashboard_metrics(store_id=selected_store, date_from=date_from.isoformat(), date_to=date_to.isoformat())
    period_days = max(1, (date_to-date_from).days+1)
    prev_to = date_from-timedelta(days=1); prev_from = prev_to-timedelta(days=period_days-1)
    previous = dashboard_metrics(store_id=selected_store, date_from=prev_from.isoformat(), date_to=prev_to.isoformat())
    def delta_num(current, prior, pct=False):
        if prior in (None, 0): return None
        diff = current-prior
        return f"{diff:+.1%}" if pct else f"{diff:+.1f}" if isinstance(diff,float) else f"{diff:+d}"
    st.markdown('<div class="metric-section">', unsafe_allow_html=True)
    row1 = st.columns(6)
    row1[0].metric("累计提问", metrics["total_questions"], delta_num(metrics["total_questions"], previous["total_questions"]))
    row1[1].metric("导购活跃率", f"{metrics['associate_active_rate']:.0%}", delta_num(metrics["associate_active_rate"], previous["associate_active_rate"], True))
    row1[2].metric("知识库覆盖率", f"{metrics.get('knowledge_coverage_rate',0):.0%}", delta_num(metrics.get("knowledge_coverage_rate",0), previous.get("knowledge_coverage_rate",0), True))
    row1[3].metric("高风险拦截率", f"{metrics.get('high_risk_interception_rate',0):.0%}", delta_num(metrics.get("high_risk_interception_rate",0), previous.get("high_risk_interception_rate",0), True))
    row1[4].metric("待确认工单", metrics["pending_reviews"])
    row1[5].metric("人均查询", metrics["per_user_daily_queries"], delta_num(metrics["per_user_daily_queries"], previous["per_user_daily_queries"]))
    row2 = st.columns(6)
    row2[0].metric("平均使用时长", f"{metrics['avg_session_minutes']} 分钟")
    row2[1].metric("高风险占比", f"{metrics['high_risk_rate']:.0%}")
    row2[2].metric("零结果率", f"{metrics['zero_result_rate']:.0%}")
    row2[3].metric("Bad Case解决率", "暂无" if metrics["bad_case_resolution_rate"] is None else f"{metrics['bad_case_resolution_rate']:.0%}")
    row2[4].metric("有帮助率", "暂无" if metrics["helpful_rate"] is None else f"{metrics['helpful_rate']:.0%}")
    row2[5].metric("算价/推荐使用", f"{metrics.get('calculator_uses',0)}/{metrics.get('recommendation_uses',0)}")
    st.markdown('</div>', unsafe_allow_html=True)
    if role == "manager":
        regional = dashboard_metrics(store_id="ALL", date_from=date_from.isoformat(), date_to=date_to.isoformat())
        st.info(f"区域平均：活跃率 {regional['associate_active_rate']:.0%}｜知识覆盖率 {regional.get('knowledge_coverage_rate',0):.0%}｜高风险占比 {regional['high_risk_rate']:.0%}")
    left, right = st.columns(2)
    with left:
        st.subheader("问题意图分布")
        if metrics["intent_counts"]:
            intent_df = pd.DataFrame(metrics["intent_counts"]).rename(columns={"intent":"问题类型","count":"数量"})
            st.dataframe(intent_df, width="stretch", hide_index=True)
            st.bar_chart(intent_df.set_index("问题类型"))
        st.subheader("高频问题Top10")
        top_df = pd.DataFrame(metrics["top_questions"])
        if top_df.empty: st.info("暂无高频问题。")
        else:
            top_df = top_df.rename(columns={"intent":"问题类型","question":"问题","count":"次数"})
            st.dataframe(top_df, width="stretch", hide_index=True)
            selected_top = st.selectbox("选择需要发起优化的问题", top_df["问题"].tolist(), key="dashboard-top-select")
            if st.button("进入Bad Case闭环", key="dashboard-top-go"): jump_to("Bad Case")
        st.subheader("按导购高风险问题")
        st.dataframe(pd.DataFrame(metrics["high_by_user"]), width="stretch", hide_index=True)
    with right:
        st.subheader("高风险问题趋势")
        if metrics["risk_trend"]:
            risk_df = pd.DataFrame(metrics["risk_trend"]).rename(columns={"day":"日期","count":"高风险数量"})
            risk_df["预警线"] = 3
            st.line_chart(risk_df.set_index("日期"))
            if any(risk_df["高风险数量"] > 3): st.error("部分日期高风险问题超过日均3条预警线，建议按门店和导购开展专项培训。")
        else: st.info("当前时间范围内没有高风险问题。")
        st.subheader("零结果问题Top10")
        zero_df = pd.DataFrame(metrics["zero_questions"])
        if zero_df.empty:
            st.success("暂无零结果问题，知识库覆盖良好。")
        else:
            zero_df = zero_df.rename(columns={"intent":"问题类型","question":"问题","count":"次数"})
            st.dataframe(zero_df, width="stretch", hide_index=True)
            if role == "regional_admin" and st.button("进入知识库维护", key="dashboard-zero-go"): jump_to("商品与推荐配置")
        st.subheader("按门店高风险问题")
        st.dataframe(pd.DataFrame(metrics["high_by_store"]), width="stretch", hide_index=True)
    st.subheader("门店横向对比与综合排名")
    rank_df = pd.DataFrame(metrics["store_rank"])
    if not rank_df.empty:
        rank_df = rank_df.rename(columns={"store_id":"门店","store_name":"门店名称","status":"状态","queries":"提问量","high_risk":"高风险数","zero_results":"零结果数","active_users":"活跃导购"})
        if "状态" in rank_df: rank_df["状态"] = rank_df["状态"].map(role_status_name)
        st.dataframe(rank_df, width="stretch", hide_index=True)
    st.subheader("门店问题类型差异")
    if metrics["intent_by_store"]:
        pivot = pd.DataFrame(metrics["intent_by_store"]).pivot(index="store_id", columns="intent", values="count").fillna(0)
        st.bar_chart(pivot)
    st.subheader("导购成长曲线")
    learn_df = pd.DataFrame(metrics.get("learning_progress", []))
    if learn_df.empty: st.info("暂无淡场学习记录。")
    else: st.dataframe(learn_df.rename(columns={"name":"导购","store_id":"门店","attempts":"练习次数","correct":"答对数","accuracy":"正确率"}), width="stretch", hide_index=True)
    st.subheader("运营动作效果追踪")
    if metrics["action_effects"]: st.dataframe(pd.DataFrame(metrics["action_effects"]), width="stretch", hide_index=True)
    else: st.info("暂无规则发布、商品更新或Bad Case优化记录。")
    st.caption("客诉关联指标将在接入门店客诉系统后展示；当前客诉记录数：" + str(metrics["complaint_count"]))
    c1, c2 = st.columns(2)
    c1.download_button("导出Excel报表", make_dashboard_excel(metrics), file_name=f"门店看板-{selected_store}-{date_to}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    c2.download_button("导出看板图片", make_dashboard_png(metrics, f"门店智伴 - {selected_store}"), file_name=f"门店看板-{selected_store}-{date_to}.png", mime="image/png", width="stretch")

def page_product_requests(user_id: int, role: str, store_id: str) -> None:
    if not require_roles(role, {"manager", "regional_admin"}):
        return
    st.title("新品建档")
    if st.button("刷新申请", key="refresh-product-requests"):
        st.rerun()
    requests = list_product_requests(store_id="ALL" if role == "regional_admin" else store_id)
    if not requests:
        st.markdown('<div class="empty-guide">暂无新品建档申请。导购扫描未知条码后可提交商品资料。</div>', unsafe_allow_html=True)
        return
    for item in requests:
        with st.expander(f"#{item['request_id']}｜{item['status']}｜{item['store_name']}｜{item['scanned_code']}"):
            st.caption(f"提交人：{item['requester']}｜提交时间：{item['created_at']}｜现场备注：{item['note']}")
            if item.get("photo_path"):
                photo = ROOT / item["photo_path"]
                if photo.exists():
                    st.image(str(photo), width=280)
            c1, c2, c3 = st.columns(3)
            proposed_code = c1.text_input("商品编码", value=item["proposed_product_code"], key=f"pr-code-{item['request_id']}")
            product_name = c2.text_input("商品名称", value=item["product_name"], key=f"pr-name-{item['request_id']}")
            category = c3.text_input("商品类别", value=item["category"], key=f"pr-category-{item['request_id']}")
            fabric = st.text_input("面料", value=item["fabric"], key=f"pr-fabric-{item['request_id']}")
            fit = st.text_input("版型", value=item["fit"], key=f"pr-fit-{item['request_id']}")
            target = st.text_input("适用顾客", value=item["target_customer"], key=f"pr-target-{item['request_id']}")
            tags = st.text_input("顾客标签（|分隔）", value=item["customer_tags"], key=f"pr-tags-{item['request_id']}")
            aliases = st.text_input("别名（|分隔）", value=item["aliases"], key=f"pr-alias-{item['request_id']}")
            selling = st.text_area("核心卖点", value=item["selling_points"], key=f"pr-selling-{item['request_id']}")
            styling = st.text_area("搭配建议", value=item["styling_tips"], key=f"pr-style-{item['request_id']}")
            size_notes = st.text_area("尺码提示", value=item["size_notes"], key=f"pr-size-{item['request_id']}")
            objection = st.text_area("常见异议", value=item["common_objection"], key=f"pr-objection-{item['request_id']}")
            script = st.text_area("标准话术", value=item["suggested_script"], key=f"pr-script-{item['request_id']}")
            forbidden = st.text_area("禁止承诺", value=item["forbidden_claims"], key=f"pr-forbidden-{item['request_id']}")
            fields = {
                "proposed_product_code": proposed_code, "product_name": product_name, "category": category,
                "fabric": fabric, "fit": fit, "target_customer": target, "customer_tags": tags, "aliases": aliases,
                "selling_points": selling, "styling_tips": styling, "size_notes": size_notes,
                "common_objection": objection, "suggested_script": script, "forbidden_claims": forbidden,
            }
            if role == "manager":
                c1, c2 = st.columns(2)
                if c1.button("保存草稿", key=f"pr-save-{item['request_id']}", width="stretch"):
                    update_product_request(item["request_id"], user_id, {**fields, "manager_id": user_id})
                    st.rerun()
                if c2.button("提交区域审核", key=f"pr-submit-{item['request_id']}", type="primary", width="stretch"):
                    update_product_request(item["request_id"], user_id, {**fields, "manager_id": user_id, "status": "待区域审核"})
                    st.rerun()
            else:
                c1, c2, c3, c4 = st.columns(4)
                price = c1.number_input("标价", min_value=0.0, value=299.0, key=f"pr-price-{item['request_id']}")
                promo_price = c2.number_input("活动参考价", min_value=0.0, value=269.0, key=f"pr-promo-{item['request_id']}")
                version = c3.text_input("版本", value="V1.0", key=f"pr-version-{item['request_id']}")
                effective = c4.date_input("生效日期", value=date.fromisoformat(settings.business_date), key=f"pr-effective-{item['request_id']}")
                expiry = st.date_input("失效日期", value=date.fromisoformat(settings.business_date)+timedelta(days=365), key=f"pr-expiry-{item['request_id']}")
                c5, c6, c7 = st.columns(3)
                if c5.button("保存资料", key=f"pr-reg-save-{item['request_id']}", width="stretch"):
                    update_product_request(item["request_id"], user_id, {**fields, "regional_reviewer_id": user_id})
                    st.rerun()
                if c6.button("退回店长修改", key=f"pr-return-{item['request_id']}", width="stretch"):
                    update_product_request(item["request_id"], user_id, {**fields, "status": "运营退回修改", "regional_reviewer_id": user_id})
                    st.rerun()
                if c7.button("审核发布", key=f"pr-publish-{item['request_id']}", type="primary", width="stretch"):
                    if not catalog_write_allowed():
                        return
                    update_product_request(item["request_id"], user_id, {**fields, "status": "待区域审核", "regional_reviewer_id": user_id})
                    try:
                        code = publish_product_request(item["request_id"], user_id, price, promo_price, version, effective.isoformat(), expiry.isoformat())
                        refresh_services()
                        st.success(f"商品 {code} 已发布，条码映射和零库存档案已建立。")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def page_learning(user_id: int, store_id: str, role: str) -> None:
    st.title("淡场学习模式")
    st.caption("每日用3—5分钟巩固商品、活动、售后和服务红线，店长可在看板查看成长曲线。")
    quizzes = [
        {"key":"return-tag-cut","category":"售后规则","question":"顾客吊牌已剪、无明显穿着痕迹，导购应该怎么做？","options":["直接承诺退款","直接拒绝并让顾客离店","核验商品和凭证后交店长确认","私下换一件"],"answer":"核验商品和凭证后交店长确认","explain":"吊牌已剪属于特殊退换场景，新人无权直接承诺，需核验并交负责人处理。"},
        {"key":"wool-pilling","category":"商品知识","question":"顾客问羊毛大衣是否绝对不起球，正确口径是什么？","options":["绝对不起球","摩擦部位可能轻微起球，应按洗标护理","只要贵就不起球","起球就是质量问题"],"answer":"摩擦部位可能轻微起球，应按洗标护理","explain":"羊毛/毛呢在摩擦位置可能出现轻微起球，不得作绝对化承诺。"},
        {"key":"promo-stack","category":"活动规则","question":"会员折扣与全场活动不可叠加时，应如何处理？","options":["导购自行叠加","让顾客二选一并在结算前说明","结算后再补差","私下收款"],"answer":"让顾客二选一并在结算前说明","explain":"优惠口径必须以当前活动规则和收银系统为准。"},
        {"key":"busy-service","category":"服务SOP","question":"旺场同时有三位顾客需要服务，推荐做法是？","options":["只服务第一位，不理其他人","接一、待二、招呼三","让所有人自己找","把问题全部推给店长"],"answer":"接一、待二、招呼三","explain":"通过回应和预期管理避免顾客被忽视。"},
        {"key":"white-shirt","category":"商品知识","question":"介绍白衬衫防透时，哪种话术更安全？","options":["任何颜色内衣都完全不透","建议搭配肤色内衣并现场试穿确认","永远不会发黄","洗多少次都不皱"],"answer":"建议搭配肤色内衣并现场试穿确认","explain":"卖点要有边界，并给出可验证的现场动作。"},
        {"key":"stock-promise","category":"库存调货","question":"本店断货、附近店显示可调货时，导购可以怎么说？","options":["保证明天一定到","先确认附近库存和调货时效后再答复","让顾客直接去别家","随口估计三天"],"answer":"先确认附近库存和调货时效后再答复","explain":"库存属于实时数据，未锁定前不能承诺。"},
    ]
    index = (date.fromisoformat(settings.business_date).toordinal() + user_id) % len(quizzes)
    quiz = quizzes[index]
    with st.container(border=True):
        st.markdown(f"### 今日考点｜{quiz['category']}")
        st.write(quiz["question"])
        choice = st.radio("选择答案", quiz["options"], index=None, key=f"quiz-{quiz['key']}")
        if st.button("提交答案", type="primary", disabled=choice is None, width="stretch"):
            correct = choice == quiz["answer"]
            submit_learning_result(user_id, store_id, quiz["key"], quiz["category"], choice or "", correct)
            track_event(user_id, store_id, "淡场学习", "quiz", quiz["key"], {"correct": correct})
            if correct: st.success("回答正确。" + quiz["explain"])
            else: st.error("回答不正确。正确答案：" + quiz["answer"]); st.info(quiz["explain"])
    st.markdown("#### 我的学习记录")
    progress = learning_progress(store_id=store_id, user_id=user_id)
    if progress: st.dataframe(pd.DataFrame(progress).rename(columns={"name":"姓名","store_id":"门店","attempts":"练习次数","correct":"答对数","accuracy":"正确率","last_practice":"最近练习"}), width="stretch", hide_index=True)
    else: st.info("完成今日练习后，将在这里形成成长记录。")


def page_catalog_admin(user_id: int) -> None:
    st.title("商品与推荐配置")
    tabs = st.tabs(["商品维护", "批量更新", "连带推荐配置"])
    products = safe_load(load_products, "商品")
    with tabs[0]:
        options = {f"{r.product_name}｜{r.product_code}": idx for idx, r in products.iterrows()}
        selected = st.selectbox("选择商品", list(options))
        idx = options[selected]
        row = products.loc[idx].to_dict()
        with st.form("edit-product"):
            c1, c2, c3 = st.columns(3)
            row["product_name"] = c1.text_input("商品名称", row["product_name"])
            row["category"] = c2.text_input("类别", row["category"])
            row["version"] = c3.text_input("版本", row["version"])
            d1, d2 = st.columns(2)
            try:
                current_effective = date.fromisoformat(row["effective_date"])
            except ValueError:
                current_effective = date.fromisoformat(settings.business_date)
            try:
                current_expiry = date.fromisoformat(row["expiry_date"])
            except ValueError:
                current_expiry = current_effective + timedelta(days=365)
            row["effective_date"] = d1.date_input("生效日期", current_effective).isoformat()
            row["expiry_date"] = d2.date_input("失效日期", current_expiry).isoformat()
            for field, label in [
                ("fabric", "面料"), ("fit", "版型"), ("target_customer", "适用顾客"),
                ("customer_tags", "顾客标签"), ("aliases", "别名"), ("selling_points", "核心卖点"),
                ("styling_tips", "搭配建议"), ("size_notes", "尺码提示"), ("common_objection", "常见异议"),
                ("suggested_script", "标准话术"), ("forbidden_claims", "禁止承诺"),
            ]:
                row[field] = st.text_area(label, row[field])
            save = st.form_submit_button("保存商品", type="primary", width="stretch")
        if save:
            if not catalog_write_allowed():
                return
            for col in PRODUCT_COLUMNS:
                products.loc[idx, col] = row.get(col, "")
            save_products(products, user_id)
            refresh_services()
            st.success("商品资料已保存。")
            st.rerun()
    with tabs[1]:
        selected_codes = st.multiselect("选择商品", products["product_code"].tolist())
        field_map = {"禁止承诺": "forbidden_claims", "尺码提示": "size_notes", "版本": "version", "生效日期": "effective_date", "失效日期": "expiry_date", "顾客标签": "customer_tags"}
        field_label = st.selectbox("批量更新字段", list(field_map))
        value = st.text_area("统一值")
        confirm = st.checkbox(f"确认更新 {len(selected_codes)} 个商品")
        if st.button("批量保存", type="primary", disabled=not selected_codes):
            if not catalog_write_allowed():
                return
            if not confirm:
                st.error("请勾选确认。")
            else:
                products.loc[products["product_code"].isin(selected_codes), field_map[field_label]] = value
                save_products(products, user_id, action="批量更新商品")
                refresh_services()
                st.rerun()
    with tabs[2]:
        recs = safe_load(load_recommendations, "推荐")
        edited = st.data_editor(recs, num_rows="dynamic", width="stretch", hide_index=True)
        if st.button("保存推荐配置", type="primary"):
            if not catalog_write_allowed():
                return
            save_recommendations(edited, user_id)
            refresh_services()
            st.rerun()


def page_audit(role: str) -> None:
    if not require_roles(role, {"regional_admin"}):
        return
    st.title("操作日志")
    actions = ["全部", "审批工单", "升级工单", "处理Bad Case", "发布规则", "更新商品", "批量更新商品", "发布新品", "更新连带推荐"]
    action = st.selectbox("操作类型", actions)
    store = st.selectbox("门店", ["ALL", *[s["store_id"] for s in list_stores()]], format_func=lambda x: "全部门店" if x == "ALL" else x)
    if st.button("刷新日志", key="refresh-audit"):
        st.rerun()
    logs = list_audit_logs(store_id=store, action=action)
    if not logs:
        st.markdown('<div class="empty-guide">暂无操作记录。审批、商品、规则和知识处理动作会自动留痕。</div>', unsafe_allow_html=True)
        return
    st.dataframe(pd.DataFrame(logs)[["created_at", "actor_name", "actor_role", "store_id", "action", "entity_type", "entity_id"]], width="stretch", hide_index=True)
    for item in logs[:50]:
        with st.expander(f"{item['created_at']}｜{item['actor_name']}｜{item['action']}｜{item['entity_type']} {item['entity_id']}"):
            if item["before_json"]:
                st.markdown("**操作前**")
                st.json(json.loads(item["before_json"]))
            if item["after_json"]:
                st.markdown("**操作后**")
                st.json(json.loads(item["after_json"]))


def main() -> None:
    demo_access_gate()
    users = list_users()
    st.sidebar.title("🧥 门店智伴")
    st.sidebar.caption("服装门店导购AI知识与销售辅助系统")
    if settings.is_demo:
        st.sidebar.caption("🧪 作品演示｜模拟业务数据")
    user = resolve_signed_in_user(users)
    user_id, role, fixed_store = user["user_id"], user["role"], user["store_id"]
    if role == "regional_admin":
        stores = list_stores()
        scope_store = st.sidebar.selectbox("当前查看门店", ["ALL", *[x["store_id"] for x in stores]], format_func=lambda x: "全部门店" if x == "ALL" else next((f"{z['store_id']}｜{z['store_name']}｜{role_status_name(z['status'])}" for z in stores if z['store_id']==x), x))
        current_store = "S001" if scope_store == "ALL" else scope_store
    else:
        current_store = fixed_store
        st.sidebar.text_input("所属门店", value=current_store, disabled=True)
    st.sidebar.caption(f"业务日期：{settings.business_date}")
    if settings.is_demo and role == "regional_admin":
        if st.sidebar.button("重置演示数据", width="stretch", help="恢复商品、规则、工单和反馈的初始演示状态"):
            reset_demo_runtime()
            st.cache_data.clear()
            st.cache_resource.clear()
            clear_context_state()
            init_db()
            st.success("演示数据已恢复。")
            st.rerun()
    render_demo_banner()
    context = (user_id, current_store)
    if st.session_state.get("last_context") and st.session_state.last_context != context:
        clear_context_state()
    st.session_state.last_context = context
    st.session_state.current_user_id = user_id
    st.session_state.current_store_id = current_store
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("price_cart", [])
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    track_user_session(user_id, current_store, role, st.session_state.session_id)
    counts = count_pending_by_risk(role=role, user_store=fixed_store) if role in {"manager", "regional_admin"} else {"high": 0, "medium": 0, "low": 0}
    open_badcases = count_open_feedback(role, fixed_store) if role in {"manager", "regional_admin"} else 0
    unread_count = len(list_notifications(user_id, unread_only=True))
    unread_rules = len(unacknowledged_rules(user_id, active_rule_rows()))
    st.sidebar.markdown("### 待办提醒")
    if role in {"manager", "regional_admin"}:
        st.sidebar.markdown(f"🔴 高风险工单 **{counts['high']}**　🟡 中风险 **{counts['medium']}**")
        st.sidebar.markdown(f"🧩 待处理Bad Case **{open_badcases}**")
    st.sidebar.markdown(f"📘 未读规则 **{unread_rules}**")
    st.sidebar.markdown(f"🔔 未读通知 **{unread_count}**")
    if st.sidebar.button("启用桌面通知", width="stretch"):
        st.session_state.desktop_notifications_enabled = True
        browser_notification("门店智伴通知已启用", "高风险工单、升级工单和规则更新将在浏览器允许时提醒。", "notification-enabled")
    critical_notices = [x for x in list_notifications(user_id, unread_only=True) if x["notification_type"] in {"escalated_review","review_assignment","review_result"}]
    if st.session_state.get("desktop_notifications_enabled") and not st.session_state.get("desktop_notified"):
        if critical_notices:
            first = critical_notices[0]
            browser_notification(first["title"], first["content"], f"notice-{first['notification_id']}")
            st.session_state.desktop_notified = True
        elif unread_rules:
            browser_notification("门店规则已更新", f"当前有 {unread_rules} 条规则待确认阅读。", "rule-update")
            st.session_state.desktop_notified = True
    pages = ["导购问答", "通知中心", "问答记录", "顾客需求匹配", "商品知识卡", "连带推荐", "快捷算价", "规则中心", "淡场学习"]
    if role == "manager": pages += ["店长确认", "Bad Case", "新品建档", "数据看板"]
    elif role == "regional_admin": pages += ["区域工单", "Bad Case", "新品建档", "商品与推荐配置", "数据看板", "操作日志"]
    current_nav = st.session_state.get("nav_page")
    if current_nav not in pages: st.session_state["nav_page"] = pages[0]
    page = st.sidebar.radio("功能导航", pages, key="nav_page")
    show_rule_notice(user_id)
    handlers = {
        "导购问答": lambda: page_chat(user_id, current_store, role), "通知中心": lambda: page_notifications(user_id),
        "问答记录": lambda: page_question_records(user_id, role, fixed_store), "顾客需求匹配": lambda: page_customer_match(current_store),
        "商品知识卡": lambda: page_products(current_store), "连带推荐": lambda: page_recommendations(current_store),
        "快捷算价": lambda: page_price_calculator(current_store), "规则中心": lambda: page_rules(user_id, role),
        "淡场学习": lambda: page_learning(user_id, current_store, role), "店长确认": lambda: page_reviews(user_id, role, fixed_store),
        "区域工单": lambda: page_reviews(user_id, role, fixed_store), "Bad Case": lambda: page_bad_cases(user_id, role, fixed_store),
        "新品建档": lambda: page_product_requests(user_id, role, fixed_store), "商品与推荐配置": lambda: page_catalog_admin(user_id),
        "数据看板": lambda: page_dashboard(role, fixed_store), "操作日志": lambda: page_audit(role),
    }
    handlers[page]()
    st.divider(); st.caption(f"{settings.app_name} v{settings.app_version}｜{"演示环境" if settings.is_demo else "正式环境"}")


try:
    main()
except Exception as exc:
    logger.exception("unhandled ui error")
    try:
        record_error("ui.global", str(exc), traceback.format_exc(), st.session_state.get("current_user_id"), st.session_state.get("current_store_id", ""))
    except Exception:
        pass
    st.error("系统繁忙，请稍后再试，或联系负责人处理。")
