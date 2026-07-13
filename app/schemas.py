from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["商品知识", "搭配话术", "活动会员", "售后规则", "投诉处理", "其他"]
RiskLevel = Literal["low", "medium", "high"]


class SourceItem(BaseModel):
    doc_id: str
    title: str
    section: str = ""
    score: float = 0.0
    version: str = ""
    effective_date: str = ""
    expiry_date: str = ""


class AnswerPayload(BaseModel):
    conclusion: str
    suggested_script: str
    conditions: str = ""
    warning: str = ""
    sources: list[SourceItem] = Field(default_factory=list)
    intent: Intent = "其他"
    risk_level: RiskLevel = "low"
    need_manager_confirmation: bool = False
    refused: bool = False
    confidence_level: Literal["high", "medium", "low"] = "medium"
    query_id: int | None = None
    manager_reason: str = ""
    product_code: str = ""


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    user_id: int = 1
    store_id: str = "S001"


class FeedbackRequest(BaseModel):
    query_id: int
    feedback_type: Literal[
        "有帮助", "答案不准确", "来源不匹配", "规则已过期", "话术不适合", "没有解决问题", "应交由店长处理"
    ]
    comment: str = ""


class ReviewUpdate(BaseModel):
    review_status: Literal["confirmed", "corrected", "rejected"]
    corrected_answer: str = ""
    review_note: str = ""


class ReviewEscalation(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


class FeedbackUpdate(BaseModel):
    processing_status: Literal["待处理", "处理中", "已优化", "已关闭"]
    issue_type: str
    comment: str = ""
    assigned_to: int | None = None
    resolution_action: str = ""
    linked_entity_type: str = ""
    linked_doc_id: str = ""
    optimized_version: str = ""
    verification_note: str = ""


class ProductRequestCreate(BaseModel):
    scanned_code: str = Field(min_length=2, max_length=100)
    product_name: str = ""
    category: str = ""
    note: str = ""


class ProductRequestUpdate(BaseModel):
    fields: dict[str, str | int | None]


class ProductPublishRequest(BaseModel):
    price: float = Field(ge=0)
    promo_price: float = Field(ge=0)
    version: str = "V1.0"
    effective_date: str
    expiry_date: str


class RulePublishRequest(BaseModel):
    title: str
    doc_type: str
    version: str
    effective_date: str
    expiry_date: str
    store_scope: str = "ALL"
    risk_level: str = "medium"
    source_section: str = ""
    keywords: str = ""
    content: str


class CatalogProductsUpdate(BaseModel):
    products: list[dict[str, str]]


class RecommendationUpdate(BaseModel):
    recommendations: list[dict[str, str]]


class HealthResponse(BaseModel):
    status: str
    version: str
    time: datetime
