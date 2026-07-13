from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from pypinyin import lazy_pinyin
except Exception:  # optional fallback
    lazy_pinyin = None

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import DATA_DIR, settings

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    doc_type: str
    version: str
    effective_date: str
    expiry_date: str
    store_scope: str
    risk_level: str
    source_section: str
    keywords: str
    content: str

    @property
    def searchable_text(self) -> str:
        return " ".join([self.title, self.doc_type, self.keywords, self.content])


@dataclass(frozen=True)
class RetrievedDocument:
    document: Document
    score: float


class HybridRetriever:
    def __init__(self, data_dir: Path | str = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.product_search_terms: dict[str, list[str]] = {}
        self.documents = self._load_documents()
        corpus = [doc.searchable_text for doc in self.documents]
        self.char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        self.word_vectorizer = TfidfVectorizer(analyzer="word", token_pattern=r"(?u)\b\w+\b", ngram_range=(1, 2), min_df=1)
        self.char_matrix = self.char_vectorizer.fit_transform(corpus)
        self.word_matrix = self.word_vectorizer.fit_transform(corpus)

    def _load_documents(self) -> list[Document]:
        docs: list[Document] = []
        knowledge = pd.read_csv(self.data_dir / "knowledge_docs.csv", dtype=str).fillna("")
        for row in knowledge.to_dict(orient="records"):
            docs.append(Document(**row))

        products = pd.read_csv(self.data_dir / "products.csv", dtype=str).fillna("")
        for row in products.to_dict(orient="records"):
            content = (
                f"商品编码：{row['product_code']}。商品名称：{row['product_name']}。类别：{row['category']}。"
                f"面料：{row['fabric']}。版型：{row['fit']}。适合人群：{row['target_customer']}。"
                f"顾客标签：{row.get('customer_tags','')}。别名：{row.get('aliases','')}。"
                f"核心卖点：{row['selling_points']}。搭配建议：{row['styling_tips']}。"
                f"尺码提示：{row['size_notes']}。常见异议：{row['common_objection']}。"
                f"推荐话术：{row['suggested_script']}。禁止承诺：{row['forbidden_claims']}。"
                f"关联推荐：{row.get('recommendation_codes','')}。"
            )
            terms = [row['product_code'], row['product_name']] + [x.strip() for x in row.get('aliases','').split('|') if x.strip()]
            if lazy_pinyin:
                for term in list(terms):
                    if any('\u4e00' <= ch <= '\u9fff' for ch in term):
                        py = lazy_pinyin(term)
                        terms.extend([''.join(py), ''.join(x[0] for x in py if x)])
            self.product_search_terms[row['product_code'].upper()] = list(dict.fromkeys(t.lower() for t in terms if t))
            docs.append(Document(
                doc_id=f"product-{row['product_code']}", title=f"{row['product_name']}（{row['product_code']}）",
                doc_type="商品资料", version=row.get("version", "V1.0"), effective_date=row.get("effective_date", ""),
                expiry_date=row.get("expiry_date", ""), store_scope=row.get("store_scope", "ALL"), risk_level="low",
                source_section="商品知识卡", keywords=" ".join([row['product_code'], row['product_name'], row['category'], row['fabric'], row['fit'], row.get('aliases',''), row.get('customer_tags','')]),
                content=content,
            ))
        return docs

    @staticmethod
    def _is_active(doc: Document) -> bool:
        on_date = settings.active_date()
        try:
            from datetime import date
            if doc.effective_date and date.fromisoformat(doc.effective_date) > on_date:
                return False
            if doc.expiry_date and date.fromisoformat(doc.expiry_date) < on_date:
                return False
        except ValueError:
            return False
        return True

    @staticmethod
    def _keyword_overlap(query: str, doc: Document) -> float:
        query_tokens = set(TOKEN_PATTERN.findall(query.lower()))
        doc_tokens = set(TOKEN_PATTERN.findall((doc.keywords + " " + doc.title).lower()))
        if not query_tokens or not doc_tokens:
            return 0.0
        return len(query_tokens & doc_tokens) / math.sqrt(len(query_tokens) * len(doc_tokens))

    def search(self, query: str, *, top_k: int = 5, min_score: float = 0.055, store_id: str = "S001", allowed_doc_types: Iterable[str] | None = None) -> list[RetrievedDocument]:
        q_char = self.char_vectorizer.transform([query])
        q_word = self.word_vectorizer.transform([query])
        char_scores = cosine_similarity(q_char, self.char_matrix)[0]
        word_scores = cosine_similarity(q_word, self.word_matrix)[0]
        allowed = set(allowed_doc_types or [])
        results: list[RetrievedDocument] = []
        q_lower = query.lower()
        for idx, doc in enumerate(self.documents):
            if not self._is_active(doc):
                continue
            if doc.store_scope not in {"ALL", "全部门店", store_id}:
                continue
            if allowed and doc.doc_type not in allowed:
                continue
            keyword_score = self._keyword_overlap(query, doc)
            exact_boost = 0.0
            if doc.doc_id.startswith("product-"):
                code_upper = doc.doc_id.removeprefix("product-").upper()
                code = code_upper.lower()
                if code in q_lower:
                    exact_boost += 0.70
                for term in self.product_search_terms.get(code_upper, []):
                    if len(term) >= 2 and term in q_lower:
                        exact_boost += 0.32 if term != code else 0.0
                        break
            score = 0.50 * float(char_scores[idx]) + 0.27 * float(word_scores[idx]) + 0.23 * keyword_score + exact_boost
            if score >= min_score:
                results.append(RetrievedDocument(doc, round(score, 4)))
        results.sort(key=lambda item: (item.score, item.document.version), reverse=True)
        return results[:top_k]
