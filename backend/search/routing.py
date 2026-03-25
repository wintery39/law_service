from __future__ import annotations

from collections import defaultdict

from schemas.related_articles import DomainRoute, StructuredCase


DOMAIN_KEYWORDS = {
    "criminal": {"폭행", "상해", "절도", "처벌"},
    "disciplinary": {"근무지이탈", "명령거부", "징계", "상관", "복무"},
    "administrative": {"행정처분", "의견제출", "민원", "사전통지"},
    "civil": {"손해배상", "배상", "재산피해", "불법행위"},
    "military_special": {"군용물", "기밀", "기밀유출", "무단촬영", "보안", "무단반출", "보안구역"},
}


class DomainRouter:
    def classify(self, structured_case: StructuredCase) -> DomainRoute:
        scores: dict[str, float] = defaultdict(float)
        terms = {
            *structured_case.legal_terms,
            *structured_case.keyphrases,
            *(action.verb for action in structured_case.actions),
            *(obj.name for obj in structured_case.objects),
        }
        for label, keywords in DOMAIN_KEYWORDS.items():
            for term in terms:
                if any(keyword in term for keyword in keywords):
                    scores[label] += 1.0

        if not scores:
            scores["administrative"] = 0.1

        total = sum(scores.values()) or 1.0
        normalized = {label: round(score / total, 4) for label, score in scores.items()}
        labels = [label for label, score in sorted(normalized.items(), key=lambda item: item[1], reverse=True) if score >= 0.15]
        if not labels:
            labels = [max(normalized, key=normalized.get)]
        return DomainRoute(
            labels=labels,
            scores=normalized,
            filter_hints={
                "preferred_domains": labels,
                "keyword_hints": list(terms)[:10],
            },
        )
