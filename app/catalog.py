from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import DATA_DIR
from .db import audit_log, get_product_request, update_product_request

_WRITE_LOCK = threading.Lock()
PRODUCT_COLUMNS = [
    "product_code", "product_name", "category", "fabric", "fit", "target_customer", "customer_tags",
    "aliases", "selling_points", "styling_tips", "size_notes", "common_objection", "suggested_script",
    "forbidden_claims", "recommendation_codes", "version", "effective_date", "expiry_date", "store_scope",
]
RECOMMENDATION_COLUMNS = ["source_code", "source_name", "target_code", "target_name", "rank", "logic"]
RULE_COLUMNS = [
    "doc_id", "title", "doc_type", "version", "effective_date", "expiry_date", "store_scope", "risk_level",
    "source_section", "keywords", "content",
]


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def ensure_barcode_file(data_dir: Path | str = DATA_DIR) -> Path:
    data_dir = Path(data_dir)
    path = data_dir / "barcodes.csv"
    if path.exists():
        return path
    products = pd.read_csv(data_dir / "products.csv", dtype=str).fillna("")
    rows = []
    for idx, row in products.reset_index(drop=True).iterrows():
        rows.append({"barcode": str(6900000000000 + idx + 1), "product_code": row["product_code"], "status": "active"})
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


class BarcodeService:
    def __init__(self, data_dir: Path | str = DATA_DIR):
        self.data_dir = Path(data_dir)
        ensure_barcode_file(self.data_dir)
        self.reload()

    def reload(self) -> None:
        self.products = pd.read_csv(self.data_dir / "products.csv", dtype=str).fillna("")
        self.mappings = pd.read_csv(self.data_dir / "barcodes.csv", dtype=str).fillna("")
        self.codes = set(self.products["product_code"].str.upper())
        self.map = {
            str(r["barcode"]).strip(): str(r["product_code"]).upper()
            for _, r in self.mappings.iterrows()
            if str(r.get("status", "active")) == "active"
        }

    def resolve(self, raw_code: str) -> str | None:
        raw = str(raw_code).strip()
        if raw.upper() in self.codes:
            return raw.upper()
        return self.map.get(raw)

    def register(self, barcode: str, product_code: str, actor_id: int, data_dir: Path | str | None = None) -> None:
        data_dir = Path(data_dir or self.data_dir)
        path = ensure_barcode_file(data_dir)
        with _WRITE_LOCK:
            df = pd.read_csv(path, dtype=str).fillna("")
            mask = df["barcode"].astype(str) == str(barcode)
            row = {"barcode": str(barcode), "product_code": product_code.upper(), "status": "active"}
            if mask.any():
                df.loc[mask, list(row)] = list(row.values())
            else:
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_csv(path, index=False, encoding="utf-8-sig")
        self.reload()
        audit_log(actor_id, "登记商品条码", "barcode", str(barcode), after=row)


def load_products(data_dir: Path | str = DATA_DIR) -> pd.DataFrame:
    return pd.read_csv(Path(data_dir) / "products.csv", dtype=str).fillna("")


