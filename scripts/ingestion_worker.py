from __future__ import annotations

import time

from ict_kg.service import KnowledgeGraphService


def main(poll_interval: float = 2.0) -> None:
    service = KnowledgeGraphService()
    while True:
        jobs, _ = service.list_ingestion_jobs("default", limit=20, offset=0)
        queued = [j for j in jobs if j["status"] == "queued"]
        for job in queued:
            service.process_ingestion_job(job["id"])
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
