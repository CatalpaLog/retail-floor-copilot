from __future__ import annotations

import hmac
import traceback
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .assistant import RetailAssistant
from .catalog import publish_product_request, publish_rule, save_products, save_recommendations
from .config import DATA_DIR
import pandas as pd
from .config import settings
from .db import (
    add_feedback,
    create_product_request,
    dashboard_metrics,
    escalate_review,
    get_product_request,
    get_review,
    get_user,
    list_audit_logs,
    list_feedback,
    list_pending_reviews,
    list_product_requests,
    list_questions_scope,
    record_error,
    update_feedback,
    update_product_request,
    update_review,
)
from .inventory import InventoryService
from .logging_utils import get_logger
from .schemas import (
    AnswerPayload,
    AskRequest,
    FeedbackRequest,
    FeedbackUpdate,
    HealthResponse,
    CatalogProductsUpdate,
    ProductPublishRequest,
    ProductRequestCreate,
    ProductRequestUpdate,
    RecommendationUpdate,
    RulePublishRequest,
    ReviewEscalation,
    ReviewUpdate,
)

logger = get_logger(__name__)
app = FastAPI(
    title="Retail Floor Copilot API",
    version=settings.app_version,
    description="服装门店导购知识、库存、审批、反馈、商品建档与区域运营API。",
)
assistant = RetailAssistant()
inventory = InventoryService()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled api error: %s %s", request.method, request.url.path)
    record_error("api.global", str(exc), traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": "系统繁忙，请稍后再试，或联系负责人处理。"})


def current_user(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    x_demo_token: str = Header(default="", alias="X-Demo-Token"),
) -> dict:
    if settings.api_demo_token and not hmac.compare_digest(x_demo_token, settings.api_demo_token):
        raise HTTPException(status_code=401, detail="演示接口令牌无效")
    user = get_user(x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="无权限执行该操作")
        return user
    return dependency


def ensure_review_access(review_id: int, user: dict) -> dict:
    item = get_review(review_id)
    if not item:
        raise HTTPException(status_code=404, detail="工单不存在")
    if user["role"] == "manager" and (item["store_id"] != user["store_id"] or item["review_level"] != "manager"):
        raise HTTPException(status_code=403, detail="该工单不属于当前门店")
    if user["role"] not in {"manager", "regional_admin"}:
        raise HTTPException(status_code=403, detail="无权限执行该操作")
    return item


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version, time=datetime.now(timezone.utc))


@app.post("/ask", response_model=AnswerPayload)
def ask(request: AskRequest, user: dict = Depends(current_user)) -> AnswerPayload:
    store_id = user["store_id"] if user["role"] != "regional_admin" else request.store_id
    return assistant.answer(request.question, user["user_id"], store_id, persist=True)


@app.get("/questions")
def questions(store_id: str | None = None, user: dict = Depends(current_user)) -> list[dict]:
    return list_questions_scope(user["role"], user["user_id"], user["store_id"], store_id)


@app.get("/inventory/{product_code}")
def inventory_lookup(product_code: str, store_id: str = "S001", size: str | None = None, user: dict = Depends(current_user)) -> dict:
    target_store = user["store_id"] if user["role"] != "regional_admin" else store_id
    result = inventory.lookup(product_code, target_store, size)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="商品不存在")
    return result


@app.post("/feedback")
def feedback(request: FeedbackRequest, user: dict = Depends(current_user)) -> dict[str, int | str]:
    feedback_id = add_feedback(request.query_id, request.feedback_type, request.comment)
    return {"status": "created", "feedback_id": feedback_id}


@app.get("/reviews")
def reviews(
    store_id: str | None = None,
    risk_level: str | None = None,
    user: dict = Depends(require_roles("manager", "regional_admin")),
) -> list[dict]:
    return list_pending_reviews(
        role=user["role"], user_store=user["store_id"], region_id=user["region_id"],
        store_id=store_id, risk_level=risk_level,
    )


@app.patch("/reviews/{review_id}")
def review_update(review_id: int, request: ReviewUpdate, user: dict = Depends(require_roles("manager", "regional_admin"))) -> dict[str, str]:
    ensure_review_access(review_id, user)
    update_review(review_id, request.review_status, request.corrected_answer, request.review_note, user["user_id"])
    return {"status": "updated"}


@app.post("/reviews/{review_id}/escalate")
def review_escalate(review_id: int, request: ReviewEscalation, user: dict = Depends(require_roles("manager"))) -> dict[str, str]:
    ensure_review_access(review_id, user)
    escalate_review(review_id, request.reason, user["user_id"])
    return {"status": "escalated"}


