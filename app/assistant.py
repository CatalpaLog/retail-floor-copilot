from __future__ import annotations

import re
from pathlib import Path

from .config import DATA_DIR, DB_PATH, settings
from .db import init_db, record_question
from .inventory import InventoryService
from .llm import generate_with_llm
from .logging_utils import get_logger
from .retrieval import HybridRetriever, RetrievedDocument
from .risk import classify
from .schemas import AnswerPayload, SourceItem

logger = get_logger(__name__)

DOC_TYPES_BY_INTENT = {
    "商品知识": {"商品资料", "销售SOP"},
    "搭配话术": {"商品资料", "销售SOP"},
    "活动会员": {"活动规则"},
    "售后规则": {"售后规则"},
    "投诉处理": {"售后规则"},
    "其他": set(),
}


class RetailAssistant:
    def __init__(self, data_dir: Path | str = DATA_DIR, db_path: Path | str = DB_PATH):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        init_db(self.db_path)
        self.retriever = HybridRetriever(self.data_dir)
        self.inventory = InventoryService(self.data_dir)

    @staticmethod
    def _extract_sentence(content: str, label: str) -> str:
        pattern = re.compile(rf"{re.escape(label)}[:：]\s*([^。；\n]+)")
        match = pattern.search(content)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _build_context(results: list[RetrievedDocument]) -> str:
        return "\n\n".join(
            f"[来源:{x.document.title}|章节:{x.document.source_section}|版本:{x.document.version}|分数:{x.score}]\n{x.document.content}"
            for x in results
        )

    @staticmethod
    def _live_data_fallback(question: str) -> dict[str, str]:
        if any(x in question for x in ["库存", "有货", "仓库", "调货", "补货", "预留"]):
            return {
                "conclusion": "未识别到明确商品，无法查询库存。",
                "suggested_script": "“请告诉我商品编码或商品名称，我马上帮您查本店和附近门店库存。”",
                "conditions": "支持吊牌扫码、商品编码或商品名称查询。",
                "warning": "未锁定库存前不得承诺一定有货或到货时间。",
            }
        if any(x in question for x in ["多少钱", "价格", "活动价"]):
            return {
                "conclusion": "未识别到明确商品，无法核对当前价格。",
                "suggested_script": "“请提供商品编码，我帮您核对当前标价和活动参考价，最终以收银系统结算为准。”",
                "conditions": "价格、券码、会员权益和活动状态属于实时交易数据。",
                "warning": "不得口头估价或绕过收银系统承诺成交价。",
            }
        return {
            "conclusion": "该信息需要通过对应业务系统核实。",
            "suggested_script": "“我帮您通过对应系统或负责人核实，确认后再给您准确答复。”",
            "conditions": "排班、财务、设备等信息不属于当前知识范围。",
            "warning": "不得猜测内部实时信息。",
        }

    def _fallback_answer(self, question: str, intent: str, risk_level: str, results: list[RetrievedDocument]) -> dict[str, str]:
        if not results:
            return {
                "conclusion": "当前知识库没有找到可靠依据，暂时无法确认。",
                "suggested_script": "“这个问题我先帮您向店长确认，确认后再给您准确答复。”",
                "conditions": "需要补充或核对对应商品、活动或售后资料。",
                "warning": "请勿根据经验自行承诺。",
            }
        top = results[0].document
        content = top.content
        if top.doc_type == "商品资料":
            selling = self._extract_sentence(content, "核心卖点") or content[:96]
            script = self._extract_sentence(content, "推荐话术")
            size_notes = self._extract_sentence(content, "尺码提示")
            forbidden = self._extract_sentence(content, "禁止承诺")
            return {
                "conclusion": selling + ("。" if not selling.endswith("。") else ""),
                "suggested_script": script or "“我结合您的穿着场景、身形和试穿感受，帮您确认更合适的选择。”",
                "conditions": size_notes or "尺码和体感以现场试穿为准。",
                "warning": forbidden or "不得作出资料中没有的绝对化承诺。",
            }
        first = re.split(r"[\n。]", content.strip(), maxsplit=1)[0].strip()
        conclusion = first[:160] + ("。" if first and not first.endswith("。") else "")
        return {
            "conclusion": conclusion or f"请参考《{top.title}》中的当前生效规则。",
            "suggested_script": "“我先按当前生效规则为您核对；涉及权限或特殊处理的部分，需要由店长确认后再答复。”" if risk_level == "high" else "“我按当前生效规则为您说明，最终以门店系统和现场核验结果为准。”",
            "conditions": f"版本：{top.version}；有效期：{top.effective_date} 至 {top.expiry_date}。",
            "warning": "涉及经济损失、权限审批或客诉升级时，必须由店长处理。" if risk_level == "high" else "如资料冲突、过期或适用范围不明确，请停止回答并联系店长。",
        }

    def answer(self, question: str, user_id: int = 1, store_id: str = "S001", persist: bool = True) -> AnswerPayload:
        classification = classify(question)
        normalized_question = classification.normalized_question or question
        product_code = self.inventory.extract_product_code(normalized_question) or ""
        manager_reason = ""
        try:
            if classification.prohibited_instruction:
                results = self.retriever.search(
                    normalized_question,
                    top_k=settings.top_k,
                    min_score=settings.min_score,
                    store_id=store_id,
                    allowed_doc_types=DOC_TYPES_BY_INTENT.get(classification.intent, set()),
                ) if classification.intent != "其他" else []
                text = {
                    "conclusion": "不能按照该要求作出虚假、越权或绝对化承诺。",
                    "suggested_script": "“我只能依据商品资料和当前门店规则如实说明；涉及优惠、退换或特殊处理时，需要店长确认。”",
                    "conditions": "回答需有可核验来源，并遵守门店权限和服务红线。",
                    "warning": "禁止虚假宣传、私自让利、绕过审批或把风险转嫁给他人。",
                }
                refused = True
                manager_reason = "触发服务红线"
            elif classification.requires_live_data:
                results = []
                inventory_answer = self.inventory.answer_inventory_question(normalized_question, store_id)
                text = inventory_answer or self._live_data_fallback(normalized_question)
                product_code = (inventory_answer or {}).get("product_code", product_code)
                refused = inventory_answer is None
                if refused:
                    manager_reason = "缺少商品或业务系统数据"
            else:
                allowed = DOC_TYPES_BY_INTENT.get(classification.intent, set())
                results = [] if classification.intent == "其他" else self.retriever.search(
                    normalized_question,
                    top_k=settings.top_k,
                    min_score=settings.min_score,
                    store_id=store_id,
                    allowed_doc_types=allowed,
                )
                if not results and classification.intent in {"活动会员", "售后规则", "投诉处理"}:
                    results = self.retriever.search(
                        normalized_question,
                        top_k=settings.top_k,
                        min_score=0.0,
                        store_id=store_id,
                        allowed_doc_types=allowed,
                    )
                refused = not results
                context = self._build_context(results)
                generated = generate_with_llm(normalized_question, context, classification.risk_level) if results else None
                text = generated or self._fallback_answer(normalized_question, classification.intent, classification.risk_level, results)

            sources = [
                SourceItem(
                    doc_id=x.document.doc_id,
                    title=x.document.title,
                    section=x.document.source_section,
                    score=x.score,
                    version=x.document.version,
                    effective_date=x.document.effective_date,
                    expiry_date=x.document.expiry_date,
                )
                for x in results[:3]
            ]
            top_score = results[0].score if results else (0.95 if classification.requires_live_data and not refused else 0.0)
            confidence = "high" if top_score >= 0.38 else "medium" if top_score >= 0.14 else "low"
            need_manager = (
                classification.risk_level == "high"
                or classification.prohibited_instruction
                or refused
                or (bool(results) and confidence == "low")
            )
            if need_manager and not manager_reason:
                if classification.risk_level == "high":
                    manager_reason = "高风险业务"
                elif refused:
                    manager_reason = "未检索到可靠依据"
                elif confidence == "low":
                    manager_reason = "检索置信度不足"

            payload = AnswerPayload(
                conclusion=text.get("conclusion", ""),
                suggested_script=text.get("suggested_script", ""),
                conditions=text.get("conditions", ""),
                warning=text.get("warning", ""),
                sources=sources,
                intent=classification.intent,
                risk_level=classification.risk_level,
                need_manager_confirmation=need_manager,
                refused=refused,
                confidence_level=confidence,
                manager_reason=manager_reason,
                product_code=product_code,
            )
            if persist:
                payload.query_id = record_question(
                    {
                        "question": question,
                        "intent": payload.intent,
                        "risk_level": payload.risk_level,
                        "conclusion": payload.conclusion,
                        "suggested_script": payload.suggested_script,
                        "warning": payload.warning,
                        "source_titles": [s.title for s in payload.sources],
                        "need_manager_confirmation": payload.need_manager_confirmation,
                        "refused": payload.refused,
                        "confidence_level": payload.confidence_level,
                    },
                    user_id=user_id,
                    store_id=store_id,
                    db_path=self.db_path,
                )
            return payload
        except Exception:
            logger.exception("answer failed")
            payload = AnswerPayload(
                conclusion="系统暂时无法完成查询。",
                suggested_script="“系统现在有点忙，我先按门店规则为您核实，稍后给您准确答复。”",
                conditions="可前往规则中心查看当前生效制度，或联系店长处理。",
                warning="系统异常时不得凭经验作出价格、库存、退换货或优惠承诺。",
                intent=classification.intent,
                risk_level="high" if classification.risk_level == "high" else "medium",
                need_manager_confirmation=True,
                refused=True,
                confidence_level="low",
                manager_reason="系统异常",
                product_code=product_code,
            )
            if persist:
                payload.query_id = record_question(
                    {
                        "question": question,
                        "intent": payload.intent,
                        "risk_level": payload.risk_level,
                        "conclusion": payload.conclusion,
                        "suggested_script": payload.suggested_script,
                        "warning": payload.warning,
                        "source_titles": [],
                        "need_manager_confirmation": True,
                        "refused": True,
                        "confidence_level": "low",
                    },
                    user_id=user_id,
                    store_id=store_id,
                    db_path=self.db_path,
                )
            return payload
