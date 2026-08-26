#!/usr/bin/env python3
"""
Builds data/search_index.json for the "can the new system still generate this
actual comment?" support/triage search feature.

Source: ../Output Excel Sheets/Actual_To_Atomic_Mapping.xlsx, Detail sheet
(comment_text, count, matched_template_id, match_confidence) - read directly
here, no dependency on any prior session's scratch files.

Post-processing:
  1. Remap old raw template IDs (T39/T48/T56/T58/T43/T55/T52) to their
     canonical merged ID per the same DROPPED_AS_DUPLICATE map used in
     build_templates.py, so search results point at a real template in
     this MVP's templates.json.
  2. Flag whether the resolved template is actually in-scope for this
     Education-MVP build (templates.json only covers Course/VS-scoped +
     generic CHECK_NAME-scoped templates - Employment/Address-only templates
     T19-T36 and the rare T64 variant are out of scope for now, so a match
     against one of those is reported as "template exists, not yet wired
     into this MVP" rather than "fully supported").
  3. "No match" rows stay "not_supported" (the ~0.25% genuinely not captured -
     see the "Not Captured" sheet analysis already on file in the workbook).

Run from this folder, after build_data.py and build_templates.py:
`python3 build_search_index.py`
"""
import json, os, re, openpyxl
from build_data import DOCUMENTS_ATOMIC

BASE = os.path.dirname(__file__)
OUT_DIR = os.path.join(BASE, "data")
SOURCE_WORKBOOK = os.path.join(BASE, "..", "Output Excel Sheets", "Actual_To_Atomic_Mapping.xlsx")

DROPPED_AS_DUPLICATE = {
    "T56": "T37", "T58": "T40", "T43": "T42", "T39": "T57", "T48": "T57",
    "T55": "T61", "T52": "T59",
}
OUT_OF_SCOPE_FOR_MVP = {f"T{i}" for i in range(19, 37)} | {"T64"}  # Employment/Address-only + rare source-sub variant

ENTRY_RE = re.compile(r"([A-Za-z0-9_]+)=(.*?)\s*\((High|Medium|Low)\)")


def parse_extracted_tags(raw):
    """'DOCUMENTS=Degree (High); CHECK_NAME=... (Medium)' -> {'DOCUMENTS': 'Degree', ...}
    Used 2026-08-15 onward to power the support-triage step-guide's
    "suggested values" (pulled from the closest real historical comment's
    own extracted tags, not invented)."""
    if not raw:
        return {}
    out = {}
    for m in ENTRY_RE.finditer(raw):
        tag, val = m.group(1), m.group(2).strip()
        if val:
            out[tag] = val
    return out


def resolve_documents_to_atomic(raw_value, atomic_list=DOCUMENTS_ATOMIC):
    """A historical row's raw DOCUMENTS tag value is often a compound/messy
    string (see build_data.py's DOCUMENTS_ATOMIC docstring for why). For the
    step-guide's "suggested documents", heuristically match it against the
    curated atomic list via substring containment, so the suggestion shown
    to the user is itself a clean atomic name (or names) rather than a raw
    compound string. Best-effort only - if nothing matches, the caller falls
    back to showing the raw text as free-form context instead."""
    if not raw_value:
        return []
    raw_lower = raw_value.lower()
    matches = {a for a in atomic_list if a.lower() in raw_lower}
    return sorted(matches, key=lambda a: raw_lower.find(a.lower()))


def load_detail_rows(workbook_path):
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    ws = wb["Detail"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}
    out = []
    for r in rows[1:]:
        out.append({
            "comment": r[idx["comment_text"]],
            "count": r[idx["count"]],
            "template_id": r[idx["matched_template_id"]],
            "confidence": r[idx["match_confidence"]],
            "extracted_tags": parse_extracted_tags(r[idx["extracted_tags"]]),
        })
    return out


def build():
    raw = load_detail_rows(SOURCE_WORKBOOK)
    templates = {t["id"]: t for t in json.load(open(os.path.join(OUT_DIR, "templates.json")))}

    out = []
    for row in raw:
        tid = row["template_id"]
        resolved = DROPPED_AS_DUPLICATE.get(tid, tid)
        if resolved == "No match" or not resolved:
            status = "not_supported"
            resolved = None
        elif resolved in OUT_OF_SCOPE_FOR_MVP:
            status = "template_exists_not_in_education_mvp"
        elif resolved in templates:
            status = "supported"
        else:
            status = "not_supported"
            resolved = None
        tags = dict(row["extracted_tags"])
        suggested_documents = resolve_documents_to_atomic(tags.get("DOCUMENTS", ""))

        out.append({
            "comment": row["comment"],
            "count": row["count"],
            "resolved_template_id": resolved,
            "status": status,
            "confidence": row["confidence"],
            "extracted_tags": tags,
            "suggested_documents": suggested_documents,
        })

    json.dump(out, open(os.path.join(OUT_DIR, "search_index.json"), "w"))
    supported = sum(1 for r in out if r["status"] == "supported")
    exists_not_wired = sum(1 for r in out if r["status"] == "template_exists_not_in_education_mvp")
    not_supported = sum(1 for r in out if r["status"] == "not_supported")
    print(f"search_index.json: {len(out)} rows -> supported={supported}, "
          f"exists_but_not_in_mvp={exists_not_wired}, not_supported={not_supported}")


if __name__ == "__main__":
    build()
