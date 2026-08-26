#!/usr/bin/env python3
"""
*** STALE - DO NOT RUN (as of 2026-08-18) ***
data/tag_values.json has been hand-edited directly in every session since
Phase 2 - QUALIFICATION_TYPE was added then removed again, YEAR_FROM/YEAR_TO/
REVIEW_REASON/FIELD_NAME/VALUE1/VALUE2/THRESHOLD were added, SPECIAL_
INSTRUCTIONS/CLIENT_ACTION/IDENTIFIER_TYPE were expanded, COURSE_NAME was
converted from free_text to a cleaned picklist, ANTECEDENTS/CASE_LEVEL_
INFORMATION/VERIFICATION_BLOCKER were converted to dropdown_multi (with
CASE_LEVEL_INFORMATION's values also deduped/split/PII-scrubbed and
ANTECEDENTS casing-normalized), PORTAL_NAME's hedd/Hedd duplicate was merged,
DOCUMENTS had its embedded "or" phrasing split out and one entry simplified,
and DOCUMENT_OPTIONS/DOCUMENT_REQUIREMENTS were removed entirely - none of
this is reflected in the DOCUMENTS_ATOMIC list or tag_values dict below.
Rerunning this script would silently throw away every one of those fixes.
If tag_values.json ever needs a full rebuild from scratch again, this script
must be brought current first (or just keep hand-editing the JSON, which is
the pattern every session has used).

Builds the JSON data files that drive the Education Insuff-Comment MVP:
  - tag_values.json     : real, frequency-ranked dropdown value lists per tag
  - reason_clauses.json : reason-sentence fragments used to patch templates that
                           were missing an explicit "why" clause

Source of truth for real values: ../Output Excel Sheets/Actual_To_Atomic_Mapping.xlsx
(Detail sheet's extracted_tags column, format "TAG=value (Confidence); ..."),
parsed directly here (no dependency on any prior session's scratch files) plus
the 36-tag glossary + Tag Glossary v2 reconciliation done earlier this project.

Run from this folder: `python3 build_data.py` (then build_templates.py, then
build_search_index.py - all three must run in that order).
"""
import json, os, re, openpyxl
from collections import Counter, defaultdict

BASE = os.path.dirname(__file__)
OUT_DIR = os.path.join(BASE, "data")
os.makedirs(OUT_DIR, exist_ok=True)

SOURCE_WORKBOOK = os.path.join(BASE, "..", "Output Excel Sheets", "Actual_To_Atomic_Mapping.xlsx")

# ---------------------------------------------------------------------------
# 0. Harvest real per-tag value counts from the Detail sheet's extracted_tags
#    column (format: "TAG=value (Confidence); TAG2=value2 (Confidence)").
# ---------------------------------------------------------------------------
def harvest_tag_value_counts(workbook_path):
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    ws = wb["Detail"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}
    et_i, count_i = idx["extracted_tags"], idx["count"]

    entry_re = re.compile(r"([A-Za-z0-9_]+)=(.*?)\s*\((High|Medium|Low)\)")
    tag_value_counts = defaultdict(Counter)
    for r in rows[1:]:
        et, cnt = r[et_i], r[count_i] or 1
        if not et:
            continue
        for m in entry_re.finditer(et):
            tag, val = m.group(1), m.group(2).strip()
            if val:
                tag_value_counts[tag][val] += cnt
    return tag_value_counts

tag_value_counts = harvest_tag_value_counts(SOURCE_WORKBOOK)

def top(tag, n=30, min_count=1):
    vals = tag_value_counts.get(tag, {})
    items = sorted(vals.items(), key=lambda x: -x[1])
    return [v for v, c in items if c >= min_count][:n]

