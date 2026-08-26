#!/usr/bin/env python3
"""
One-off script (2026-08-18, third fix same session): cleans up confusing
bracketed/jargon Reason & Sub-reason labels the owner flagged from a live
screenshot of the "Reason" dropdown, and retires T16/T38 ("Missing
(Signed)") by merging their function into the base "Missing" reason +
the existing SPECIAL_INSTRUCTIONS mechanism (which already has "Duly signed
by the institution" / "Filled and hand-signed by the candidate" values) -
per the owner's explicit instruction: "if you find some special
instructions in them add them to respective tags here special
instructions."

Run once from this folder: python3 _apply_tag_cleanup.py
Then delete this script (kept only as an audit trail of exactly what
changed - see PROGRESS_LOG.md for the full write-up).
"""
import json, os

BASE = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE, "data")

templates = json.load(open(os.path.join(DATA_DIR, "templates.json")))
tree = json.load(open(os.path.join(DATA_DIR, "dropdown_tree.json")))

# ---------------------------------------------------------------------------
# 1. Retire T16/T38 ("Missing (Signed)") - their exact function (a Document
#    reason that additionally needs to be signed) is already fully covered
#    by picking base "Missing" (T9/T37) and ticking "Duly signed by the
#    institution" or "Filled and hand-signed by the candidate" in the
#    existing Special Instructions checkboxes, which already render for
#    every Document-category template. No template-specific tag was ever
#    needed for T16/T38 beyond what T9/T37 already ask for.
# ---------------------------------------------------------------------------
templates = [t for t in templates if t["id"] not in ("T16", "T38")]

# Remove from dropdown_tree.json: the nested {course_vs: T16, check_only: T38} entry
del tree["Insufficiency"]["Document"]["Missing (Signed)"]

# ---------------------------------------------------------------------------
# 2. Rename confusing bracketed/jargon labels to plain, dash-separated
#    wording (owner: "we should not have brackets... clean the values").
#    Renames both reason_sub_type/scenario_label AND the matching
#    dropdown_tree.json key + dropdown_path.reason_detail, so the UI and
#    the underlying template stay in sync. Keeps the leading keyword
#    ("Missing"/"Blurred"/"Incomplete"/"Expired"/"Wrong"/"Rejected") in
#    every renamed string, since php/CommentEngine.php's
#    combinedDocumentSentence() does a str_contains() check against these
#    exact substrings to pick the right lead-in wording for the
#    Mandatory+Any-one-of bulleted DOCUMENTS block.
# ---------------------------------------------------------------------------
RENAMES = {
    "Missing (Identifier)": "Missing - Identifier Number",
    "Wrong/Status (Contact outcome)": "Wrong / No Longer Valid - Contact Details",
    "Missing (Case-level)": "Missing - Case-level Information",
    "Mismatch (with verified value)": "Mismatch - Verified Value on File",
    "Wrong/Rejected (source substitution)": "Wrong/Rejected - Institution's Own Record",
    "Missing (Address)": "Missing - Address",
    "Missing (format-specific)": "Missing - Specific Format Required",
    "Expired (with validity period)": "Expired - State Validity Period",
    "Field Mismatch (Antecedent Contains)": "Field Mismatch - Conflicting Values",
    "Field Below Threshold (Antecedent Less Than)": "Field Below Minimum - Threshold Not Met",
    "Missing (special instructions)": "Missing - Company Details Required",
}
SCENARIO_RENAMES = {
    "Additional verification cost (on top of an already-approved cost)": "Additional Verification Cost - On Top of an Already-Approved Cost",
}

for t in templates:
    if t.get("reason_sub_type") in RENAMES:
        old = t["reason_sub_type"]
        t["reason_sub_type"] = RENAMES[old]
        if t.get("dropdown_path", {}).get("reason_detail") == old:
            t["dropdown_path"]["reason_detail"] = RENAMES[old]
    if t.get("scenario_label") in SCENARIO_RENAMES:
        old = t["scenario_label"]
        t["scenario_label"] = SCENARIO_RENAMES[old]
        if t.get("dropdown_path", {}).get("reason_detail") == old:
            t["dropdown_path"]["reason_detail"] = SCENARIO_RENAMES[old]

def rename_tree_keys(node, renames):
    if not isinstance(node, dict):
        return node
    new_node = {}
    for k, v in node.items():
        new_key = renames.get(k, k)
        new_node[new_key] = rename_tree_keys(v, renames) if isinstance(v, dict) else v
    return new_node

ALL_RENAMES = {**RENAMES, **SCENARIO_RENAMES}
tree = rename_tree_keys(tree, ALL_RENAMES)

json.dump(templates, open(os.path.join(DATA_DIR, "templates.json"), "w"), indent=2)
json.dump(tree, open(os.path.join(DATA_DIR, "dropdown_tree.json"), "w"), indent=2)

print(f"templates.json: {len(templates)} templates (T16/T38 retired)")
print("dropdown_tree.json: renamed", len(ALL_RENAMES), "labels, removed 'Missing (Signed)'")
