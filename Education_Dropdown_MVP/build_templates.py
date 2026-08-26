#!/usr/bin/env python3
"""
*** STALE - DO NOT RUN (as of 2026-08-18) ***
data/templates.json and data/dropdown_tree.json have been hand-edited directly
in every session since (at least) Phase 2 - QUALIFICATION_TYPE/YEAR_FROM/
YEAR_TO, T69/T70/T71, the Mandatory+Any-one-of DOCUMENTS redesign, the
CONTEXT-bypass fixes on T10/T11/T12/T13/T17/T18, T64 (new), T67 (retired),
DOCUMENT_REQUIREMENTS removal (T63), ADDRESS_TYPE on T65, and the T53/T66
dangling-reference fixes are ALL only reflected in the JSON files on disk,
NOT in the RAW list or logic below. Rerunning this script would silently
throw away every one of those fixes and regenerate an out-of-date 68/44-ish
template set. If templates.json/dropdown_tree.json ever need a full rebuild
from scratch again, this script must be brought current first (or just
keep hand-editing the JSON, which is the pattern every session has used).

Builds templates.json: the OPTIMIZED template set (68 raw templates -> merged/
reason-patched canonical set) plus dropdown_tree.json (the Insuff Category ->
Reason -> Sub-reason decision tree the MVP UI walks).

Optimization pass applied here (this is the "T71 processing" the owner flagged
as not yet done):
  1. Duplicate consolidation: T56->T37, T58->T40, T43->T42, T39/T48->T57-wording.
     (near-identical phrasing, same Reason Category/Sub-type/Tags — kept as one
     canonical template, old IDs recorded as merged_from for audit trail.)
  2. Reason-clause injection: templates whose raw text was a bare "Kindly
     provide X" with NO stated reason (Missing / Missing-Signed / Missing-
     Special-instructions / Information-Missing variants) get a reason
     sentence PREPENDED using reason_clauses.json, so every generated comment
     states why before what.
  3. Templates that already narrate the reason inline (Blurred/Incomplete/
     Expired/Wrong-Rejected/Mismatch/Contact-outcome) are left as-is — they
     already pass the acceptance bar.
"""
import json, os

BASE = os.path.dirname(__file__)
OUT_DIR = os.path.join(BASE, "data")

