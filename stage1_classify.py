"""Stage 1 bulk classification pass — gemini-2.5-flash-lite.

Batches all Education!A/B rows in groups of 100, matches each comment to a
template (T1-T68 or "No match") by meaning and extracts tag values, per
Claude.md. Checkpoints each completed batch to a JSONL file so a crash
resumes from the last completed batch.

Usage:
    python stage1_classify.py                 # run all batches
    python stage1_classify.py --end-batch 0    # run only batch 0 (rows 2-101)
"""

import argparse
import asyncio
import sys

from gemini_common import (
    load_client, load_rows, load_templates, load_tag_glossary,
    build_fixed_context, make_batches, build_prompt, call_gemini_async,
    append_checkpoint, load_done_batches,
)

MODEL = "gemini-3.1-flash-lite"  # gemini-2.5-flash-lite retired for this API key (404); see PROGRESS_LOG.md
CHECKPOINT_PATH = "stage1_checkpoint.jsonl"
MAX_CONCURRENCY = 4


async def run_batch(client, sem, fixed_context, batch_index, batch_rows, checkpoint_path):
    async with sem:
        prompt = build_prompt(fixed_context, batch_rows)
        results = await call_gemini_async(client, MODEL, prompt)
        append_checkpoint(checkpoint_path, batch_index, results)
        print(f"[batch {batch_index}] done — {len(results)} rows classified")
        return batch_index


async def main(start_batch: int, end_batch: int, checkpoint_path: str):
    client = load_client()
    rows = load_rows()
    templates = load_templates()
    tags = load_tag_glossary()
    fixed_context = build_fixed_context(templates, tags)

    batches = make_batches(rows)
    total_batches = len(batches)
    print(f"Total rows: {len(rows)} | Total batches: {total_batches} | Templates: {len(templates)} | Tags: {len(tags)}")

    if end_batch is None:
        end_batch = total_batches - 1
    end_batch = min(end_batch, total_batches - 1)

    done = load_done_batches(checkpoint_path)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    tasks = []
    for i in range(start_batch, end_batch + 1):
        if i in done:
            print(f"[batch {i}] already done, skipping (resume)")
            continue
        tasks.append(run_batch(client, sem, fixed_context, i, batches[i], checkpoint_path))

    if not tasks:
        print("Nothing to do — all requested batches already checkpointed.")
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    failures = [r for r in results if isinstance(r, Exception)]
    if failures:
        print(f"\n{len(failures)} batch(es) failed:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        sys.exit(1)

    print(f"\nAll requested batches complete ({start_batch}-{end_batch}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--end-batch", type=int, default=None)
    parser.add_argument("--checkpoint", type=str, default=CHECKPOINT_PATH)
    args = parser.parse_args()
    asyncio.run(main(args.start_batch, args.end_batch, args.checkpoint))
