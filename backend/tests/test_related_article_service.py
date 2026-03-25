from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from graph import InMemoryGraphStore
from main import app, container
from schemas import (
    CorpusBundle,
    Law,
    ObservationContext,
    Reference,
    ReferenceType,
    RelatedArticleRequest,
    SourceMeta,
    Unit,
    UnitType,
    UserProfile,
    Version,
)
from search import (
    GoldExpectation,
    GoldScenario,
    GoldSet,
    InMemoryTextSearchStore,
    RelatedArticleFinderService,
    RelatedArticleFinderSettings,
    SchemaFillingLLM,
    StructuredCaseService,
)
from storage import (
    InMemoryCorpusRepository,
    InMemoryVectorStore,
    build_internal_id,
    build_law_id,
    build_reference_id,
    build_version_id,
    build_version_key,
)


@dataclass(frozen=True)
class ArticleSpec:
    alias: str
    unit_number: str
    heading: str
    body_text: str


@dataclass(frozen=True)
class VersionSpec:
    alias: str
    promulgated_at: date
    effective_at: date
    promulgation_number: str
    history_code: str
    chapter_heading: str
    chapter_body: str
    articles: list[ArticleSpec]
    is_repealed: bool = False
    repealed_at: date | None = None


@dataclass(frozen=True)
class ReferenceSpec:
    source_alias: str
    target_alias: str
    reference_type: ReferenceType
    raw_text: str


@dataclass
class SeededRelatedArticleFixture:
    repository: InMemoryCorpusRepository
    graph_store: InMemoryGraphStore
    text_search_store: InMemoryTextSearchStore
    vector_store: InMemoryVectorStore
    service: RelatedArticleFinderService
    ids: dict[str, str]


def build_context() -> ObservationContext:
    return ObservationContext(
        request_id="req-related-articles",
        corpus_version="gold-v1",
        ingestion_run_id="ing-related-articles",
    )


def build_law_bundle(
    *,
    jurisdiction: str,
    official_law_id: str,
    law_name: str,
    version_specs: list[VersionSpec],
    reference_specs: list[ReferenceSpec] | None = None,
) -> tuple[CorpusBundle, dict[str, str]]:
    law_id = build_law_id(jurisdiction, official_law_id)
    versions: list[Version] = []
    units: list[Unit] = []
    references: list[Reference] = []
    ids: dict[str, str] = {}
    unit_meta: dict[str, dict[str, str]] = {}

    for version_index, spec in enumerate(version_specs, start=1):
        version_key = build_version_key(
            spec.promulgated_at,
            spec.effective_at,
            spec.promulgation_number,
            spec.history_code,
        )
        version_id = build_version_id(jurisdiction, official_law_id, version_key)
        source_meta = SourceMeta(
            jurisdiction=jurisdiction,
            promulgation_number=spec.promulgation_number,
            promulgated_at=spec.promulgated_at,
            status_name="폐지" if spec.is_repealed else "현행",
        )
        version = Version(
            id=version_id,
            law_id=law_id,
            official_law_id=official_law_id,
            version_key=version_key,
            promulgated_at=spec.promulgated_at,
            effective_at=spec.effective_at,
            repealed_at=spec.repealed_at,
            is_repealed=spec.is_repealed,
            history_code=spec.history_code,
            source_meta=source_meta,
        )
        versions.append(version)

        chapter_path = f"chapter-{version_index:02d}"
        chapter_id = build_internal_id(jurisdiction, official_law_id, version_key, chapter_path)
        units.append(
            Unit(
                id=chapter_id,
                law_id=law_id,
                version_id=version_id,
                version_key=version_key,
                unit_path=chapter_path,
                unit_type=UnitType.CHAPTER,
                unit_number=str(version_index),
                heading=spec.chapter_heading,
                body_text=spec.chapter_body,
                order_index=version_index * 100,
                effective_at=spec.effective_at,
            )
        )

        for article_index, article in enumerate(spec.articles, start=1):
            unit_path = f"article-{article.unit_number}"
            unit_id = build_internal_id(jurisdiction, official_law_id, version_key, unit_path)
            units.append(
                Unit(
                    id=unit_id,
                    law_id=law_id,
                    version_id=version_id,
                    version_key=version_key,
                    unit_path=unit_path,
                    unit_type=UnitType.ARTICLE,
                    unit_number=article.unit_number,
                    heading=article.heading,
                    body_text=article.body_text,
                    parent_id=chapter_id,
                    order_index=version_index * 100 + article_index,
                    effective_at=spec.effective_at,
                )
            )
            ids[article.alias] = unit_id
            unit_meta[article.alias] = {
                "law_id": law_id,
                "version_id": version_id,
                "version_key": version_key,
                "unit_path": unit_path,
            }

    latest_version = max(
        versions,
        key=lambda item: (item.effective_at or date.min, item.promulgated_at or date.min, item.version_key),
    )
    law = Law(
        id=law_id,
        jurisdiction=jurisdiction,
        official_law_id=official_law_id,
        name_ko=law_name,
        source_meta=versions[-1].source_meta,
        version_ids=[version.id for version in versions],
        latest_version_id=latest_version.id,
    )

    for reference_spec in reference_specs or []:
        source = unit_meta[reference_spec.source_alias]
        target = unit_meta[reference_spec.target_alias]
        references.append(
            Reference(
                id=build_reference_id(
                    jurisdiction,
                    official_law_id,
                    source["version_key"],
                    source["unit_path"],
                    reference_spec.raw_text,
                ),
                source_unit_id=ids[reference_spec.source_alias],
                source_law_id=law_id,
                version_id=source["version_id"],
                reference_type=reference_spec.reference_type,
                raw_text=reference_spec.raw_text,
                normalized_citation=reference_spec.raw_text,
                target_law_id=target["law_id"],
                target_unit_id=ids[reference_spec.target_alias],
            )
        )

    return CorpusBundle(law=law, versions=versions, units=units, references=references), ids