# Raw 68-template set with categorization, exactly as audited in
# "Template Master Reference" sheet of Actual_To_Atomic_Mapping.xlsx
RAW = [
("T1","The candidate has declined to share <DOCUMENTS> required for <CHECK_NAME>. Kindly confirm whether we should <CLIENT_ACTION>.","Client Approval","Candidate Non-Cooperation","Declined to share"),
("T2","The candidate has confirmed that <DOCUMENTS> required for <CHECK_NAME> is not available. Kindly confirm whether we should <CLIENT_ACTION>.","Client Approval","Candidate Non-Cooperation","Confirmed not available"),
("T3","The candidate has left the organization. Kindly confirm whether we should <CLIENT_ACTION> for <CHECK_NAME>.","Client Approval","Candidate Non-Cooperation","Left organization"),
("T4","The candidate has confirmed that they will not join the organization. Kindly confirm whether we should <CLIENT_ACTION> for <CHECK_NAME>.","Client Approval","Candidate Non-Cooperation","Will not join"),
("T5","The candidate did not respond after the configured number of attempts for <CHECK_NAME>. Kindly confirm whether we should <CLIENT_ACTION>.","Client Approval","Candidate Non-Cooperation","Non-responsive"),
("T6","Verification cannot proceed for <CHECK_NAME> because <VERIFICATION_BLOCKER>. Kindly confirm whether we should <CLIENT_ACTION>.","Client Approval","Candidate Non-Cooperation","Verification blocked"),
("T7","Kindly approve the additional verification cost of <CURRENCY> <COST> for <CHECK_NAME>.","Cost Approval","N/A","N/A"),
("T8","Kindly approve the revised total verification cost of <CURRENCY> <TOTAL_VER_COST> for <CHECK_NAME>.","Cost Approval","N/A","N/A"),
("T9","Kindly provide <DOCUMENTS> for <COURSE_NAME> from <VS>.","Insufficiency","Document","Missing"),
("T10","The copy of <DOCUMENTS> submitted for <COURSE_NAME> from <VS> is blurred or unreadable. Kindly provide a clear and readable copy.","Insufficiency","Document","Blurred/Illegible"),
("T11","The copy of <DOCUMENTS> submitted for <COURSE_NAME> from <VS> is incomplete or partially visible. Kindly provide a complete copy.","Insufficiency","Document","Incomplete"),
("T12","The <DOCUMENTS> submitted for <COURSE_NAME> from <VS> has expired. Kindly provide a valid and current copy.","Insufficiency","Document","Expired"),
("T13","The <DOCUMENTS> submitted for <COURSE_NAME> from <VS> cannot be accepted because <VERIFICATION_BLOCKER>. Kindly provide an acceptable copy.","Insufficiency","Document","Wrong/Rejected"),
("T14","Kindly provide <ANTECEDENTS> for <COURSE_NAME> from <VS>.","Insufficiency","Information","Missing"),
("T15","Kindly provide the <IDENTIFIER_TYPE> for <COURSE_NAME> from <VS>.","Insufficiency","Information","Missing (Identifier)"),
("T16","Kindly provide a duly completed and signed <DOCUMENTS> for <COURSE_NAME> from <VS>.","Insufficiency","Document","Missing (Signed)"),
("T17","Please complete the pending verification action for <COURSE_NAME> from <VS> on <PORTAL_NAME> using <PORTAL_URL>.","Insufficiency","Action Required","Portal Action"),
("T18","The <ANTECEDENTS> provided earlier for <COURSE_NAME> from <VS> does not match the available record. Kindly provide the correct value.","Insufficiency","Information","Mismatch"),
("T37","Kindly provide <DOCUMENTS> for <CHECK_NAME>.","Insufficiency","Document","Missing"),
("T38","Kindly provide a duly completed and signed <DOCUMENTS> for <CHECK_NAME>.","Insufficiency","Document","Missing (Signed)"),
("T57","The <DOCUMENTS> submitted for <CHECK_NAME> cannot be accepted because <VERIFICATION_BLOCKER>. Kindly provide a corrected copy.","Insufficiency","Document","Wrong/Rejected"),
("T40","Kindly provide <ANTECEDENTS> for <CHECK_NAME>.","Insufficiency","Information","Missing"),
("T41","Kindly provide the <IDENTIFIER_TYPE> for <CHECK_NAME>.","Insufficiency","Information","Missing (Identifier)"),
("T42","Please complete <CHECK_NAME> at <VERIFICATION_LOCATION> within <NO_OF_DAYS> days.","Insufficiency","Action Required","Visit/complete within deadline"),
("T44","The <CONTACT_CHANNEL> previously provided for <CHECK_NAME> <CONTACT_OUTCOME>. Kindly provide another valid <CONTACT_CHANNEL>.","Insufficiency","Information","Wrong/Status (Contact outcome)"),
("T45","The copy of <DOCUMENTS> submitted for <CHECK_NAME> is blurred or unreadable. Kindly provide a clear and readable copy.","Insufficiency","Document","Blurred/Illegible"),
("T46","The copy of <DOCUMENTS> submitted for <CHECK_NAME> is incomplete or partially visible. Kindly provide a complete copy.","Insufficiency","Document","Incomplete"),
("T47","The <DOCUMENTS> submitted for <CHECK_NAME> has expired. Kindly provide a valid and current copy.","Insufficiency","Document","Expired"),
("T49","Kindly confirm whether <CLIENT_NAME> may be disclosed to <VS> for <CHECK_NAME>.","Client Approval","Disclosure Consent","N/A"),
("T50","Kindly approve the verification cost of <CURRENCY> <COST> for <CHECK_NAME> in <COUNTRY>.","Cost Approval","N/A","N/A"),
("T51","Kindly provide <CASE_LEVEL_INFORMATION> for <CHECK_NAME>.","Insufficiency","Information","Missing (Case-level)"),
("T53","Kindly complete the <DOCUMENTS> by mentioning <FORM_COMPANY_NAME> as the company name. The form must include the candidate's full name and date and must be hand-signed.","Insufficiency","Document","Missing (special instructions)"),
("T59","The <ANTECEDENTS> provided for <CHECK_NAME> does not match the supporting record. The value shown in the supporting record is <VERIFIED_VALUE>. Kindly confirm or update the correct value.","Insufficiency","Information","Mismatch (with verified value)"),
("T60","Kindly approve an extension of <NO_OF_DAYS> days for <CHECK_NAME> because <VERIFICATION_BLOCKER>.","TAT Approval","N/A","N/A"),
("T61","Please <PORTAL_ACTION> on <PORTAL_NAME> using <PORTAL_URL> to complete <CHECK_NAME>.","Insufficiency","Action Required","Portal Action"),
("T62","Please <SOURCE_ACTION> to complete <CHECK_NAME>.","Insufficiency","Action Required","Source action"),
("T63","The <SOURCE_DOCUMENT> submitted for <CHECK_NAME> cannot be accepted because <VERIFICATION_BLOCKER>. Kindly provide <DOCUMENTS>. <DOCUMENT_REQUIREMENTS>","Insufficiency","Document","Wrong/Rejected (source substitution)"),
("T65","Kindly provide the complete address in <COUNTRY> for <CHECK_NAME>.","Insufficiency","Information","Missing (Address)"),
("T66","Kindly provide <DOCUMENTS> for <CHECK_NAME>. Please use the approved format available at <REFERENCE_URL>.","Insufficiency","Document","Missing (format-specific)"),
("T67","Kindly provide any one of the following documents for <CHECK_NAME>: <DOCUMENT_OPTIONS>.","Insufficiency","Document","Missing (OR-list)"),
("T68","The <DOCUMENTS> submitted for <CHECK_NAME> has expired. It is valid only for <VALIDITY_PERIOD> from the date of issue. Kindly provide a valid and current copy.","Insufficiency","Document","Expired (with validity period)"),
]