# ---------------------------------------------------------------------------
# 0b. DOCUMENTS: the raw extracted_tags values are frequently COMPOUND -
#     several real documents joined by comma/slash/"and", or even concatenated
#     with no separator at all (e.g. "Higher Secondary Certificate(HSC)All
#     year marksheets"), because the classifier captured everything mentioned
#     in one comment as a single DOCUMENTS value. Feeding those straight into
#     a dropdown (the original bug) makes "one document" options that are
#     actually 2-4 documents glued together - exactly backwards, since the
#     whole point of the AND/OR/BOTH document-builder is for the USER to
#     compose combinations, not to have them pre-baked into the value list.
#
#     A fully automated splitter was tried and rejected: naive rules (split
#     on ",", "/", " and ") produce garbage on this data (e.g. splitting the
#     single real document "Transcripts and Marksheets" into two fake ones,
#     or leaving un-spaced concatenations like "BCom- Bachelor of
#     CommerceDegree" un-split). Given Education's real document vocabulary
#     is small, this list is a manually curated, atomic set - each entry a
#     single real document, cross-checked against the highest-frequency raw
#     values above (frequency shown in comments for traceability) and
#     de-duplicated (case/spacing variants merged to one canonical form).
DOCUMENTS_ATOMIC = [
    "Degree",                                                   # 1725 standalone, 7312 incl. combos
    "All year marksheets",                                      # 1114 standalone, 6252 incl. combos
    "Final year marksheet",                                     # 1042 standalone, 5687 incl. combos
    "Provisional Certificate",                                  # 2906 incl. combos
    "Highest Passing Education Marksheet or Degree",             # 1730
    "Higher Secondary Certificate (HSC)",                        # 1378 incl. spacing variants
    "Highest completed education documents",                    # 1079
    "HEDD consent form",                                         # 523
    "Name change proof",                                         # 361, merges "Name Change proof" + "documentary proof supporting the name change"
    "Original copies of University-issued Final year marksheet", # 312
    "Degree certificate",                                        # 209
    "Authorization form",                                        # 198
    "Consent form",                                              # 176
    "Secondary School Certificate (SSC)",                        # 158 incl. spacing variants
    "Transcripts and Marksheets",                                # 157, kept as one document (not split into Transcripts + Marksheets)
    "Bonafide/NOC",                                              # 149, kept as one document (an either/or document type, not two)
    "Diploma/Certificate",                                       # 61, kept as one document
    "Authbridge ARN",                                            # 132
    "Both-side colour copy of University-issued Degree",         # 106
    "Letter of Authorization",                                   # 100
    "Second highest completed Education Documents",              # 93
    "Application Form",                                          # 79
    "Graduation or above education documents",                   # 44
    "Aadhaar card",                                               # 39, common name-change supporting doc
]

# ---------------------------------------------------------------------------
# 0c. CHECK_NAME: same root problem as DOCUMENTS but worse - the raw
#     extracted_tags values for CHECK_NAME are mostly NOT check names at all;
#     the classifier frequently captured the qualification/course name
#     instead (e.g. "MBA", "B.Tech", "Bachelor of Commerce" appearing 3x in
#     slightly different spellings/cases). The authoritative, clean list of
#     actual check names is `Reference Data/master checks.csv` (381 rows,
#     check_id + check_name, arrived from the wider consolidation project).
#     Filtered here to the Education-relevant subset by keyword match.
def load_education_check_names(csv_path):
    import csv
    keywords = ("education", "academic", "professional certificate", "professional license")
    names = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["check_name"].strip()
            if any(k in name.lower() for k in keywords) and name not in names:
                names.append(name)
    return names

CHECK_NAMES_EDUCATION = load_education_check_names(os.path.join(BASE, "..", "Reference Data", "master checks.csv"))

# ---------------------------------------------------------------------------
# 1. TAG VALUES  (only genuinely finite/categorical tags get enumerated lists;
#    VS / COST / ANTECEDENTS / CLIENT_NAME / COURSE_NAME stay free-text per
#    the explicit "we never need to capture VS/COST/ANTECEDENTS" rule)
# ---------------------------------------------------------------------------

