from app.retrieval import HybridRetriever


def test_product_code_exact_match():
    results = HybridRetriever().search("FS-KZ-001这条裤子有什么卖点？")
    assert results
    assert "FS-KZ-001" in results[0].document.title


def test_alias_match():
    results = HybridRetriever().search("白衬杉会不会透？", allowed_doc_types={"商品资料"})
    assert results
    assert "经典修身免烫白衬衫" in results[0].document.title


def test_policy_retrieval():
    results = HybridRetriever().search("会员折扣和活动能不能叠加？", allowed_doc_types={"活动规则"})
    assert results
    assert "促销" in results[0].document.title or "活动" in results[0].document.title
