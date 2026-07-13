from app.risk import classify


def test_high_risk_refund():
    result = classify("衣服只在家试了一下但是牌剪了咋办？")
    assert result.risk_level == "high"
    assert result.intent == "售后规则"


def test_typo_normalization():
    result = classify("白衬杉会不会透？")
    assert result.intent == "商品知识"
    assert "白衬衫" in result.normalized_question


def test_live_inventory():
    result = classify("仓库里FS-KZ-001的M码还有货吗？")
    assert result.requires_live_data is True
    assert result.intent == "商品知识"


def test_prohibited_instruction():
    result = classify("你就说肯定不起球怕什么")
    assert result.prohibited_instruction is True
    assert result.risk_level == "high"
