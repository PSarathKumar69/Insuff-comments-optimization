"""Stage 2 escalation pass — gemini-flash-latest.

Re-runs only the rows Stage 1 left as "No match" or Medium/Low confidence
through a stronger model, same batch/checkpoint/retry logic as Stage 1.
See Claude.md and PROGRESS_LOG.md for why gemini-flash-latest is used here
instead of the originally pinned gemini-2.5-flash (retired for this API key,
no pinned non-lite same-generation equivalent exists).

gemini-flash-latest resolves to gemini-3.7-flash, which on this free-tier key
is capped at 5 RPM / 20 requests-per-day — far below the 9 batches needed.
Rather than a one-shot run that dies on quota exhaustion, this script
self-resumes: each pass processes whatever's still pending per the checkpoint
file; a quota/API error logs it and sleeps before retrying; a full day's
worth of retries is capped by --max-window-hours so it doesn't loop forever
if something else is actually wrong.

Usage:
    python stage2_escalate.py                        # self-resuming loop (default)
    python stage2_escalate.py --once                  # single pass, no retry loop
    python stage2_escalate.py --retry-interval 1800   # 30 min between retries
    python stage2_escalate.py --max-window-hours 12   # shorter give-up window
"""

import argparse
import asyncio
import json
import sys
import time

from gemini_common import (
    load_client, load_templates, load_tag_glossary,
    build_fixed_context, make_batches, build_prompt, call_gemini_async,
    append_checkpoint, load_done_batches, log_progress,
)

MODEL = "gemini-3.1-flash-lite"  # gemini-flash-latest (-> gemini-3.7-flash) was persistently 503/429 on free tier; see PROGRESS_LOG.md
STAGE1_CHECKPOINT = "stage1_checkpoint.jsonl"
CHECKPOINT_PATH = "stage2_checkpoint.jsonl"
MAX_CONCURRENCY = 4  # same tier/config Stage 1 ran cleanly across all 83 batches
MIN_GAP_SECONDS = 1
INNER_MAX_RETRIES = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 45 * 60
DEFAULT_MAX_WINDOW_HOURS = 36


def load_stage2_subset(stage1_checkpoint: str = STAGE1_CHECKPOINT):
    with open(stage1_checkpoint, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    subset = [
        r for r in rows
        if r["matched_template_id"] == "No match" or r["match_confidence"] in ("Medium", "Low")
    ]
    return [{"row_number": r["row_number"], "comment_text": r["comment_text"], "count": r["count"]} for r in subset]


async def run_batch(client, sem, fixed_context, batch_index, batch_rows, checkpoint_path):
    async with sem:
        prompt = build_prompt(fixed_context, batch_rows)
        results = await call_gemini_async(client, MODEL, prompt, max_retries=INNER_MAX_RETRIES)
        append_checkpoint(checkpoint_path, batch_index, results)
        print(f"[batch {batch_index}] done - {len(results)} rows classified")
        return batch_index


async def process_pending(client, fixed_context, batches, done: set, checkpoint_path):
    """One pass over currently-pending batches. Stops at the first error so
    the caller can log it and back off. Returns (completed_this_pass, error_or_None)."""
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    pending = [i for i in range(len(batches)) if i not in done]
    completed = 0
    for idx, i in enumerate(pending):
        try:
            await run_batch(client, sem, fixed_context, i, batches[i], checkpoint_path)
            done.add(i)
            completed += 1
        except Exception as e:
            return completed, e
        if idx < len(pending) - 1:
            await asyncio.sleep(MIN_GAP_SECONDS)
    return completed, None


async def run_with_resume(checkpoint_path: str, retry_interval_s: int, max_window_s: float):
    client = load_client()
    rows = load_stage2_subset()
    templates = load_templates()
    tags = load_tag_glossary()
    fixed_context = build_fixed_context(templates, tags)
    batches = make_batches(rows)
    total_batches = len(batches)
    print(f"Stage 2 subset rows: {len(rows)} | Total batches: {total_batches}")

    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        done = load_done_batches(checkpoint_path)
        pending_count = total_batches - len(done)
        elapsed_h = (time.time() - start) / 3600

        if pending_count == 0:
            log_progress(f"Stage 2 attempt {attempt}: all {total_batches} batches complete. Done.")
            print("All batches complete.")
            return True

        if time.time() - start > max_window_s:
            log_progress(
                f"Stage 2 attempt {attempt}: TIMEOUT after {elapsed_h:.1f}h — "
                f"{pending_count}/{total_batches} batches still pending. Giving up; investigate manually."
            )
            print(f"Timed out after {elapsed_h:.1f}h with {pending_count} batches still pending.", file=sys.stderr)
            return False

        completed, err = await process_pending(client, fixed_context, batches, done, checkpoint_path)

        if err is not None:
            log_progress(
                f"Stage 2 attempt {attempt}: quota/API-blocked after {completed} batch(es) this pass "
                f"({pending_count - completed} still pending). Error: {err}. "
                f"Sleeping {retry_interval_s // 60}min before next attempt."
            )
            print(f"[attempt {attempt}] blocked ({err}); completed {completed} this pass; "
                  f"sleeping {retry_interval_s}s")
            await asyncio.sleep(retry_interval_s)
        else:
            log_progress(f"Stage 2 attempt {attempt}: completed {completed} batch(es) this pass, no errors.")


async def run_once(checkpoint_path: str):
    client = load_client()
    rows = load_stage2_subset()
    templates = load_templates()
    tags = load_tag_glossary()
    fixed_context = build_fixed_context(templates, tags)
    batches = make_batches(rows)
    print(f"Stage 2 subset rows: {len(rows)} | Total batches: {len(batches)}")

    done = load_done_batches(checkpoint_path)
    completed, err = await process_pending(client, fixed_context, batches, done, checkpoint_path)
    print(f"Completed {completed} batch(es) this pass.")
    if err is not None:
        print(f"Stopped early on error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, default=CHECKPOINT_PATH)
    parser.add_argument("--once", action="store_true", help="single pass, no retry loop")
    parser.add_argument("--retry-interval", type=int, default=DEFAULT_RETRY_INTERVAL_SECONDS,
                         help="seconds to sleep between retry attempts (default 2700 = 45min)")
    parser.add_argument("--max-window-hours", type=float, default=DEFAULT_MAX_WINDOW_HOURS,
                         help="give up after this many hours of retrying (default 36)")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once(args.checkpoint))
    else:
        ok = asyncio.run(run_with_resume(args.checkpoint, args.retry_interval, args.max_window_hours * 3600))
        sys.exit(0 if ok else 1)