def save_products(df: pd.DataFrame, actor_id: int, action: str = "更新商品", data_dir: Path | str = DATA_DIR) -> None:
    path = Path(data_dir) / "products.csv"
    clean = df.copy()
    for col in PRODUCT_COLUMNS:
        if col not in clean:
            clean[col] = ""
    clean = clean[PRODUCT_COLUMNS].fillna("").astype(str)
    if clean["product_code"].duplicated().any():
        raise ValueError("商品编码不能重复")
    with _WRITE_LOCK:
        clean.to_csv(path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    audit_log(actor_id, action, "product_catalog", "products.csv", after={"row_count": len(clean)})


def save_recommendations(df: pd.DataFrame, actor_id: int, data_dir: Path | str = DATA_DIR) -> None:
    path = Path(data_dir) / "product_recommendations.csv"
    clean = df.copy()
    for col in RECOMMENDATION_COLUMNS:
        if col not in clean:
            clean[col] = ""
    clean = clean[RECOMMENDATION_COLUMNS].fillna("").astype(str)
    with _WRITE_LOCK:
        clean.to_csv(path, index=False, encoding="utf-8-sig")
    audit_log(actor_id, "更新连带推荐", "recommendation", "product_recommendations.csv", after={"row_count": len(clean)})


def publish_rule(rule: dict[str, Any], actor_id: int, data_dir: Path | str = DATA_DIR) -> str:
    path = Path(data_dir) / "knowledge_docs.csv"
    with _WRITE_LOCK:
        df = pd.read_csv(path, dtype=str).fillna("")
        doc_id = str(rule.get("doc_id") or f"rule-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
        row = {col: str(rule.get(col, "")) for col in RULE_COLUMNS}
        row["doc_id"] = doc_id
        if not row["effective_date"]:
            row["effective_date"] = _today()
        if not row["store_scope"]:
            row["store_scope"] = "ALL"
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
    audit_log(actor_id, "发布规则", "rule", doc_id, after=row)
    return doc_id


def append_inventory_stub(product_code: str, price: float, promo_price: float, data_dir: Path | str = DATA_DIR) -> None:
    path = Path(data_dir) / "inventory.csv"
    with _WRITE_LOCK:
        df = pd.read_csv(path, dtype=str).fillna("")
        if (df["product_code"].str.upper() == product_code.upper()).any():
            return
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for store_id in ["S001", "S002", "S003"]:
            for size in ["XS", "S", "M", "L", "XL"]:
                rows.append({
                    "product_code": product_code.upper(), "store_id": store_id, "size": size, "stock_qty": 0,
                    "price": price, "promo_price": promo_price, "transfer_days": 1, "updated_at": now,
                })
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")


def publish_product_request(
    request_id: int,
    actor_id: int,
    price: float,
    promo_price: float,
    version: str,
    effective_date: str,
    expiry_date: str,
    data_dir: Path | str = DATA_DIR,
) -> str:
    request = get_product_request(request_id)
    if not request:
        raise ValueError("新品建档申请不存在")
    if request["status"] not in {"待区域审核", "运营退回修改"}:
        raise ValueError("当前状态不可发布")
    required = ["proposed_product_code", "product_name", "category", "selling_points", "suggested_script", "forbidden_claims"]
    missing = [x for x in required if not str(request.get(x, "")).strip()]
    if missing:
        raise ValueError("缺少必填字段：" + "、".join(missing))
    product_code = request["proposed_product_code"].upper()
    df = load_products(data_dir)
    if (df["product_code"].str.upper() == product_code).any():
        raise ValueError("商品编码已存在")
    row = {
        "product_code": product_code,
        "product_name": request["product_name"],
        "category": request["category"],
        "fabric": request["fabric"],
        "fit": request["fit"],
        "target_customer": request["target_customer"],
        "customer_tags": request["customer_tags"],
        "aliases": request["aliases"],
        "selling_points": request["selling_points"],
        "styling_tips": request["styling_tips"],
        "size_notes": request["size_notes"],
        "common_objection": request["common_objection"],
        "suggested_script": request["suggested_script"],
        "forbidden_claims": request["forbidden_claims"],
        "recommendation_codes": "",
        "version": version,
        "effective_date": effective_date,
        "expiry_date": expiry_date,
        "store_scope": "ALL",
    }
    save_products(pd.concat([df, pd.DataFrame([row])], ignore_index=True), actor_id, action="发布新品", data_dir=data_dir)
    append_inventory_stub(product_code, price, promo_price, data_dir)
    BarcodeService(data_dir).register(request["scanned_code"], product_code, actor_id, data_dir)
    update_product_request(
        request_id,
        actor_id,
        {"status": "已发布", "regional_reviewer_id": actor_id, "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    )
    return product_code
