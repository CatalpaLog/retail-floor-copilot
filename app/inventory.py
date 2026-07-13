from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import DATA_DIR

PRODUCT_CODE_RE = re.compile(r"\bFS-[A-Z]{2}-\d{3}\b", flags=re.I)
SIZE_RE = re.compile(r"(XXL|XL|XS|S|M|L)\s*码", flags=re.I)


@dataclass(frozen=True)
class InventoryItem:
    product_code: str
    store_id: str
    size: str
    stock_qty: int
    price: float
    promo_price: float
    transfer_days: int
    updated_at: str

    @property
    def status(self) -> str:
        if self.stock_qty <= 0:
            return "断货"
        if self.stock_qty <= 2:
            return "紧张"
        return "充足"


class InventoryService:
    def __init__(self, data_dir: Path | str = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.products = pd.read_csv(self.data_dir / "products.csv", dtype=str).fillna("")
        self.inventory = pd.read_csv(self.data_dir / "inventory.csv", dtype=str).fillna("")
        for col in ["stock_qty", "transfer_days"]:
            self.inventory[col] = pd.to_numeric(self.inventory[col], errors="coerce").fillna(0).astype(int)
        for col in ["price", "promo_price"]:
            self.inventory[col] = pd.to_numeric(self.inventory[col], errors="coerce").fillna(0.0)
        self._aliases = self._build_alias_map()

    def _build_alias_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for row in self.products.to_dict(orient="records"):
            code = row["product_code"].upper()
            mapping[code.lower()] = code
            mapping[row["product_name"].lower()] = code
            for alias in str(row.get("aliases", "")).split("|"):
                alias = alias.strip().lower()
                if alias:
                    mapping[alias] = code
        return mapping

    def extract_product_code(self, text: str) -> str | None:
        match = PRODUCT_CODE_RE.search(text)
        if match:
            return match.group(0).upper()
        q = text.lower().strip()
        candidates = sorted(self._aliases.items(), key=lambda item: len(item[0]), reverse=True)
        for alias, code in candidates:
            if len(alias) >= 2 and alias in q:
                return code
        return None

    @staticmethod
    def extract_size(text: str) -> str | None:
        clean = PRODUCT_CODE_RE.sub(" ", text.upper())
        match = SIZE_RE.search(clean)
        if match:
            return match.group(1).upper()
        match = re.search(r"(?:尺码|码数|有)\s*(XXL|XL|XS|S|M|L)(?![A-Z])", clean, flags=re.I)
        return match.group(1).upper() if match else None

    def product_row(self, product_code: str) -> dict | None:
        rows = self.products[self.products["product_code"].str.upper() == product_code.upper()]
        return rows.iloc[0].to_dict() if not rows.empty else None

    def rows_for_product(self, product_code: str, store_id: str | None = None) -> pd.DataFrame:
        rows = self.inventory[self.inventory["product_code"].str.upper() == product_code.upper()].copy()
        if store_id:
            rows = rows[rows["store_id"] == store_id]
        return rows.sort_values(["store_id", "size"])

    def lookup(self, product_code: str, store_id: str, size: str | None = None) -> dict:
        product = self.product_row(product_code)
        if not product:
            return {"found": False, "reason": "未找到对应商品"}
        local = self.rows_for_product(product_code, store_id)
        if size:
            local = local[local["size"].str.upper() == size.upper()]
        nearby = self.rows_for_product(product_code)
        nearby = nearby[nearby["store_id"] != store_id]
        if size:
            nearby = nearby[nearby["size"].str.upper() == size.upper()]
        local_records = [self._to_record(r) for _, r in local.iterrows()]
        nearby_records = [self._to_record(r) for _, r in nearby.sort_values("stock_qty", ascending=False).iterrows()]
        return {
            "found": True,
            "product": product,
            "local": local_records,
            "nearby": nearby_records,
            "updated_at": (local_records or nearby_records or [{}])[0].get("updated_at", ""),
        }

    @staticmethod
    def _to_record(row: pd.Series) -> dict:
        item = InventoryItem(
            product_code=str(row["product_code"]),
            store_id=str(row["store_id"]),
            size=str(row["size"]),
            stock_qty=int(row["stock_qty"]),
            price=float(row["price"]),
            promo_price=float(row["promo_price"]),
            transfer_days=int(row["transfer_days"]),
            updated_at=str(row["updated_at"]),
        )
        return {
            "product_code": item.product_code,
            "store_id": item.store_id,
            "size": item.size,
            "stock_qty": item.stock_qty,
            "status": item.status,
            "price": item.price,
            "promo_price": item.promo_price,
            "transfer_days": item.transfer_days,
            "updated_at": item.updated_at,
        }

    def answer_inventory_question(self, question: str, store_id: str) -> dict | None:
        code = self.extract_product_code(question)
        if not code:
            return None
        size = self.extract_size(question)
        data = self.lookup(code, store_id, size)
        if not data.get("found"):
            return None
        product = data["product"]
        local = data["local"]
        nearby = data["nearby"]
        price_terms = any(term in question for term in ["多少钱", "价格", "活动价", "售价"])
        stock_terms = any(term in question for term in ["库存", "有货", "仓库", "调货", "补货", "预留", "几天能到", "码"])
        if not (price_terms or stock_terms):
            return None

        if size:
            local_item = local[0] if local else None
            if local_item and local_item["stock_qty"] > 0:
                stock_text = f"{store_id}门店{size}码现有{local_item['stock_qty']}件，库存{local_item['status']}。"
                transfer = ""
            else:
                available = next((x for x in nearby if x["stock_qty"] > 0), None)
                stock_text = f"{store_id}门店{size}码当前断货。"
                transfer = (
                    f"{available['store_id']}门店有{available['stock_qty']}件，可申请调货，预计{max(1, available['transfer_days'])}天到店。"
                    if available else "附近门店也暂无可调库存。"
                )
        else:
            available_sizes = [f"{x['size']}码{x['stock_qty']}件" for x in local if x["stock_qty"] > 0]
            stock_text = f"{store_id}门店可售库存：" + ("、".join(available_sizes) if available_sizes else "当前无库存") + "。"
            transfer = ""

        price_item = (local or nearby or [{}])[0]
        price_text = ""
        if price_terms and price_item:
            price_text = f"当前标价¥{price_item.get('price', 0):.0f}，活动参考价¥{price_item.get('promo_price', 0):.0f}，最终以收银系统结算为准。"
        conclusion = f"{product['product_name']}（{code}）：{stock_text}{transfer}{price_text}".strip()
        script = f"“我帮您查到了，{stock_text}{transfer}需要的话我现在为您预留或发起调货。”"
        return {
            "conclusion": conclusion,
            "suggested_script": script,
            "conditions": f"库存更新时间：{data['updated_at']}；库存与价格以门店系统最终状态为准。",
            "warning": "不得在未锁定库存前承诺一定有货，也不得绕过收银系统承诺成交价。",
            "product_code": code,
        }

    def stock_summary(self, product_code: str, store_id: str) -> dict:
        data = self.lookup(product_code, store_id)
        if not data.get("found"):
            return data
        local_total = sum(x["stock_qty"] for x in data["local"])
        nearby_total = sum(x["stock_qty"] for x in data["nearby"])
        return {
            **data,
            "local_total": local_total,
            "nearby_total": nearby_total,
            "local_status": "断货" if local_total == 0 else "紧张" if local_total <= 3 else "充足",
        }

    def rank_by_availability(self, product_codes: Iterable[str], store_id: str) -> list[str]:
        scored = []
        for code in product_codes:
            summary = self.stock_summary(code, store_id)
            local = summary.get("local_total", 0)
            nearby = summary.get("nearby_total", 0)
            scored.append((1 if local > 0 else 0, local, nearby, code))
        scored.sort(reverse=True)
        return [x[-1] for x in scored]