# Cost/TAT Approval templates all share reason_category="N/A" / reason_sub_type="N/A",
# so they'd collide in the dropdown tree without a distinguishing scenario label.
# This label becomes the 3rd-level dropdown option shown to the user for these
# two "flat" Insuff Categories (they don't use the Document/Information/Action
# Reason mechanism at all - Cost/TAT approval is its own short, independent flow).
SCENARIO_LABELS = {
    "T7": "Additional verification cost (on top of an already-approved cost)",
    "T8": "Revised total verification cost",
    "T50": "Verification cost for a specific country",
    "T60": "TAT extension request",
}

MERGED_FROM = {
    "T37": ["T56"], "T40": ["T58"], "T42": ["T43"], "T57": ["T39", "T48"],
    "T61": ["T55"],  # T55 (account-creation-specific) folds into T61's free-text PORTAL_ACTION
    "T59": ["T52"],  # T52 lacked explicit CHECK_NAME context; T59 is the clearer, check-scoped version
}
DROPPED_AS_DUPLICATE = {
    "T56": "T37", "T58": "T40", "T43": "T42", "T39": "T57", "T48": "T57",
    "T55": "T61", "T52": "T59",
}

REASON_NEEDED = {
    ("Document", "Missing"): "document.missing",
    ("Document", "Missing (Signed)"): "document.missing_signed",
    ("Document", "Missing (special instructions)"): "document.missing_special",
    ("Document", "Missing (format-specific)"): "document.missing_special",
    ("Information", "Missing"): "information.missing",
    ("Information", "Missing (Identifier)"): "information.missing_identifier",
    ("Information", "Missing (Case-level)"): "information.missing_case_level",
    ("Information", "Missing (Address)"): "information.missing_address",
}

import re
TAG_RE = re.compile(r"<([A-Za-z0-9_]+)>")