def seed_related_article_fixture(
    *,
    operational_mode: bool = False,
    structuring_service: StructuredCaseService | None = None,
) -> SeededRelatedArticleFixture:
    repository = InMemoryCorpusRepository()
    graph_store = InMemoryGraphStore()
    text_search_store = InMemoryTextSearchStore()
    vector_store = InMemoryVectorStore()
    context = build_context()
    ids: dict[str, str] = {}

    bundles: list[CorpusBundle] = []

    criminal_bundle, criminal_ids = build_law_bundle(
        jurisdiction="kr",
        official_law_id="100001",
        law_name="형법",
        version_specs=[
            VersionSpec(
                alias="criminal_v1",
                promulgated_at=date(2023, 1, 1),
                effective_at=date(2023, 1, 1),
                promulgation_number="1001",
                history_code="cur",
                chapter_heading="형사 일반",
                chapter_body="폭행 상해 절도 관련 조문",
                articles=[
                    ArticleSpec(
                        alias="criminal_assault",
                        unit_number="000100",
                        heading="폭행",
                        body_text="사람의 신체나 피해자를 폭행하거나 상해를 입힌 자를 처벌한다. 폭행 상해 피해자 신체.",
                    ),
                    ArticleSpec(
                        alias="criminal_theft",
                        unit_number="000110",
                        heading="절도",
                        body_text="타인의 재물 또는 물건을 절취한 자는 절도죄로 처벌한다. 절도 재물 물건.",
                    ),
                ],
            )
        ],
    )
    bundles.append(criminal_bundle)
    ids.update(criminal_ids)

    military_bundle, military_ids = build_law_bundle(
        jurisdiction="kr",
        official_law_id="100002",
        law_name="군사보안법",
        version_specs=[
            VersionSpec(
                alias="military_v1",
                promulgated_at=date(2023, 2, 1),
                effective_at=date(2023, 2, 1),
                promulgation_number="1002",
                history_code="cur",
                chapter_heading="군특수범",
                chapter_body="기밀 유출 무단촬영 군용물 무단반출",
                articles=[
                    ArticleSpec(
                        alias="military_secret",
                        unit_number="000300",
                        heading="군사기밀 유출 및 무단촬영",
                        body_text="군인 또는 병사가 기밀 자료나 문서를 유출하거나 보안구역에서 사진을 무단촬영한 경우 처벌한다. 기밀 문서 유출 보안구역 무단촬영.",
                    ),
                    ArticleSpec(
                        alias="military_property",
                        unit_number="000310",
                        heading="군용물 무단반출",
                        body_text="부대 창고의 군용물 또는 장비를 무단반출한 자를 처벌한다. 군용물 무단반출 창고 부대.",
                    ),
                ],
            )
        ],
        reference_specs=[
            ReferenceSpec(
                source_alias="military_secret",
                target_alias="military_property",
                reference_type=ReferenceType.RELATED,
                raw_text="기밀 유출과 군용물 무단반출은 관련 절차를 함께 검토한다.",
            )
        ],
    )
    bundles.append(military_bundle)
    ids.update(military_ids)

    discipline_bundle, discipline_ids = build_law_bundle(
        jurisdiction="kr",
        official_law_id="100003",
        law_name="군복무규율",
        version_specs=[
            VersionSpec(
                alias="discipline_v1",
                promulgated_at=date(2023, 3, 1),
                effective_at=date(2023, 3, 1),
                promulgation_number="1003",
                history_code="cur",
                chapter_heading="복무규율",
                chapter_body="근무지 이탈 명령거부 징계",
                articles=[
                    ArticleSpec(
                        alias="discipline_absence",
                        unit_number="000400",
                        heading="근무지이탈 금지",
                        body_text="병사나 군인이 상관의 허가 없이 근무지 또는 생활관을 이탈하면 징계한다. 근무지 이탈 생활관 상관 징계.",
                    ),
                    ArticleSpec(
                        alias="discipline_order",
                        unit_number="000410",
                        heading="명령거부 금지",
                        body_text="지휘관 또는 상관의 정당한 명령을 거부한 자는 징계한다. 명령거부 명령 상관 지휘관 징계.",
                    ),
                ],
            )
        ],
        reference_specs=[
            ReferenceSpec(
                source_alias="discipline_absence",
                target_alias="discipline_order",
                reference_type=ReferenceType.RELATED,
                raw_text="근무지이탈 사건은 명령거부 여부를 함께 본다.",
            )
        ],
    )
    bundles.append(discipline_bundle)
    ids.update(discipline_ids)

    administrative_bundle, administrative_ids = build_law_bundle(
        jurisdiction="kr",
        official_law_id="100004",
        law_name="행정절차법",
        version_specs=[
            VersionSpec(
                alias="admin_v1",
                promulgated_at=date(2023, 1, 1),
                effective_at=date(2023, 1, 1),
                promulgation_number="1004",
                history_code="v1",
                chapter_heading="행정처분 절차",
                chapter_body="행정처분 사전통지 의견제출",
                articles=[
                    ArticleSpec(
                        alias="admin_notice_v1",
                        unit_number="000500",
                        heading="처분의 사전통지",
                        body_text="행정청이 불이익처분을 하려면 처분의 제목, 원인, 법적 근거와 의견제출 기한을 사전통지하여야 한다. 행정처분 사전통지 의견제출 기한.",
                    ),
                    ArticleSpec(
                        alias="admin_opinion_v1",
                        unit_number="000510",
                        heading="의견제출",
                        body_text="민원인 또는 당사자는 행정처분 전에 의견제출을 할 수 있다. 의견제출 민원인 처분.",
                    ),
                ],
            ),
            VersionSpec(
                alias="admin_v2",
                promulgated_at=date(2024, 7, 1),
                effective_at=date(2024, 7, 1),
                promulgation_number="1005",
                history_code="v2",
                chapter_heading="행정처분 절차",
                chapter_body="행정처분 사전통지 청문 의견제출",
                articles=[
                    ArticleSpec(
                        alias="admin_notice_v2",
                        unit_number="000500",
                        heading="처분의 사전통지",
                        body_text="행정청이 불이익처분을 하려면 처분 사전통지와 청문 또는 의견제출 기회를 충분히 보장하여야 한다. 행정처분 사전통지 청문 의견제출.",
                    ),
                    ArticleSpec(
                        alias="admin_opinion_v2",
                        unit_number="000510",
                        heading="의견제출 및 청문",
                        body_text="민원인 또는 당사자는 처분 전에 의견제출과 청문을 신청할 수 있다. 청문 의견제출 민원인 처분.",
                    ),
                ],
            ),
        ],
        reference_specs=[
            ReferenceSpec(
                source_alias="admin_notice_v1",
                target_alias="admin_opinion_v1",
                reference_type=ReferenceType.RELATED,
                raw_text="사전통지 후 의견제출 절차가 이어진다.",
            ),
            ReferenceSpec(
                source_alias="admin_notice_v2",
                target_alias="admin_opinion_v2",
                reference_type=ReferenceType.RELATED,
                raw_text="사전통지 후 청문 및 의견제출 절차가 이어진다.",
            ),
        ],
    )
    bundles.append(administrative_bundle)
    ids.update(administrative_ids)

    civil_bundle, civil_ids = build_law_bundle(
        jurisdiction="kr",
        official_law_id="100005",
        law_name="민법",
        version_specs=[
            VersionSpec(
                alias="civil_v1",
                promulgated_at=date(2023, 4, 1),
                effective_at=date(2023, 4, 1),
                promulgation_number="1006",
                history_code="cur",
                chapter_heading="손해배상",
                chapter_body="손해배상 재산손해 불법행위",
                articles=[
                    ArticleSpec(
                        alias="civil_damage",
                        unit_number="000600",
                        heading="불법행위 손해배상",
                        body_text="고의 또는 과실로 타인에게 손해를 가한 자는 손해배상 책임을 진다. 손해배상 손해 고의 과실.",
                    ),
                    ArticleSpec(
                        alias="civil_property",
                        unit_number="000610",
                        heading="재산손해 배상범위",
                        body_text="재산상 손해, 파손된 재물 또는 물건에 대한 배상 범위를 정한다. 재산손해 파손 재물 물건 배상.",
                    ),
                ],
            )
        ],
        reference_specs=[
            ReferenceSpec(
                source_alias="civil_damage",
                target_alias="civil_property",
                reference_type=ReferenceType.RELATED,
                raw_text="손해배상 범위는 재산손해 조문을 함께 본다.",
            )
        ],
    )
    bundles.append(civil_bundle)
    ids.update(civil_ids)

    repealed_bundle, repealed_ids = build_law_bundle(
        jurisdiction="kr",
        official_law_id="100006",
        law_name="구 행정처분 특별법",
        version_specs=[
            VersionSpec(
                alias="repealed_admin_v1",
                promulgated_at=date(2022, 1, 1),
                effective_at=date(2022, 1, 1),
                promulgation_number="1007",
                history_code="old",
                chapter_heading="폐지된 처분 절차",
                chapter_body="처분 통지 사전통지 의견제출",
                articles=[
                    ArticleSpec(
                        alias="repealed_notice",
                        unit_number="000700",
                        heading="폐지된 처분 통지",
                        body_text="행정청의 처분 통지는 사전통지와 의견제출 절차를 따른다. 처분 통지 사전통지 의견제출.",
                    )
                ],
                is_repealed=True,
                repealed_at=date(2024, 1, 1),
            )
        ],
    )
    bundles.append(repealed_bundle)
    ids.update(repealed_ids)

    foreign_bundle, foreign_ids = build_law_bundle(
        jurisdiction="us",
        official_law_id="200001",
        law_name="US Administrative Notice Act",
        version_specs=[
            VersionSpec(
                alias="foreign_admin_v1",
                promulgated_at=date(2023, 5, 1),
                effective_at=date(2023, 5, 1),
                promulgation_number="2001",
                history_code="cur",
                chapter_heading="Administrative notice",
                chapter_body="행정처분 사전통지 의견제출",
                articles=[
                    ArticleSpec(
                        alias="foreign_notice",
                        unit_number="000800",
                        heading="Administrative notice",
                        body_text="행정청 처분 사전통지 의견제출 절차를 설명한다. 행정처분 사전통지 의견제출.",
                    )
                ],
            )
        ],
    )
    bundles.append(foreign_bundle)
    ids.update(foreign_ids)

    for bundle in bundles:
        repository.upsert_bundle(bundle, context)
        graph_store.upsert_units(bundle.units, context)
        graph_store.upsert_references(bundle.references, context)
        text_search_store.index_units(bundle.units, context)
        vector_store.upsert_units(bundle.units, context)

    service = RelatedArticleFinderService(
        repository=repository,
        graph_store=graph_store,
        text_search_store=text_search_store,
        vector_store=vector_store,
        structuring_service=structuring_service,
        settings=RelatedArticleFinderSettings(
            operational_mode=operational_mode,
            top_k=8,
            top_n=5,
        ),
    )
    return SeededRelatedArticleFixture(
        repository=repository,
        graph_store=graph_store,
        text_search_store=text_search_store,
        vector_store=vector_store,
        service=service,
        ids=ids,
    )


