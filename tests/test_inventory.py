from app.inventory import InventoryService
from app.assistant import RetailAssistant


def test_inventory_lookup_by_code_and_size():
    service = InventoryService()
    result = service.lookup("FS-KZ-001", "S001", "M")
    assert result["found"] is True
    assert result["product"]["product_name"]
    assert all(x["size"] == "M" for x in result["local"])


def test_inventory_question_returns_live_result():
    payload = RetailAssistant().answer("FS-KZ-001的M码有货吗？", persist=False)
    assert "FS-KZ-001" in payload.conclusion
    assert "M码" in payload.conclusion
    assert payload.refused is False
    assert payload.product_code == "FS-KZ-001"
