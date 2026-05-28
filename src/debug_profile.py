#!/usr/bin/env python3
"""
Quick debug: time query_writer.py stages
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def main():
    print("Query Writer Debug Timings")
    print("=" * 50)

    print("\n[1] Initializing LightRAG...")
    from config import initialize_lightrag

    t0 = time.perf_counter()
    config = await initialize_lightrag(working_dir=str(Path(__file__).parent.parent / "working_dir"))
    t1 = time.perf_counter() - t0
    print(f"    Init time: {t1:.2f}s")

    rag = config["rag"]

    print("\n[2] Querying LightRAG (naive mode)...")
    from lightrag import QueryParam

    t2 = time.perf_counter()
    result = await rag.aquery(
        "Train to Pakistan Khushwant Singh themes",
        param=QueryParam(mode="naive", top_k=3, only_need_context=True)
    )
    t3 = time.perf_counter() - t2
    print(f"    Query time: {t3:.2f}s")
    print(f"    Result: {str(result)[:300]}...")

    print(f"\n{'='*50}")
    print(f"TOTAL: {t1 + t3:.2f}s (Init: {t1:.2f}s + Query: {t3:.2f}s)")


if __name__ == "__main__":
    asyncio.run(main())