@app.get("/feedback")
def feedback_list(
    store_id: str | None = None,
    user: dict = Depends(require_roles("manager", "regional_admin")),
) -> list[dict]:
    scope = user["store_id"] if user["role"] == "manager" else store_id
    return list_feedback(store_id=scope)


@app.patch("/feedback/{feedback_id}")
def feedback_update(
    feedback_id: int,
    request: FeedbackUpdate,
    user: dict = Depends(require_roles("manager", "regional_admin")),
) -> dict[str, str]:
    items = list_feedback(store_id=user["store_id"] if user["role"] == "manager" else "ALL")
    if feedback_id not in {x["feedback_id"] for x in items}:
        raise HTTPException(status_code=404, detail="当前权限范围内不存在该反馈")
    if user["role"] == "manager" and request.processing_status == "已优化":
        raise HTTPException(status_code=403, detail="只有区域运营可以将知识问题标记为已优化")
    update_feedback(
        feedback_id, request.processing_status, request.issue_type, request.comment,
        request.linked_doc_id, request.optimized_version, user["user_id"], request.assigned_to,
        request.resolution_action, request.linked_entity_type, request.verification_note,
    )
    return {"status": "updated"}


@app.get("/dashboard")
def dashboard(
    store_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: dict = Depends(require_roles("manager", "regional_admin")),
) -> dict:
    scope = user["store_id"] if user["role"] == "manager" else store_id
    return dashboard_metrics(store_id=scope, region_id=user["region_id"], date_from=date_from, date_to=date_to)


@app.post("/product-requests")
def product_request_create(request: ProductRequestCreate, user: dict = Depends(current_user)) -> dict[str, int | str]:
    store_id = user["store_id"] if user["store_id"] != "ALL" else "S001"
    request_id = create_product_request(request.scanned_code, store_id, user["user_id"], request.product_name, request.category, request.note)
    return {"status": "created", "request_id": request_id}


@app.get("/product-requests")
def product_request_list(user: dict = Depends(require_roles("manager", "regional_admin"))) -> list[dict]:
    return list_product_requests(store_id=user["store_id"] if user["role"] == "manager" else "ALL")


@app.get("/audit-logs")
def audit_logs(user: dict = Depends(require_roles("regional_admin"))) -> list[dict]:
    return list_audit_logs()


@app.patch("/product-requests/{request_id}")
def product_request_update(
    request_id: int, request: ProductRequestUpdate,
    user: dict = Depends(require_roles("manager", "regional_admin")),
) -> dict[str, str]:
    item = get_product_request(request_id)
    if not item:
        raise HTTPException(status_code=404, detail="新品建档申请不存在")
    if user["role"] == "manager" and item["store_id"] != user["store_id"]:
        raise HTTPException(status_code=403, detail="该新品申请不属于当前门店")
    update_product_request(request_id, user["user_id"], request.fields)
    return {"status": "updated"}


@app.post("/product-requests/{request_id}/publish")
def product_request_publish(
    request_id: int, request: ProductPublishRequest,
    user: dict = Depends(require_roles("regional_admin")),
) -> dict[str, str]:
    code = publish_product_request(
        request_id, user["user_id"], request.price, request.promo_price, request.version,
        request.effective_date, request.expiry_date,
    )
    return {"status": "published", "product_code": code}


@app.get("/catalog/products")
def catalog_products(user: dict = Depends(current_user)) -> list[dict]:
    return pd.read_csv(DATA_DIR / "products.csv", dtype=str).fillna("").to_dict(orient="records")


@app.put("/catalog/products")
def catalog_products_update(
    request: CatalogProductsUpdate,
    user: dict = Depends(require_roles("regional_admin")),
) -> dict[str, int | str]:
    df = pd.DataFrame(request.products)
    save_products(df, user["user_id"], action="API更新商品")
    return {"status": "updated", "count": len(df)}


@app.get("/catalog/recommendations")
def catalog_recommendations(user: dict = Depends(current_user)) -> list[dict]:
    return pd.read_csv(DATA_DIR / "product_recommendations.csv", dtype=str).fillna("").to_dict(orient="records")


@app.put("/catalog/recommendations")
def catalog_recommendations_update(
    request: RecommendationUpdate,
    user: dict = Depends(require_roles("regional_admin")),
) -> dict[str, int | str]:
    df = pd.DataFrame(request.recommendations)
    save_recommendations(df, user["user_id"])
    return {"status": "updated", "count": len(df)}


@app.post("/catalog/rules")
def catalog_rule_publish(
    request: RulePublishRequest,
    user: dict = Depends(require_roles("regional_admin")),
) -> dict[str, str]:
    doc_id = publish_rule(request.model_dump(), user["user_id"])
    return {"status": "published", "doc_id": doc_id}
