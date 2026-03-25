from datetime import date

from schemas import ObservationContext, SourceMeta, Version
from storage.repository import select_version_as_of


def test_select_version_as_of() -> None:
    source_meta = SourceMeta(jurisdiction="kr")
    versions = [
        Version(
            id="kr:000001:20230101-20230115-no-cur:version",
            law_id="kr:000001:law:root",
            official_law_id="000001",
            version_key="20230101-20230115-no-cur",
            promulgated_at=date(2023, 1, 1),
            effective_at=date(2023, 1, 15),
            source_meta=source_meta,
        ),
        Version(
            id="kr:000001:20240101-20240201-no-cur:version",
            law_id="kr:000001:law:root",
            official_law_id="000001",
            version_key="20240101-20240201-no-cur",
            promulgated_at=date(2024, 1, 1),
            effective_at=date(2024, 2, 1),
            source_meta=source_meta,
        ),
    ]

    selected = select_version_as_of(versions, date(2024, 3, 1))

    assert selected.version_key == "20240101-20240201-no-cur"


def test_select_version_as_of_before_first_effective_raises() -> None:
    source_meta = SourceMeta(jurisdiction="kr")
    versions = [
        Version(
            id="kr:000001:20240101-20240201-no-cur:version",
            law_id="kr:000001:law:root",
            official_law_id="000001",
            version_key="20240101-20240201-no-cur",
            promulgated_at=date(2024, 1, 1),
            effective_at=date(2024, 2, 1),
            source_meta=source_meta,
        )
    ]

    try:
        select_version_as_of(versions, date(2024, 1, 15))
    except LookupError as error:
        assert "no version available" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected LookupError")
