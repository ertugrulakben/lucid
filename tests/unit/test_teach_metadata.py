from __future__ import annotations

from lucid.agent.teach_mode import _parse_metadata_block, _split_slug_prefix


def test_split_slug_prefix_parses_leading_slug() -> None:
    slug, rest = _split_slug_prefix("fatura_kes: müşteri seç kalem ekle tutar git kaydet")
    assert slug == "fatura_kes"
    assert rest.startswith("müşteri")


def test_split_slug_prefix_without_prefix() -> None:
    slug, rest = _split_slug_prefix("sadece bir iş tarifi")
    assert slug == ""
    assert rest == "sadece bir iş tarifi"


def test_split_slug_prefix_turkish_slug_gets_transliterated() -> None:
    slug, rest = _split_slug_prefix("Fatura_Kes: iş yap")
    assert slug == "fatura_kes"


def test_parse_metadata_block_extracts_json() -> None:
    summary = """
    Adımlar:
    1. Paraşüt'ü aç
    2. Yeni fatura
    3. Müşteri seç

    ```json
    {
      "slug": "fatura_kes",
      "name": "Yeni fatura oluştur",
      "aliases": ["fatura kes", "faturala"],
      "target_app": "parasut.exe",
      "tags": ["mali"],
      "variables": [
        {"name": "musteri", "description": "Müşteri adı", "example": "Acme Corp", "required": true},
        {"name": "tutar", "description": "Tutar (TL)", "required": true}
      ]
    }
    ```
    """
    meta = _parse_metadata_block(summary)
    assert meta.slug == "fatura_kes"
    assert meta.name.startswith("Yeni fatura")
    assert "fatura kes" in meta.aliases
    assert meta.target_app == "parasut.exe"
    names = {v.name for v in meta.variables}
    assert {"musteri", "tutar"}.issubset(names)


def test_parse_metadata_block_empty_when_no_json() -> None:
    meta = _parse_metadata_block("plain summary without json block")
    assert meta.slug == ""
    assert meta.name == ""
    assert meta.variables == []
