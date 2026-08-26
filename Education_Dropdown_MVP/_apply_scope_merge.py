#!/usr/bin/env python3
"""
One-off script (2026-08-18, fourth fix same session): eliminates the
course_vs / check_only Scope selector for 8 template pairs, replacing it
with a single template per reason where COURSE_NAME/VS/YEAR_FROM/YEAR_TO
become OPTIONAL rather than a forced either/or choice.

ROOT CAUSE this fixes: the owner tested the real comment "Require
B.Tech-Computer Science Engineering (B.Tech)Degree, Final year marksheet."
manually through the wizard and got a vague check_only-style comment
("Degree for Academic Reference Check was not submitted...") with no
course/institute mentioned at all - even though the comment (and the
underlying real dataset row, resolved_template_id=T37) clearly involves a
specific course. Quantified via data/search_index.json: of 2,067 real
comments resolved to T37 (Document/Missing, check_only), 1,245 (60%)
actually name a specific degree/course in the text but got routed to the
generic check_only path anyway - because the binary Scope choice makes it
trivially easy to lose that context, whether by a live agent picking the
wrong option or (as here) by the original classification pipeline failing
to extract COURSE_NAME cleanly. T57 (Wrong/Rejected, check_only) shows the
same pattern at 47% (34/72 rows).

FIX: rather than a wording/label patch (which only reduces the odds of the
mistake), merge each course_vs/check_only pair into ONE template with
context_mode "course_vs_optional": COURSE_NAME/VS/YEAR_FROM/YEAR_TO are
always available to fill in, never hidden behind a prior Scope choice, and
only become required TOGETHER if the agent starts filling any of them in
(enforced in php/CommentEngine.php's generate()). If left blank, the
comment reads exactly like the old check_only version. If filled, it reads
exactly like the old course_vs version. No more silent loss of course
context, no more Scope question to get wrong.

Merged (course_vs ID kept as the surviving template, check_only ID
retired):
  T9  <- T37   (Document / Missing)
  T10 <- T45   (Document / Blurred/Illegible)
  T11 <- T46   (Document / Incomplete)
  T12 <- T47   (Document / Expired)
  T13 <- T57   (Document / Wrong/Rejected)
  T14 <- T40   (Information / Missing)
  T15 <- T41   (Information / Missing - Identifier Number)
  T63 <- T64   (Document / Wrong/Rejected - Institution's Own Record)

NOT merged (kept exactly as-is, not clean 1:1 pairs):
  T17 / T61 (Action Required / Portal Action) - T61 has a free-text
    PORTAL_ACTION dimension T17 doesn't have; genuinely different shape.
  T18 (Information / Mismatch) - no check_only sibling ever existed; a
    mismatch inherently implies a specific prior value tied to a specific
    course, so forcing course context here was already correct.

Run once from this folder: python3 _apply_scope_merge.py
Kept in the repo as an audit trail (can't be deleted from this sandbox -
connected-folder delete protection).
"""
import json, os

BASE = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE, "data")

templates = json.load(open(os.path.join(DATA_DIR, "templates.json")))
tree = json.load(open(os.path.join(DATA_DIR, "dropdown_tree.json")))
by_id = {t["id"]: t for t in templates}

MERGES = {
    "T9": "T37",
    "T10": "T45",
    "T11": "T46",
    "T12": "T47",
    "T13": "T57",
    "T14": "T40",
    "T15": "T41",
    "T63": "T64",
}
CONDITIONAL_TAGS = {"COURSE_NAME", "VS", "YEAR_FROM", "YEAR_TO"}

for keep_id, retire_id in MERGES.items():
    t = by_id[keep_id]
    t["context_mode"] = "course_vs_optional"
    t["needed_tags"] = sorted(tag for tag in t["needed_tags"] if tag not in CONDITIONAL_TAGS)
    t["merged_from"] = sorted(set(t.get("merged_from", [])) | {retire_id})
    t["dropdown_path"]["needs_scope_choice"] = False
    t["dropdown_path"]["scope_value"] = None
    t["dropdown_path"]["scope_label"] = None
    t["reason_clause_added"] = (t.get("reason_clause_added") or "") + (
        f" [2026-08-18 fourth fix: merged with retired {retire_id} - COURSE_NAME/VS/YEAR_FROM/YEAR_TO "
        f"are now OPTIONAL here instead of behind a forced Scope choice, since real data showed the "
        f"large majority of real {retire_id}-resolved comments actually did reference a specific course.]"
    ).strip()

templates = [t for t in templates if t["id"] not in MERGES.values()]

def collapse_tree(node):
    """Recursively replace any {course_vs: X, check_only: Y} dict where X is a
    key in MERGES and Y is its retired partner with the flat surviving ID."""
    if not isinstance(node, dict):
        return node
    if set(node.keys()) == {"course_vs", "check_only"} and MERGES.get(node["course_vs"]) == node["check_only"]:
        return node["course_vs"]
    return {k: collapse_tree(v) for k, v in node.items()}

tree = collapse_tree(tree)

json.dump(templates, open(os.path.join(DATA_DIR, "templates.json"), "w"), indent=2)
json.dump(tree, open(os.path.join(DATA_DIR, "dropdown_tree.json"), "w"), indent=2)

print(f"templates.json: {len(templates)} templates ({len(MERGES)} pairs merged)")
print("dropdown_tree.json: collapsed", len(MERGES), "scope-choice nodes to flat IDs")

# Remap search_index.json rows pointing at retired IDs to their surviving partner
rows = json.load(open(os.path.join(DATA_DIR, "search_index.json")))
remap = MERGES.__class__({v: k for k, v in MERGES.items()})  # retired -> surviving
changed = 0
for r in rows:
    tid = r.get("resolved_template_id")
    if tid in remap:
        r["resolved_template_id"] = remap[tid]
        r["_remapped_note"] = (f"Originally resolved to retired {tid} - merged into {remap[tid]} "
                                f"(course_vs_optional unification, 2026-08-18 fourth fix).")
        changed += 1
json.dump(rows, open(os.path.join(DATA_DIR, "search_index.json"), "w"), indent=2)
print(f"search_index.json: remapped {changed} rows")
