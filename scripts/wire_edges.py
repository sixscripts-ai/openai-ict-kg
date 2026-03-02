#!/usr/bin/env python3
"""Standalone CLI: auto-wire edges for all nodes in the database.

Usage:
    # From project root with .env loaded
    source .env && PYTHONPATH=src python scripts/wire_edges.py
    # Or with specific tenant
    source .env && PYTHONPATH=src python scripts/wire_edges.py --tenant default
"""
from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ict_kg.db import Database
from ict_kg.wiring import auto_wire_edges


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-wire edges in the ICT knowledge graph")
    parser.add_argument("--tenant", default="default", help="Tenant ID to wire edges for")
    args = parser.parse_args()

    print(f"Connecting to database...")
    db = Database()
    print(f"Auto-wiring edges for tenant '{args.tenant}'...")
    counts = auto_wire_edges(db, tenant_id=args.tenant)
    total = sum(counts.values())
    print(f"\nDone!")
    print(f"  Semantic (similar_to):  {counts['semantic']} edges")
    print(f"  Domain (related_to):    {counts['domain']} edges")
    print(f"  Ontology (typed):       {counts['ontology']} edges")
    print(f"  Total inserted:         {total} edges")


if __name__ == "__main__":
    main()