tag_values = {
    "DOCUMENTS": {
        "type": "atomic_document_builder",
        "note": "Curated, deduplicated, ATOMIC document list (one real document per entry - never a combined/comma-joined value). Combinations are built by the user via the pick-one -> AND/OR -> pick-next document-builder UI, never pre-baked into this list. 'Other' always available as free text for genuinely new document names.",
        "values": DOCUMENTS_ATOMIC,
    },
    "IDENTIFIER_TYPE": {
        "type": "dropdown",
        "note": "Real values harvested from 1,776 classified rows. Dominated by Roll/Registration Number; long tail normalized under 'Other (specify)'.",
        "values": ["Roll/Registration Number", "Hall Ticket No", "Exam Roll No", "Student ID Number", "Reference Number"],
    },
    "ADDRESS_TYPE": {
        "type": "dropdown",
        "note": "Enumerated 'pick one' placeholder resolved earlier this project (see OPEN_QUESTIONS.md) — confirmed 3 real values; 'Intermediate' was investigated and rejected as a 4th value.",
        "values": ["Current", "Previous", "Permanent"],
    },
    "COUNTRY": {
        "type": "dropdown",
        "note": "Value domain = Old Source Files/master country.csv (223 rows). Top real usage shown first for Education (USA/UK/Canada dominate), full list available via search-as-you-type.",
        "values": top("COUNTRY", 20) or ["USA", "United Kingdom", "Canada", "India", "Australia"],
        "full_list_source": "Old Source Files/master country.csv",
    },
    "CURRENCY": {
        "type": "dropdown",
        "note": "Value domain = Old Source Files/currency Name.csv (12 rows). Real usage: INR/USD/GBP cover ~99% of Education cases.",
        "values": top("CURRENCY", 12) or ["INR", "USD", "GBP", "EUR", "AUD"],
    },
    "CHECK_NAME": {
        "type": "dropdown_searchable",
        "note": "Auto-filled from Bridge navigation context in production (per owner: 'check family and type autofills'). Values here are the Education-relevant subset of the authoritative Reference Data/master checks.csv (381 rows total) - NOT the raw extracted_tags harvest, which turned out to be mostly misclassified qualification names (e.g. bare 'MBA') rather than real check names. Kept here only so the standalone prototype can simulate the header.",
        "values": CHECK_NAMES_EDUCATION,
        "full_list_source": "Reference Data/master checks.csv",
    },
    "VERIFICATION_BLOCKER": {
        "type": "dropdown",
        "note": "THE KEY REASON-DRIVING TAG. Real values harvested from 90 classified rows replace the earlier guessed sub-type list. Powers both the Document 'Wrong/Rejected' Reason sub-type AND the special-instruction checkboxes below.",
        "values": [
            "Document is not sufficient on its own (needs supporting document)",
            "Name on document does not match name in application form",
            "Letterhead verification is not possible for this institute",
            "Scanned copy is not clear / is cut off — needs a clear, uncut copy",
            "Online record does not fulfil the mandatory verification requirements",
            "Institute is not recognized by the verifying body",
            "File is not in the required format",
            "Course name on document does not match the course being verified",
            "Year of passing on document is incorrect / does not match",
            "Both-side colour copy required (only one side / black & white received)",
            "Signatures on document do not match across pages",
            "Document owner has disabled third-party verification of this record",
            "Dues are pending with the institute, blocking verification",
            "Record could not be located / traced by the institute",
        ],
    },
    "CLIENT_ACTION": {
        "type": "dropdown",
        "note": "Client Approval branch — what AuthBridge should do next when candidate can't/won't cooperate. Real value harvested: 'conduct Stamp verification' (58 rows). Kept short since this list should stay small and client-approval-policy driven, not comment-generation driven.",
        "values": ["conduct Stamp verification", "close the case as Unable to Verify", "proceed with alternate verification method", "continue follow-up for a further defined period"],
    },
    # NOTE: AND_OR_MODE (a single global dropdown for the join style) was
    # REMOVED 2026-08-15 per corrected design: AND/OR is chosen per-document,
    # via two buttons beside the document picker, not one dropdown applied to
    # the whole list. "BOTH" was also removed as a separate option - it's not
    # a user choice at all, just the natural-language phrasing automatically
    # used when exactly two documents are AND-joined ("both X and Y"); three+
    # AND-joined documents render as "all of X, Y, and Z" instead. See
    # CommentEngine.php's mandatoryPhrase()-equivalent logic (Mandatory +
    # Any-one-of model, 2026-08-18) and public/app.js's document-builder UI.
    "SPECIAL_INSTRUCTIONS": {
        "type": "dropdown_multi",
        "note": "Non-exhaustive but finite set of recurring submission-quality instructions, derived from VERIFICATION_BLOCKER real values + T16/T25/T38/T53/T54/T66 template language. Free-text 'Other instruction' always available.",
        "values": [
            "Duly signed by the institution",
            "Both sides, colour copy",
            "Original (not a photocopy)",
            "Self-attested by the candidate",
            "In the approved format (link will be shown)",
            "Company/entity name entered exactly as: AuthBridge Research Services Pvt. Ltd.",
        ],
    },
}

