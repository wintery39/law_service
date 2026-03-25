from pydantic import ValidationError

from schemas import CorpusBundle, Law, SourceMeta, Unit, UnitType, Version


def test_corpus_bundle_schema_validation() -> None:
    source_meta = SourceMeta(jurisdiction="kr", promulgation_number="12345")
    version = Version(
        id="kr:000001:20240101-20240101-12345-cur:version",
        law_id="kr:000001:law:root",
        official_law_id="000001",
        version_key="20240101-20240101-12345-cur",
        source_meta=source_meta,
    )
    law = Law(
        id="kr:000001:law:root",
        official_law_id="000001",
        name_ko="테스트법",
        source_meta=source_meta,
        version_ids=[version.id],
        latest_version_id=version.id,
    )
    unit = Unit(
        id="kr:000001:20240101-20240101-12345-cur:article-000100",
        law_id=law.id,
        version_id=version.id,
        version_key=version.version_key,
        unit_path="article-000100",
        unit_type=UnitType.ARTICLE,
        unit_number="000100",
    )

    bundle = CorpusBundle(law=law, versions=[version], units=[unit], references=[])

    assert bundle.law.id == "kr:000001:law:root"


def test_invalid_internal_id_rejected() -> None:
    source_meta = SourceMeta(jurisdiction="kr")

    try:
        Version(
            id="invalid-id",
            law_id="kr:000001:law:root",
            official_law_id="000001",
            version_key="20240101-20240101-no-cur",
            source_meta=source_meta,
        )
    except ValidationError as error:
        assert "jurisdiction:law_id:version_key:unit_path" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected schema validation to fail")
