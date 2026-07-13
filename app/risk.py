from __future__ import annotations

from dataclasses import dataclass

from .schemas import Intent, RiskLevel


TYPO_MAP = {
    "白衬杉": "白衬衫", "牛子裤": "牛仔裤", "打低衫": "打底衫", "打低裤": "打底裤",
    "雪仿": "雪纺", "皮尤": "PU", "休身": "修身", "库子": "裤子", "锻面": "缎面",
    "羊戎": "羊毛", "卫群": "卫衣裙",
}

HIGH_RISK_TERMS = {
    "退款", "退货", "换货", "退换", "赔偿", "投诉", "差价", "价签", "标价", "价格争议",
    "活动叠加", "优惠叠加", "叠加", "会员权益", "积分", "特殊处理", "破例", "过期",
    "吊牌", "牌剪", "牌子剪", "穿过", "洗过", "质量问题", "小票", "凭证", "12315", "差评", "纠纷", "受伤",
    "现金退款", "调包", "媒体曝光", "绝对", "肯定", "全国门店", "别让店长", "就说", "拼单", "能不能一起", "能不能叠", "承诺补发", "提前开单", "额外打折", "拆单", "买了快", "能换", "能退", "香水味", "吵着", "皮肤过敏",
    "多送", "私下", "不退不换", "价保", "补差", "员工内购", "赠品", "改价",
    "审批", "团购", "替顾客用内购", "多给个折扣", "拼个单", "缩水超过",
}
MEDIUM_RISK_TERMS = {
    "优惠", "折扣", "满减", "会员", "活动", "机洗", "水洗", "甩干", "皱", "偏大", "偏小", "掉皮", "扎人", "掉毛", "材质", "面料", "尺码", "成分", "起球", "缩水",
    "掉色", "洗涤", "护理", "收银系统", "旧活动", "新旧规则", "过敏", "色差", "勾丝",
}
LIVE_DATA_TERMS = {
    "有货", "库存", "仓库", "放哪", "哪个区", "第几层", "多少钱", "当前价格", "活动价多少", "线上比店里便宜", "调货", "补货",
    "预留", "几天能到", "排班", "工资", "提成", "钥匙", "遥控器", "POS机", "收银机",
    "物业费", "员工餐", "客服台", "工牌", "今天几点上班", "明天休息", "发票抬头",
}
PROHIBITED_INSTRUCTION_TERMS = {
    "就说", "别让店长知道", "反正顾客不知道", "直接答应", "悄悄", "怕什么", "推给店长",
    "顾客又不懂", "普通人摸不出来", "不会较真", "又不用你担责",
}
OUT_OF_DOMAIN_TERMS = {"股票", "天气", "写诗", "彩票", "新闻", "治疗", "颈椎", "隔壁品牌卖得", "物业费", "员工餐", "客服台"}

INTENT_TERMS: dict[Intent, set[str]] = {
    "售后规则": {"退", "换", "售后", "吊牌", "牌剪", "牌子剪", "退款", "退钱", "小票", "凭证", "质量问题", "维修", "色差", "起球算质量", "穿过", "洗过", "买了", "缩水严重", "缩水超过", "原账户", "香水味", "运费", "全款"},
    "投诉处理": {"投诉", "生气", "差评", "赔偿", "12315", "争议", "纠纷", "争执", "受伤", "媒体", "医院", "过敏", "吵"},
    "活动会员": {"活动", "优惠", "折扣", "打折", "额外", "满减", "会员", "积分", "叠加", "券", "赠品", "礼品", "补发", "内购", "价保", "补差", "团购", "储值", "新会员", "生日月", "金卡", "银卡", "发票", "凑单", "拆单", "秒杀", "开单"},
    "搭配话术": {"搭配", "配什么", "怎么说", "话术", "嫌贵", "显瘦", "显白", "显胖", "显老", "压个子", "犹豫", "推荐", "适合", "好看", "面试穿", "婚礼", "身材"},
    "商品知识": {"商品", "衣服", "纯羊毛", "面料", "材质", "版型", "尺码", "洗涤", "护理", "机洗", "水洗", "甩干", "外套", "开衫", "裤", "裙", "衬衫", "针织", "西装", "T恤", "羽绒", "大衣", "风衣", "打底", "起球", "缩水", "掉色", "卖点", "成分", "防水", "透", "热", "透气", "扎", "静电", "领口", "口袋", "拉链", "扣子", "腰带", "帽子", "勾丝"},
    "其他": set(),
}


@dataclass(frozen=True)
class Classification:
    intent: Intent
    risk_level: RiskLevel
    matched_risk_terms: tuple[str, ...]
    requires_live_data: bool = False
    prohibited_instruction: bool = False
    normalized_question: str = ""


def normalize(question: str) -> str:
    q = question.strip()
    for wrong, right in TYPO_MAP.items():
        q = q.replace(wrong, right)
    return q


def classify(question: str) -> Classification:
    normalized = normalize(question)
    q = normalized.lower()
    if any(term.lower() in q for term in OUT_OF_DOMAIN_TERMS):
        return Classification("其他", "low", (), False, False, normalized)

    prohibited = any(term.lower() in q for term in PROHIBITED_INSTRUCTION_TERMS)
    requires_live = any(term.lower() in q for term in LIVE_DATA_TERMS)
    high_hits = tuple(sorted(term for term in HIGH_RISK_TERMS if term.lower() in q))
    medium_hits = tuple(sorted(term for term in MEDIUM_RISK_TERMS if term.lower() in q))
    risk: RiskLevel = "high" if (high_hits or prohibited) else "medium" if medium_hits else "low"

    scores = {intent: sum(1 for term in terms if term.lower() in q) for intent, terms in INTENT_TERMS.items()}
    styling_specific = {"搭配", "配什么", "怎么说", "话术", "嫌贵", "显瘦", "显白", "显胖", "显老", "压个子", "犹豫", "面试穿", "婚礼"}
    aftersales_context = any(term in q for term in ["怎么处理", "怎么办", "能不能退", "能不能换", "质量问题", "缩水超过", "洗坏", "售后"])
    activity_context = any(term in q for term in ["活动", "优惠", "折扣", "满减", "会员", "积分", "价签", "系统价格", "团购", "内购", "凑单", "拼单", "拼个单"])

    if scores["投诉处理"] > 0:
        intent: Intent = "投诉处理"
    elif aftersales_context and scores["售后规则"] > 0:
        intent = "售后规则"
    elif activity_context and scores["活动会员"] > 0:
        intent = "活动会员"
    elif any(term in q for term in styling_specific):
        intent = "搭配话术"
    elif scores["售后规则"] > 0:
        intent = "售后规则"
    elif scores["活动会员"] > 0:
        intent = "活动会员"
    elif scores["商品知识"] > 0:
        intent = "商品知识"
    elif scores["搭配话术"] > 0:
        intent = "搭配话术"
    else:
        intent = "其他"

    # A live inventory/price question may still belong to product or activity intent.
    import re
    if re.search(r"\bFS-[A-Z]{2}-\d{3}\b", normalized, flags=re.I):
        intent = "商品知识"
    if re.search(r"有[XSML]{1,3}码", normalized, flags=re.I):
        requires_live = True
    if requires_live:
        if any(t in q for t in ["多少钱", "当前价格", "活动价多少", "多少折扣"]):
            intent = "活动会员"
        elif intent == "其他" and any(t in q for t in ["库存", "仓库", "有货", "调货", "补货", "预留", "放哪", "第几层"]):
            intent = "商品知识"

    return Classification(intent, risk, high_hits or medium_hits, requires_live, prohibited, normalized)