# Free-text / auto-filled / system-constant tags — documented, not enumerated
tag_values["VS"] = {"type": "free_text", "note": "Institute/university/employer name — unbounded, never enumerate. Auto-filled from case context where available, else free text."}
tag_values["COURSE_NAME"] = {"type": "free_text", "note": "Unbounded — auto-filled from case context, else free text."}
tag_values["ANTECEDENTS"] = {"type": "dropdown_free_hybrid", "note": "Real observed values (Academic year, CGPA, Bonafide/NOC, passing year...) show this is itself a small finite label set for Education — exposed as a dropdown with 'Other' fallback.", "values": top("ANTECEDENTS", 15)}
tag_values["COST"] = {"type": "free_text", "note": "Unbounded numeric — never enumerate."}
tag_values["TOTAL_VER_COST"] = {"type": "free_text", "note": "Unbounded numeric — never enumerate."}
tag_values["CLIENT_NAME"] = {"type": "free_text", "note": "Unbounded — client-specific, auto-filled from case context."}
tag_values["CASE_LEVEL_INFORMATION"] = {"type": "dropdown_free_hybrid", "note": "Real values harvested (Date of Birth dominant at 57 rows).", "values": top("CASE_LEVEL_INFORMATION", 12)}
tag_values["FORM_COMPANY_NAME"] = {"type": "system_constant", "note": "Always 'AuthBridge Research Services Pvt. Ltd.' per real data (36/36 rows). Never shown as a dropdown/input — auto-injected.", "value": "AuthBridge Research Services Pvt. Ltd."}
tag_values["NO_OF_DAYS"] = {"type": "free_text", "note": "Unbounded numeric."}
tag_values["PORTAL_NAME"] = {"type": "dropdown_free_hybrid", "note": "Small real list observed (HEDD, Parchment, Sunderland, My eQuals...) — dropdown with Other fallback.", "values": top("PORTAL_NAME", 10)}
tag_values["PORTAL_URL"] = {"type": "free_text", "note": "Unbounded — paired with PORTAL_NAME, auto-filled from a portal->URL lookup where known."}
tag_values["CONTACT_ROLE"] = {"type": "dropdown_free_hybrid", "note": "Real values: Placement coordinator, point of contact, TPO.", "values": top("CONTACT_ROLE", 10)}
tag_values["CONTACT_CHANNEL"] = {"type": "free_text", "note": "Email/phone value — unbounded."}
tag_values["CONTACT_OUTCOME"] = {"type": "dropdown", "note": "Not enough real samples to harvest confidently; drafted from template context pending owner review.", "values": ["is unreachable", "is invalid / disconnected", "did not respond after multiple attempts", "bounced back / does not exist"]}
tag_values["VERIFICATION_LOCATION"] = {"type": "free_text", "note": "Unbounded address/location."}
tag_values["VERIFIED_VALUE"] = {"type": "free_text", "note": "Auto-filled from the system's own verified record, never user-entered."}
tag_values["DOCUMENT_OPTIONS"] = {"type": "free_text_list", "note": "Retired as its own tag per owner decision (session 2026-07-30) — reuses the AND/OR/BOTH selector + DOCUMENTS multi-select mechanism instead of a separate tag."}
tag_values["DOCUMENT_REQUIREMENTS"] = {"type": "free_text", "note": "Composed automatically from SPECIAL_INSTRUCTIONS selections, not entered directly."}
tag_values["SOURCE_DOCUMENT"] = {"type": "free_text", "note": "Unbounded — the specific doc that was rejected; auto-filled from case context."}
tag_values["SOURCE_ACTION"] = {"type": "free_text", "note": "Only 1 real sample observed — too thin to enumerate confidently; free text pending more data."}
tag_values["PORTAL_ACTION"] = {"type": "free_text", "note": "Only 1 real sample observed — free text pending more data."}
tag_values["REFERENCE_URL"] = {"type": "free_text", "note": "Unbounded URL."}
tag_values["VALIDITY_PERIOD"] = {"type": "free_text", "note": "Unbounded duration text (e.g. '6 months')."}
tag_values["COST_APPROVAL_CONFIG"] = {"type": "free_text", "note": "Blocked tag per Session 4 finding — no real value list exists; free text until resolved."}

