#!/usr/bin/env python3
"""Create all Elasticsearch indices for CatalogSentinel."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

from es.indices import create_all_indices

def main():
    print("\nCatalogSentinel — Initializing Elasticsearch Indices\n")
    results = create_all_indices()
    ok = sum(1 for v in results.values() if v)
    fail = sum(1 for v in results.values() if not v)
    for name, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {name}")
    print(f"\nResult: {ok} ready, {fail} failed")
    if fail:
        sys.exit(1)

if __name__ == "__main__":
    main()
