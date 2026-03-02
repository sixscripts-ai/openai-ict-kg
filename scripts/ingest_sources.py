from __future__ import annotations

from ict_kg.service import KnowledgeGraphService


SOURCES = [
    ("github", "sixscripts-ai/train-ict"),
    ("github", "sixscripts-ai/ai-knowledge-graph"),
    ("web", "https://ict-knowledge-engine.vercel.app/"),
]


def main() -> None:
    service = KnowledgeGraphService()
    for source_system, source in SOURCES:
        job = service.create_ingestion_job("default", source_system, source, "knowledge-base")
        service.process_ingestion_job(job["id"])
        print(service.get_ingestion_job(job["id"]))


if __name__ == "__main__":
    main()