json.dump(tag_values, open(os.path.join(OUT_DIR, "tag_values.json"), "w"), indent=2)
print(f"tag_values.json: {len(tag_values)} tags")

# ---------------------------------------------------------------------------
# 2. REASON CLAUSES — full Reason+Action sentences used to replace templates
#    that were only "Kindly provide X" with no stated reason. This is the
#    direct fix for the gap flagged: "reason is missing in this generated
#    comment?".
# ---------------------------------------------------------------------------
reason_clauses = {
    "document.missing": "{DOCUMENTS} for {CONTEXT} was not submitted with the case. Kindly provide the same for verification.",
    "document.missing_signed": "The {DOCUMENTS} submitted for {CONTEXT} was not duly signed. Kindly provide a duly signed copy for verification.",
    "document.missing_special": "The {DOCUMENTS} submitted for {CONTEXT} did not include the required details/format. Kindly resubmit the {DOCUMENTS} with the instructions below.",
    "information.missing": "{ANTECEDENTS} for {CONTEXT} was not provided with the case. Kindly share this information for verification.",
    "information.missing_identifier": "The {IDENTIFIER_TYPE} for {CONTEXT} was not provided with the case. Kindly share this identifier for verification.",
    "information.missing_contact": "The {CONTACT_CHANNEL} of the {CONTACT_ROLE} for {CONTEXT} was not provided with the case. Kindly share this contact detail for verification.",
    "information.missing_case_level": "{CASE_LEVEL_INFORMATION} for {CONTEXT} was not provided with the case. Kindly share this information for verification.",
    "information.missing_address": "A complete address in {COUNTRY} for {CONTEXT} was not provided with the case. Kindly provide the complete address for verification.",
    "_comment": "Each value here is a FULL Reason+Action sentence (not a fragment to prepend) - avoids restating DOCUMENTS/CONTEXT twice. Templates whose raw text ALREADY narrates the reason inline (Blurred/Incomplete/Expired/Wrong-Rejected/Mismatch/Contact-outcome sub-types) do NOT use a clause from this file at all - they already pass the acceptance bar as-is."
}
json.dump(reason_clauses, open(os.path.join(OUT_DIR, "reason_clauses.json"), "w"), indent=2)
print(f"reason_clauses.json: {len(reason_clauses)} clauses")

print("Done - tag_values.json + reason_clauses.json written.")
