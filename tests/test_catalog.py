from app.catalog import BarcodeService, ensure_barcode_file


def test_existing_barcode_resolves_to_product():
    path = ensure_barcode_file()
    assert path.exists()
    service = BarcodeService()
    first_barcode = service.mappings.iloc[0]["barcode"]
    product_code = service.resolve(first_barcode)
    assert product_code
    assert product_code.startswith("FS-")


def test_unknown_barcode_returns_none():
    assert BarcodeService().resolve("6999999999998") is None
