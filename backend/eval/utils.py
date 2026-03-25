from __future__ import annotations

import math
import re


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def precision_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for item in top_k if item in gold_ids)
    return hits / k


def recall_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    if not gold_ids:
        return 0.0
    hits = sum(1 for item in ranked_ids[:k] if item in gold_ids)
    return hits / len(gold_ids)


def ndcg_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    if not gold_ids or k <= 0:
        return 0.0
    dcg = 0.0
    for index, candidate_id in enumerate(ranked_ids[:k], start=1):
        relevance = 1.0 if candidate_id in gold_ids else 0.0
        if relevance == 0.0:
            continue
        dcg += relevance / math.log2(index + 1)
    ideal_count = min(len(gold_ids), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    return 0.0 if idcg == 0 else dcg / idcg


def mean_reciprocal_rank(ranked_ids: list[str], gold_ids: set[str]) -> float:
    for index, candidate_id in enumerate(ranked_ids, start=1):
        if candidate_id in gold_ids:
            return 1.0 / index
    return 0.0


def average(values: list[float]) -> float:
    return 0.0 if not values else sum(values) / len(values)


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_terms(text: str) -> list[str]:
    return unique_strings(TOKEN_RE.findall(text.lower()))
