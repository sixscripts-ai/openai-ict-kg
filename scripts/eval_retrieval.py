from __future__ import annotations

import os
from dataclasses import dataclass

from ict_kg.models import NodeCreate, QueryRequest
from ict_kg.service import KnowledgeGraphService


@dataclass
class EvalCase:
    query: str
    expected_title: str


def recall_at_k(cases: list[EvalCase], k: int = 3) -> float:
    service = KnowledgeGraphService()
    seed = [
        NodeCreate(tenant_id="eval", title="Liquidity Sweep", content="Price takes highs then reverses", domain="ict"),
        NodeCreate(tenant_id="eval", title="Fair Value Gap", content="Imbalance in candle delivery", domain="ict"),
        NodeCreate(tenant_id="eval", title="Order Block", content="Last opposing candle before impulsive move", domain="ict"),
    ]
    for row in seed:
        service.add_node(row)

    hits = 0
    for case in cases:
        results = service.query(QueryRequest(tenant_id="eval", text=case.query, top_k=k, include="nodes", rerank=True))
        titles = [r.title for r in results]
        if case.expected_title in titles:
            hits += 1

    return hits / len(cases)


def main() -> None:
    threshold = float(os.getenv("ICT_KG_RECALL_THRESHOLD", "0.66"))
    cases = [
        EvalCase("where does price take highs first", "Liquidity Sweep"),
        EvalCase("imbalance inefficiency", "Fair Value Gap"),
        EvalCase("last candle before displacement", "Order Block"),
    ]
    score = recall_at_k(cases, k=3)
    print({"recall_at_3": score, "cases": len(cases), "threshold": threshold})
    if score < threshold:
        raise SystemExit(f"Recall@3 below threshold: {score:.3f} < {threshold:.3f}")


if __name__ == "__main__":
    main()