def build_gold_set(ids: dict[str, str]) -> GoldSet:
    return GoldSet(
        scenarios=[
            GoldScenario(
                name="clarify_empty",
                request=RelatedArticleRequest(session_id="s-empty", user_text="관련 조항이 궁금합니다."),
                expectation=GoldExpectation(
                    expected_type="clarify",
                    expected_missing_slots=["actors", "actions", "objects", "time", "place"],
                ),
            ),
            GoldScenario(
                name="clarify_assault_missing_object",
                request=RelatedArticleRequest(
                    session_id="s-assault",
                    user_text="병사가 생활관에서 폭행했습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="clarify",
                    expected_missing_slots=["objects", "time"],
                ),
            ),
            GoldScenario(
                name="assault_followup_result",
                request=RelatedArticleRequest(
                    session_id="s-assault",
                    user_text="피해자 신체를 다치게 했고 2024-03-01 일이었습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["criminal"],
                    expected_final_ids=[ids["criminal_assault"]],
                ),
            ),
            GoldScenario(
                name="theft_result",
                request=RelatedArticleRequest(
                    session_id="s-theft",
                    user_text="군인이 부대 창고에서 재물을 절도했습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["criminal"],
                    expected_final_ids=[ids["criminal_theft"]],
                ),
            ),
            GoldScenario(
                name="military_secret_result",
                request=RelatedArticleRequest(
                    session_id="s-military-secret",
                    user_text="병사가 보안구역에서 기밀 문서를 유출했습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["military_special"],
                    expected_final_ids=[ids["military_secret"]],
                ),
            ),
            GoldScenario(
                name="military_photo_result",
                request=RelatedArticleRequest(
                    session_id="s-military-photo",
                    user_text="군인이 보안구역에서 사진을 무단촬영했습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["military_special"],
                    expected_final_ids=[ids["military_secret"]],
                ),
            ),
            GoldScenario(
                name="military_property_with_profile",
                request=RelatedArticleRequest(
                    session_id="s-military-property",
                    user_text="부대 창고에서 군용물을 무단 반출했습니다.",
                    user_profile=UserProfile(role="병사", rank="상병", organization="1중대"),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["military_special"],
                    expected_final_ids=[ids["military_property"]],
                ),
            ),
            GoldScenario(
                name="disciplinary_absence_result",
                request=RelatedArticleRequest(
                    session_id="s-discipline-absence",
                    user_text="병사가 상관 허가 없이 근무지를 이탈했습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["disciplinary"],
                    expected_final_ids=[ids["discipline_absence"], ids["discipline_order"]],
                ),
            ),
            GoldScenario(
                name="disciplinary_order_result",
                request=RelatedArticleRequest(
                    session_id="s-discipline-order",
                    user_text="지휘관의 명령을 거부한 병사에 대한 징계가 궁금합니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["disciplinary"],
                    expected_final_ids=[ids["discipline_order"]],
                ),
            ),
            GoldScenario(
                name="administrative_notice_old_result",
                request=RelatedArticleRequest(
                    session_id="s-admin-notice",
                    user_text="행정청이 민원인에게 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
                    as_of_date=date(2024, 3, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["administrative"],
                    expected_final_ids=[ids["admin_notice_v1"], ids["admin_opinion_v1"]],
                ),
            ),
            GoldScenario(
                name="administrative_opinion_old_result",
                request=RelatedArticleRequest(
                    session_id="s-admin-opinion",
                    user_text="민원인이 행정처분 전에 의견제출을 하고 싶습니다.",
                    as_of_date=date(2024, 3, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["administrative"],
                    expected_final_ids=[ids["admin_opinion_v1"], ids["admin_notice_v1"]],
                ),
            ),
            GoldScenario(
                name="civil_damage_result",
                request=RelatedArticleRequest(
                    session_id="s-civil-damage",
                    user_text="가해자의 고의로 재산 손해가 발생해 피해자가 손해배상을 청구하려고 합니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["civil"],
                    expected_final_ids=[ids["civil_damage"], ids["civil_property"]],
                ),
            ),
            GoldScenario(
                name="civil_property_result",
                request=RelatedArticleRequest(
                    session_id="s-civil-property",
                    user_text="파손된 재물에 대한 배상이 가능한지 궁금합니다. 피해자와 가해자가 있습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["civil"],
                    expected_final_ids=[ids["civil_property"], ids["civil_damage"]],
                ),
            ),
            GoldScenario(
                name="admin_as_of_old_version",
                request=RelatedArticleRequest(
                    session_id="s-admin-old-version",
                    user_text="행정청이 불이익 처분 전에 의견제출 기한을 사전통지하지 않았습니다.",
                    as_of_date=date(2024, 3, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["administrative"],
                    expected_final_ids=[ids["admin_notice_v1"]],
                ),
            ),
            GoldScenario(
                name="admin_as_of_new_version",
                request=RelatedArticleRequest(
                    session_id="s-admin-new-version",
                    user_text="행정청이 불이익 처분 전에 청문 기회를 보장하지 않았습니다.",
                    as_of_date=date(2024, 8, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["administrative"],
                    expected_final_ids=[ids["admin_notice_v2"]],
                ),
            ),
            GoldScenario(
                name="repealed_filtered_admin",
                request=RelatedArticleRequest(
                    session_id="s-admin-repealed",
                    user_text="행정청의 처분 사전통지 절차가 궁금합니다.",
                    as_of_date=date(2024, 3, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["administrative"],
                    expected_final_ids=[ids["admin_notice_v1"]],
                ),
            ),
            GoldScenario(
                name="clarify_admin_missing_actor",
                request=RelatedArticleRequest(
                    session_id="s-admin-clarify",
                    user_text="처분 사전통지 관련 조항이 궁금합니다.",
                    as_of_date=date(2024, 3, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="clarify",
                    expected_missing_slots=["actors", "time", "place"],
                ),
            ),
            GoldScenario(
                name="admin_followup_after_clarify",
                request=RelatedArticleRequest(
                    session_id="s-admin-clarify",
                    user_text="행정청이 민원인에게 한 불이익 처분입니다.",
                    as_of_date=date(2024, 3, 1),
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["administrative"],
                    expected_final_ids=[ids["admin_notice_v1"]],
                ),
            ),
            GoldScenario(
                name="clarify_military_missing_actor",
                request=RelatedArticleRequest(
                    session_id="s-military-clarify",
                    user_text="기밀 유출이 있었어요.",
                ),
                expectation=GoldExpectation(
                    expected_type="clarify",
                    expected_missing_slots=["actors", "time", "place"],
                ),
            ),
            GoldScenario(
                name="military_followup_after_clarify",
                request=RelatedArticleRequest(
                    session_id="s-military-clarify",
                    user_text="병사가 보안구역에서 기밀 문서를 유출했습니다.",
                ),
                expectation=GoldExpectation(
                    expected_type="result",
                    expected_route_labels=["military_special"],
                    expected_final_ids=[ids["military_secret"]],
                ),
            ),
        ]
    )


class InvalidThenValidSchemaLLM(SchemaFillingLLM):
    def __init__(self) -> None:
        self.calls = 0

    async def fill_case(
        self,
        request: RelatedArticleRequest,
        partial_case,
        prompt: str,
        schema: dict[str, Any],
        context: ObservationContext,
    ) -> dict[str, Any]:
        _ = partial_case, prompt, schema, context
        self.calls += 1
        if self.calls == 1:
            return {
                "session_id": request.session_id,
                "narrative": request.user_text,
                "actors": "invalid-actors",
            }
        return {
            "session_id": request.session_id,
            "narrative": request.user_text,
            "jurisdiction": "kr",
            "actors": [{"role": "병사"}],
            "actions": [{"verb": "절도", "description": "절도"}],
            "objects": [{"name": "재물", "category": "property"}],
            "keyphrases": ["절도", "재물"],
            "legal_terms": ["절도"],
        }


async def test_related_article_gold_scenarios() -> None:
    fixture = seed_related_article_fixture()
    gold_set = build_gold_set(fixture.ids)
    context = build_context()

    assert len(gold_set.scenarios) >= 20

    for scenario in gold_set.scenarios:
        response = await fixture.service.handle(scenario.request, context)
        expectation = scenario.expectation

        assert response.type == expectation.expected_type, scenario.name

        if response.type == "clarify":
            assert response.missing_slots == expectation.expected_missing_slots, scenario.name
            assert len(response.questions) == len(expectation.expected_missing_slots), scenario.name
            assert response.partial_structured_case.session_id == scenario.request.session_id, scenario.name
            continue

        final_ids = [candidate.internal_id for candidate in response.final]
        assert final_ids[: len(expectation.expected_final_ids)] == expectation.expected_final_ids, scenario.name
        assert response.debug["structure"]["schema_attempts"], scenario.name
        assert response.debug["retrieval"]["query_terms"], scenario.name
        assert "filtered_out" in response.debug["evaluation"], scenario.name
        for label in expectation.expected_route_labels:
            assert label in response.route.labels, scenario.name


async def test_structured_case_retries_after_schema_validation_error() -> None:
    llm = InvalidThenValidSchemaLLM()
    service = StructuredCaseService(llm=llm, max_retries=3)

    structured_case, debug = await service.structure(
        RelatedArticleRequest(session_id="retry-session", user_text="병사가 재물을 절도했습니다."),
        build_context(),
    )

    assert llm.calls == 2
    assert [attempt["status"] for attempt in debug["schema_attempts"]] == ["validation_error", "ok"]
    assert structured_case.actions[0].verb == "절도"
    assert structured_case.objects[0].name == "재물"


async def test_operational_mode_masks_debug_payload() -> None:
    fixture = seed_related_article_fixture(operational_mode=True)
    response = await fixture.service.handle(
        RelatedArticleRequest(
            session_id="s-operational",
            user_text="행정청이 민원인에게 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
            as_of_date=date(2024, 3, 1),
        ),
        build_context(),
    )

    assert response.type == "result"
    assert response.debug["sampled"] is True
    assert "schema_attempts" in response.debug["structure"]
    assert len(response.debug["retrieval"]["query_terms"]) <= 5
    assert "filtered_out_count" in response.debug["evaluation"]
    assert "filtered_out" not in response.debug["evaluation"]


def test_related_articles_endpoint_smoke() -> None:
    fixture = seed_related_article_fixture()
    original_state = {
        "repository": container.repository,
        "graph_store": container.graph_store,
        "text_search_store": container.text_search_store,
        "vector_store": container.vector_store,
        "related_article_service": container.related_article_service,
    }

    container.repository = fixture.repository
    container.graph_store = fixture.graph_store
    container.text_search_store = fixture.text_search_store
    container.vector_store = fixture.vector_store
    container.related_article_service = fixture.service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/services/related-articles/find",
                headers={
                    "x-request-id": "req-api-smoke",
                    "x-corpus-version": "gold-v1",
                    "x-ingestion-run-id": "ing-api-smoke",
                },
                json={
                    "session_id": "s-api-smoke",
                    "user_text": "행정청이 민원인에게 불이익 처분을 하면서 사전통지를 하지 않았습니다.",
                    "as_of_date": "2024-03-01",
                },
            )
    finally:
        for key, value in original_state.items():
            setattr(container, key, value)

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "result"
    assert payload["final"][0]["internal_id"] == fixture.ids["admin_notice_v1"]
    assert response.headers["x-request-id"] == "req-api-smoke"