def build():
    reason_clauses = json.load(open(os.path.join(OUT_DIR, "reason_clauses.json")))
    templates = []
    for tid, text, cat, reason_cat, sub in RAW:
        raw_tags = TAG_RE.findall(text)
        has_course_vs = "COURSE_NAME" in raw_tags and "VS" in raw_tags
        has_vs_only = "VS" in raw_tags and "COURSE_NAME" not in raw_tags
        context_mode = "course_vs" if has_course_vs else ("vs_only" if has_vs_only else "check_only")

        entry = {
            "id": tid,
            "merged_from": MERGED_FROM.get(tid, []),
            "insuff_category": cat,
            "reason_category": reason_cat,
            "reason_sub_type": sub,
            "raw_text": text,
            "raw_tags": raw_tags,
            "context_mode": context_mode,
            "scenario_label": SCENARIO_LABELS.get(tid),
        }
        key = (reason_cat, sub)
        if key in REASON_NEEDED:
            clause_key = REASON_NEEDED[key]
            entry["optimized_text"] = reason_clauses[clause_key]
            entry["reason_clause_added"] = clause_key
            # tags needed by the clause itself (CONTEXT resolved separately by engine)
            clause_tags = re.findall(r"\{([A-Za-z0-9_]+)\}", reason_clauses[clause_key])
            entry["needed_tags"] = sorted(set(raw_tags) | {t for t in clause_tags if t != "CONTEXT"})
        else:
            entry["optimized_text"] = text
            entry["reason_clause_added"] = None
            entry["needed_tags"] = sorted(set(raw_tags))
        templates.append(entry)

    # (templates.json is written once, further down, after dropdown_path
    # metadata is computed - no need to write it twice.)

    # ---- Decision tree: Insuff Category -> Reason -> Sub-reason -> template id
    # (Cost/TAT Approval have no real Reason/Sub-reason - reason_category is
    # literally "N/A" for all their templates - so scenario_label stands in
    # as the 3rd-level key for those two categories to avoid collisions.)
    #
    # A SECOND collision exists within Insufficiency: the Course/VS-scoped
    # templates (T9-T18, e.g. "Missing" doc for a specific course from a
    # specific institute) share the exact same Reason/Sub-reason label as the
    # generic Check-scoped templates (T37-T68, e.g. "Missing" doc for the
    # check as a whole) - these are two genuinely different real-world
    # scenarios (common in Education, where one check can involve several
    # courses/degrees), not duplicates. So where BOTH a course_vs and a
    # check_only template exist for the same Reason/Sub-reason, the tree
    # stores a small {scope: template_id} map instead of one bare ID, and the
    # frontend asks one extra "is this about one specific course/degree, or
    # the check in general?" question before landing on the template.
    tree = {}
    scope_group = {}  # (cat, rc, sub) -> {context_mode: id}
    for t in templates:
        cat, rc = t["insuff_category"], t["reason_category"]
        sub = t["scenario_label"] or t["reason_sub_type"]
        scope_group.setdefault((cat, rc, sub), {})[t["context_mode"]] = t["id"]

    for (cat, rc, sub), modes in scope_group.items():
        tree.setdefault(cat, {}).setdefault(rc, {})
        tree[cat][rc][sub] = modes["check_only"] if list(modes.keys()) == ["check_only"] else \
            (list(modes.values())[0] if len(modes) == 1 else modes)

    json.dump(tree, open(os.path.join(OUT_DIR, "dropdown_tree.json"), "w"), indent=2)

    # ---- Dropdown-path metadata (added 2026-08-15 for the support-triage
    # step-guide): precompute, per template, exactly which UI steps a user
    # would click through to reach it, so search.php/SearchEngine.php doesn't
    # need to re-derive tree structure at request time.
    SCOPE_LABELS = {
        "course_vs": "A specific course/degree from a specific institute",
        "check_only": "General to this check (not tied to one course/institute)",
    }
    for t in templates:
        cat, rc = t["insuff_category"], t["reason_category"]
        sub = t["scenario_label"] or t["reason_sub_type"]
        group_modes = scope_group[(cat, rc, sub)]
        needs_scope = len(group_modes) > 1
        t["dropdown_path"] = {
            "insuff_category": cat,
            "reason_step_shown": rc != "N/A",
            "reason": rc if rc != "N/A" else None,
            "reason_detail": sub,
            "needs_scope_choice": needs_scope,
            "scope_value": t["context_mode"] if needs_scope else None,
            "scope_label": SCOPE_LABELS.get(t["context_mode"]) if needs_scope else None,
        }
    json.dump(templates, open(os.path.join(OUT_DIR, "templates.json"), "w"), indent=2)

    print(f"templates.json: {len(templates)} canonical templates "
          f"({sum(1 for t in templates if t['merged_from'])} absorbed duplicates, "
          f"{len(DROPPED_AS_DUPLICATE)} raw IDs merged away, "
          f"{sum(1 for t in templates if t['reason_clause_added'])} reason clauses injected)")
    print(f"dropdown_tree.json: categories = {list(tree.keys())}")
    for cat, reasons in tree.items():
        print(f"  {cat}: {list(reasons.keys())}")

if __name__ == "__main__":
    build()
