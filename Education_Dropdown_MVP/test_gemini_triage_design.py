#!/usr/bin/env python3
"""
Design verification for the new Gemini-escalation path in SearchEngine.php /
GeminiTriageClient.php (hybrid triage matcher, added 2026-08-15).

IMPORTANT: this script uses the EXISTING `GEMINI_API_KEY` (the one already in
this project's .env, used for the offline batch classification pipeline) -
NOT the new `TRIAGE_GEMINI_API_KEY` placeholder, which is intentionally left
for the owner to fill in with a distinct key for the live triage feature.
This script's only job is to prove the prompt/schema design actually
resolves the reported bug before that production key exists - it is a
one-time design check, not part of the shipped application.

Run from this folder: python3 test_gemini_triage_design.py
"""
import json, os, re
from dotenv import load_dotenv
from google import genai
from google.genai import types

BASE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.join(BASE, "..")
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

MODEL = "gemini-flash-lite-latest"  # confirmed working for this key/tier, see PROGRESS_LOG 2026-08-14

templates = json.load(open(os.path.join(BASE, "data/templates.json")))
tag_values = json.load(open(os.path.join(BASE, "data/tag_values.json")))


def templates_context():
    out = []
    for t in templates:
        out.append({
            "template_id": t["id"],
            "insuff_category": t["insuff_category"],
            "reason_category": t["reason_category"],
            "reason_sub_type": t.get("scenario_label") or t["reason_sub_type"],
            "example_phrasing": t["optimized_text"],
            "needed_tags": t["needed_tags"],
        })
    return out


def tag_values_context():
    return {tag: meta["values"] for tag, meta in tag_values.items() if meta.get("values")}


def build_prompt(query):
    templates_json = json.dumps(templates_context(), indent=2)
    tag_values_json = json.dumps(tag_values_context(), indent=2)
    return f"""You are classifying one real insufficiency-verification comment against a fixed set of Education-department comment templates, for a background-verification company (AuthBridge).

A local keyword-overlap search already ran and could not confidently resolve this comment (either no template scored well, or two+ templates scored too close together to trust). Your job: read the comment's actual MEANING and pick the single best-fitting template - do not just match shared words. Common failure mode to avoid: a comment mentioning "TAT" or "extension" is about the TAT Approval category even if it shares no words with any Document/Information template; a comment about "cost" or "approve the additional charge" is about Cost Approval even if phrased very differently from the stored example text.

The candidate templates (id, category, reason, an example of how it phrases, and which tag fields it needs):
{templates_json}

Allowed values for tags that have a fixed dropdown (map extracted values to the closest one of these if applicable; if a tag isn't listed here, it's free text - just extract the raw value):
{tag_values_json}

The actual comment to classify:
"{query}"

Return the single best-matching template_id (or "no_match" if truly nothing fits), your confidence, a one-sentence reason, and every tag value you can extract from the comment text itself (never invent a value that isn't implied by the comment)."""


SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "template_id": {"type": "STRING"},
        "confidence": {"type": "STRING", "enum": ["High", "Medium", "Low", "None"]},
        "reasoning": {"type": "STRING"},
        "extracted_tags": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "tag": {"type": "STRING"},
                    "raw_value": {"type": "STRING"},
                    "matched_dropdown_value": {"type": "STRING"},
                },
                "required": ["tag", "raw_value"],
            },
        },
        "suggested_documents": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["template_id", "confidence", "reasoning"],
}

TEST_QUERIES = [
    # The reported bug: local match tied 0.333/0.333 between T9 and T37, neither correct.
    "Requesting the extra TAT for verification",
    # A clear cost-approval case, differently phrased from any stored template text.
    "Client needs to approve extra charges before we can proceed with this check",
    # A clear document-missing case for comparison (should still resolve correctly).
    "Please share the original degree certificate for verification",
    # Something that plausibly has no template at all.
    "Candidate's phone number is switched off and unreachable since last week",
]


def run():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for q in TEST_QUERIES:
        prompt = build_prompt(q)
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=SCHEMA,
        )
        response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
        result = json.loads(response.text)
        print("=" * 100)
        print("QUERY:", q)
        print("template_id:", result.get("template_id"), "| confidence:", result.get("confidence"))
        print("reasoning:", result.get("reasoning"))
        print("extracted_tags:", result.get("extracted_tags"))
        print("suggested_documents:", result.get("suggested_documents"))


if __name__ == "__main__":
    run()
