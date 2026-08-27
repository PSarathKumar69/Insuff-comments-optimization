#!/usr/bin/env python3
"""
Faithful Python port of the redesigned php/SearchEngine.php (evaluate() +
buildSteps() + the 2026-08-15 hybrid local/Gemini escalation), used to
verify the support-triage logic without a PHP runtime (none available in
this sandbox - see PROGRESS_LOG.md).

The Gemini call itself is injected as a function (`gemini_classify`) rather
than making a real network call, so this script can verify the ESCALATION
DECISION and STEP-BUILDING logic deterministically. Whether the real Gemini
API actually classifies correctly is a separate, live concern - see
test_gemini_triage_design.py's docstring for why that couldn't be run live
in this sandbox (network policy blocks generativelanguage.googleapis.com
here), and PROGRESS_LOG.md's note on what to verify once deployed.

Run from this folder: python3 test_search_engine_logic.py
"""
import json, os, re

BASE = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE, "data")

# MIN_SCORE (0.15) removed 2026-08-26 to mirror php/SearchEngine.php - it only
# ever gated the weak local-fallback tier in evaluate(), which no longer exists.
# Revised 2026-08-15 (third fix): confidence is now about TEMPLATE agreement
# among near-top candidates, not a raw score gap between the top two rows -
# see SearchEngine.php's updated docstring for why the old score-margin
# check nearly always escalated on this duplicate-heavy dataset.
LOCAL_CONFIDENCE_FLOOR = 0.25
CLUSTER_TOLERANCE = 0.05
TOP_K = 8

SCOPE_FIELD_LABELS = {
    "course_vs": {"COURSE_NAME": "Course / degree name", "VS": "Institute name"},
    "vs_only": {"VS": "Institute / employer name"},
    # Added 2026-08-18 (fourth fix): mirrors php/SearchEngine.php's
    # course_vs_optional entry - these 8 merged templates offer
    # COURSE_NAME/VS/YEAR_FROM/YEAR_TO as optional-together fields.
    "course_vs_optional": {
        "COURSE_NAME": "Course / degree name",
        "VS": "Institute name",
        "YEAR_FROM": "Year started",
        "YEAR_TO": "Year completed",
    },
}
# Fixed 2026-08-19 (fifth pass): COURSE_NAME/VS used to be in this set
# unconditionally, on the assumption they're always rendered by the
# course_vs/vs_only/course_vs_optional branch. False for a "check_only"
# template using VS as a plain generic tag (T65) - see build_steps()'s
# context-conditional handling below, mirroring php/SearchEngine.php.
SKIP_TAGS = {"CHECK_NAME", "CONTEXT", "FORM_COMPANY_NAME"}


def normalize(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return [t for t in re.split(r"\s+", s.strip()) if len(t) > 2]


def score(q_tokens, r_tokens):
    if not q_tokens or not r_tokens:
        return 0.0
    q_set, r_set = set(q_tokens), set(r_tokens)
    inter = len(q_set & r_set)
    union = len(q_set | r_set)
    return inter / union if union else 0.0


def field_label(tag):
    return tag.replace("_", " ").title()


class SearchEngine:
    def __init__(self, data_dir, gemini_classify=None, gemini_configured=True):
        # Mirrors php/SearchEngine.php::__construct() as of 2026-08-27:
        # search_index.json is gitignored (real comment text / PII), so a
        # deployment or clone built from the repo alone has no index. Treat that
        # as an empty index instead of exploding on the next foreach.
        index_path = os.path.join(data_dir, "search_index.json")
        self.rows = json.load(open(index_path, encoding="utf-8")) if os.path.isfile(index_path) else []
        templates = json.load(open(os.path.join(data_dir, "templates.json")))
        self.templates_by_id = {t["id"]: t for t in templates}
        # Injected for testing: a function(query, templates, tag_values) -> dict|None,
        # standing in for GeminiTriageClient::classify() without a real network call.
        self.gemini_classify = gemini_classify
        self.gemini_configured = gemini_configured

    def find_top_matches(self, query, k=5):
        q_tokens = normalize(query)
        if not q_tokens:
            return []
        scored = []
        for row in self.rows:
            s = score(q_tokens, normalize(row["comment"]))
            if s > 0:
                row = dict(row)
                row["_score"] = s
                scored.append(row)
        scored.sort(key=lambda r: -r["_score"])
        return scored[:k]

    def build_steps(self, tpl, extracted_tags, suggested_documents):
        path = tpl["dropdown_path"]
        steps = []
        n = 1

        # Step-text labels renamed 2026-08-24, mirrors php/SearchEngine.php -
        # see its comment for why ("Insuff Category"/"Category" had drifted
        # out of sync with the current UI's Category/Sub-Category/Reason
        # labels).
        steps.append({"step": n, "instruction": f'Set "Category" to "{path["insuff_category"]}".'}); n += 1

        if path["reason_step_shown"]:
            steps.append({"step": n, "instruction": f'Set "Sub-Category" to "{path["reason"]}".'}); n += 1
        steps.append({"step": n, "instruction": f'Set "Reason" to "{path["reason_detail"]}".'}); n += 1

        # Scenario step REMOVED 2026-08-26, mirrors php/SearchEngine.php -
        # reason_detail now already carries the combined "{Reason} - {Scenario}"
        # text for the 21 Document/Information templates that used to need this.

        if path["needs_scope_choice"]:
            steps.append({"step": n, "instruction": f'Set "Scope" to "{path["scope_label"]}".'}); n += 1

        if tpl["context_mode"] in ("course_vs", "vs_only"):
            for tag, label in SCOPE_FIELD_LABELS[tpl["context_mode"]].items():
                suggestion = extracted_tags.get(tag)
                instr = f'Enter the "{label}"' + (f' (suggested from this comment: "{suggestion}")' if suggestion else '') + '.'
                steps.append({"step": n, "instruction": instr}); n += 1
        elif tpl["context_mode"] == "course_vs_optional":
            # Added 2026-08-18 (fourth fix): mirrors php/SearchEngine.php -
            # these 4 fields are optional-together, phrased differently from
            # the mandatory course_vs case above.
            any_suggested = any(extracted_tags.get(tag) for tag in SCOPE_FIELD_LABELS["course_vs_optional"])
            intro = ("This historical comment names a specific course/institute - fill in the following (all four together):"
                     if any_suggested else
                     "If this requirement is tied to a specific course/degree, fill in the following (all four together); otherwise leave them blank:")
            steps.append({"step": n, "instruction": intro}); n += 1
            for tag, label in SCOPE_FIELD_LABELS["course_vs_optional"].items():
                suggestion = extracted_tags.get(tag)
                instr = f'  - "{label}"' + (f' (suggested from this comment: "{suggestion}")' if suggestion else ' (optional)') + '.'
                steps.append({"step": n, "instruction": instr}); n += 1

        # Fixed 2026-08-19 (fifth pass): mirrors php/SearchEngine.php's
        # $contextHandledTags - only skip COURSE_NAME/VS/YEAR_FROM/YEAR_TO
        # here if the branch above already produced a step for them.
        context_handled_tags = {
            "course_vs": ["COURSE_NAME", "VS"],
            "vs_only": ["VS"],
            "course_vs_optional": ["COURSE_NAME", "VS", "YEAR_FROM", "YEAR_TO"],
        }.get(tpl["context_mode"], [])

        for tag in tpl["needed_tags"]:
            if tag in SKIP_TAGS or tag in context_handled_tags:
                continue
            if tag == "DOCUMENTS":
                suggested_docs = list(suggested_documents)
                if len(suggested_docs) == 0:
                    steps.append({"step": n, "instruction": 'Pick the required document from the "Document required" dropdown.'}); n += 1
                elif len(suggested_docs) == 1:
                    steps.append({"step": n, "instruction": f'Pick "{suggested_docs[0]}" from the "Document required" dropdown.'}); n += 1
                else:
                    first = suggested_docs.pop(0)
                    steps.append({"step": n, "instruction": f'Pick "{first}" from the "Document required" dropdown.'}); n += 1
                    for doc in suggested_docs:
                        steps.append({"step": n, "instruction": f'Click AND (or OR, if either document would satisfy this), then pick "{doc}".'}); n += 1
                continue

            # VS falling through here (fifth pass, 2026-08-19) means a check_only
            # template uses it as a plain generic tag (T65) - friendlier label.
            label = "Institute name" if tag == "VS" else field_label(tag)
            suggestion = extracted_tags.get(tag)
            instr = f'Fill in "{label}"' + (f' (suggested from this comment: "{suggestion}")' if suggestion else '') + '.'
            steps.append({"step": n, "instruction": instr}); n += 1

        if tpl["reason_category"] == "Document":
            steps.append({"step": n, "instruction": 'Optionally tick any relevant "Special instructions" (e.g. duly signed, both-side colour copy).'}); n += 1

        steps.append({"step": n, "instruction": 'The final comment renders automatically in the live preview as you complete the fields above — no separate "generate" click needed.'})
        return steps

    def evaluate_from_local_match(self, query, match):
        base = {
            "query": query, "matched_by": "local",
            "matched_historical_comment": match["comment"],
            "match_score": round(match["_score"], 2),
            "match_seen_count": match["count"],
        }
        if match["status"] == "template_exists_not_in_education_mvp":
            return {**base, "supported": False, "verdict_label": "Not supported (yet)",
                    "verdict_reason": f'The closest historical match resolves to template {match["resolved_template_id"]}, which exists in the wider template set but isn\'t wired into this Education build.',
                    "template_id": match["resolved_template_id"], "steps": []}
        if match["status"] == "not_supported" or not match["resolved_template_id"]:
            return {**base, "supported": False, "verdict_label": "Not supported",
                    "verdict_reason": 'The closest historical match itself was never resolved to a template.',
                    "template_id": None, "steps": []}
        tpl = self.templates_by_id.get(match["resolved_template_id"])
        if tpl is None:
            return {**base, "supported": False, "verdict_label": "Not supported",
                    "verdict_reason": f'Internal: resolved template {match["resolved_template_id"]} not found.',
                    "template_id": match["resolved_template_id"], "steps": []}
        return {**base, "supported": True, "verdict_label": "Supported",
                "verdict_reason": f'Matches template {tpl["id"]} ({tpl["insuff_category"]} / {tpl["reason_category"]} / {tpl["reason_sub_type"]}) - here\'s how to build it.',
                "template_id": tpl["id"],
                "steps": self.build_steps(tpl, match.get("extracted_tags", {}), match.get("suggested_documents", []))}

    def evaluate_from_gemini(self, query, gem, local_top):
        base = {"query": query, "matched_by": "gemini", "gemini_confidence": gem.get("confidence")}
        if local_top is not None:
            base["matched_historical_comment"] = local_top["comment"]
            base["match_score"] = round(local_top["_score"], 2)
            base["match_seen_count"] = local_top["count"]

        tid = gem.get("template_id") or "no_match"
        if tid == "no_match":
            return {**base, "supported": False, "verdict_label": "Not supported",
                    "verdict_reason": f'Gemini reviewed this comment against all templates and found no confident fit: {gem.get("reasoning", "")}',
                    "template_id": None, "steps": []}
        tpl = self.templates_by_id.get(tid)
        if tpl is None:
            return {**base, "supported": False, "verdict_label": "Not supported",
                    "verdict_reason": f'Gemini suggested template {tid}, which isn\'t valid in this build.',
                    "template_id": None, "steps": []}

        extracted_tags = {}
        for t in gem.get("extracted_tags", []):
            tag = t.get("tag")
            if not tag:
                continue
            extracted_tags[tag] = t.get("matched_dropdown_value") or t.get("raw_value")
        suggested_documents = [d for d in gem.get("suggested_documents", []) if d]

        return {**base, "supported": True, "verdict_label": "Supported",
                "verdict_reason": f'Gemini matched this to template {tpl["id"]} ({tpl["insuff_category"]} / {tpl["reason_category"]} / {tpl["reason_sub_type"]}, confidence: {gem.get("confidence")}) - here\'s how to build it.',
                "template_id": tpl["id"], "steps": self.build_steps(tpl, extracted_tags, suggested_documents)}

    def local_confidence(self, top):
        if not top or top[0]["_score"] < LOCAL_CONFIDENCE_FLOOR:
            return False
        top_score = top[0]["_score"]
        cluster = [r for r in top if r["_score"] >= top_score - CLUSTER_TOLERANCE]
        signatures = {(r.get("resolved_template_id"), r["status"]) for r in cluster}
        return len(signatures) == 1

    def not_supported_no_match(self, query, gemini_attempted, gemini_available):
        # Mirrors php/SearchEngine.php::notSupportedNoMatch() - reworded 2026-08-26
        # now that the Gemini-down branch is the only ambiguous-and-unresolvable
        # outcome, so "nothing matched, may need a new template" no longer fits it.
        reason = "This doesn't closely match anything in the classified historical dataset."
        if gemini_attempted and not gemini_available:
            reason = ("The closest keyword matches were either too weak or split across more than one"
                      " template to trust, and Gemini escalation was unavailable to break the tie - so"
                      " this is reported as unresolved rather than as a best guess. Pick the dropdown"
                      " path manually, or escalate.")
        return {
            "query": query, "matched_by": "gemini" if (gemini_attempted and gemini_available) else ("local_fallback" if gemini_attempted else "local"),
            "supported": False, "verdict_label": "Not supported",
            "verdict_reason": reason,
            "template_id": None, "steps": [], "matched_historical_comment": None, "match_score": 0.0,
        }

    def has_index(self):
        '''Mirrors php/SearchEngine.php::hasIndex().'''
        return bool(self.rows)

    def evaluate(self, query):
        # Mirrors php/SearchEngine.php::evaluate()'s no-index guard (2026-08-27):
        # with no index loaded, report the search as unavailable rather than
        # claiming the query matched nothing in a dataset that was never read.
        # Gemini is still tried, since it needs no local index.
        if not self.has_index():
            gem = self.gemini_classify(query) if (self.gemini_configured and self.gemini_classify) else None
            if gem is not None:
                return self.evaluate_from_gemini(query, gem, None)
            return {
                "query": query, "matched_by": "no_index", "supported": None,
                "verdict_label": "Search unavailable",
                "verdict_reason": "The historical comment index (data/search_index.json) is not present in this deployment, so a real comment cannot be matched to a dropdown path here. The dropdown generator itself is unaffected.",
                "template_id": None, "steps": [], "matched_historical_comment": None, "match_score": 0.0,
            }

        top = self.find_top_matches(query, TOP_K)

        if self.local_confidence(top):
            return self.evaluate_from_local_match(query, top[0])

        gemini_available = self.gemini_configured and self.gemini_classify is not None
        gem = self.gemini_classify(query) if gemini_available else None

        if gem is not None:
            return self.evaluate_from_gemini(query, gem, top[0] if top else None)

        # Mirrors php/SearchEngine.php::evaluate() as of 2026-08-26 (fifth fix):
        # local confidence failed AND Gemini is unavailable -> unresolved. The old
        # MIN_SCORE-gated "local_fallback" tier returned a green "Supported"
        # verdict with a full step guide for a match the engine had just rejected
        # as untrustworthy; see the PHP comment for the reported repro.
        return self.not_supported_no_match(query, True, False)


def run_tests():
    # ---- Part A: escalation-decision tests (the actual bug fix) ----
    print("=" * 100)
    print("PART A: hybrid escalation decision")
    print("=" * 100)

    engine_no_gemini = SearchEngine(DATA_DIR, gemini_classify=None)
    top = engine_no_gemini.find_top_matches("Requesting the extra TAT for verification", TOP_K)
    print("\nTAT query top matches (local only):")
    for r in top[:5]:
        print(f"  score={r['_score']:.3f} template={r['resolved_template_id']} | {r['comment'][:70]}")
    local_confident = engine_no_gemini.local_confidence(top)
    print("local_confidence (template-agreement based):", local_confident)
    assert not local_confident, "Expected the TAT query's top candidates to disagree on template, triggering escalation"
    print("PASS: TAT query correctly triggers Gemini escalation (top candidates disagree between T9 and T37, both wrong).")

    # Mocked Gemini correctly resolving the TAT query to T60.
    def mock_gemini_tat(query):
        return {
            "template_id": "T60", "confidence": "High",
            "reasoning": "Comment requests a TAT extension, matching the TAT Approval template.",
            "extracted_tags": [
                {"tag": "NO_OF_DAYS", "raw_value": "extra time (unspecified)", "matched_dropdown_value": None},
                {"tag": "VERIFICATION_BLOCKER", "raw_value": "pending third-party response"},
            ],
            "suggested_documents": [],
        }
    engine = SearchEngine(DATA_DIR, gemini_classify=mock_gemini_tat)
    result = engine.evaluate("Requesting the extra TAT for verification")
    print("\nWith Gemini escalation (mocked correct answer):")
    print("supported:", result["supported"], "| matched_by:", result["matched_by"], "| template:", result["template_id"])
    for s in result["steps"]:
        print(f"  Step {s['step']}: {s['instruction']}")
    assert result["supported"] is True
    assert result["template_id"] == "T60"
    assert result["matched_by"] == "gemini"
    print("PASS: mocked Gemini path produces the correct verdict (T60, TAT Approval) with a real step guide.")

    # Gemini unavailable -> does NOT crash, and does NOT claim "Supported" off an
    # ambiguous local match. Updated 2026-08-26 (fifth fix): this previously
    # asserted a "local_fallback" Supported best guess. The whole point of the
    # ambiguity check is that the engine has already decided it can't resolve this
    # query; dressing the rejected top-1 up as a green Supported verdict with a
    # full step guide is worse for the agent than saying "unresolved".
    engine_unavailable = SearchEngine(DATA_DIR, gemini_classify=None, gemini_configured=False)
    result_fallback = engine_unavailable.evaluate("Requesting the extra TAT for verification")
    print("\nWith Gemini unavailable (ambiguous -> unresolved):")
    print("supported:", result_fallback["supported"], "| matched_by:", result_fallback["matched_by"])
    print("verdict_reason:", result_fallback["verdict_reason"])
    assert result_fallback["matched_by"] == "local_fallback"
    assert result_fallback["supported"] is False
    assert result_fallback["verdict_label"] == "Not supported"
    assert result_fallback["template_id"] is None
    assert result_fallback["steps"] == []
    assert "Gemini escalation was unavailable" in result_fallback["verdict_reason"]
    print("PASS: Gemini-unavailable + ambiguous fails soft to an honest 'Not supported', not a crash and not a mislabeled best guess.")

    # A clear, unambiguous local match should NOT escalate (keep the fast path fast).
    engine_should_not_escalate = SearchEngine(DATA_DIR, gemini_classify=lambda q: (_ for _ in ()).throw(AssertionError("Gemini should not have been called for a confident local match")))
    supported_rows = [r for r in engine_should_not_escalate.rows if r["status"] == "supported"]
    # Find a row whose own comment is (near-)verbatim in the dataset - should score very high against itself.
    clean_sample = supported_rows[100]
    top_clean = engine_should_not_escalate.find_top_matches(clean_sample["comment"], TOP_K)
    print(f"\nControl case - exact historical comment re-submitted, top score: {top_clean[0]['_score']:.3f}")
    result_clean = engine_should_not_escalate.evaluate(clean_sample["comment"])
    print("supported:", result_clean["supported"], "| matched_by:", result_clean["matched_by"])
    assert result_clean["matched_by"] == "local"
    print("PASS: a confident, unambiguous local match bypasses Gemini entirely (fast path preserved).")

    # THE ACTUAL OVER-ESCALATION BUG: a paraphrased query (not a literal
    # duplicate of any stored row) whose best local match is clearly the
    # highest-scoring candidate (0.611), but the OLD logic still escalated it
    # because the runner-up (a different template, 0.556) was only 0.055
    # behind - just under the old 0.08 margin requirement. Nothing else scores
    # within 0.05 of the winner, so the new template-agreement check correctly
    # trusts it without asking Gemini. This is the dominant real-world pattern
    # behind the "every query hits Gemini" complaint: this dataset is full of
    # near-duplicate phrasings, so runner-up scores are almost always close
    # to the winner even when the winner is the clear right answer.
    dup_query = ("Required B.Tech Computer Science Engineering degree and all year marksheets, "
                 "final year marksheet to complete the verification from the engineering college.")
    engine_dup_check = SearchEngine(DATA_DIR, gemini_classify=lambda q: (_ for _ in ()).throw(AssertionError("Gemini should not have been called - top match is clear and nothing comparably-scored disagrees")))
    top_d = engine_dup_check.find_top_matches(dup_query, TOP_K)
    print("\nParaphrased case (would've wrongly escalated under the OLD margin logic):")
    print("Query:", dup_query)
    for r in top_d[:4]:
        print(f"  score={r['_score']:.3f} template={r['resolved_template_id']} | {r['comment'][:70]}")
    old_margin_confident = top_d[0]["_score"] >= 0.45 and (top_d[0]["_score"] - top_d[1]["_score"]) >= 0.08
    assert not old_margin_confident, "Expected the OLD margin logic to have flagged this ambiguous"
    result_dup = engine_dup_check.evaluate(dup_query)
    print("supported:", result_dup["supported"], "| matched_by:", result_dup["matched_by"])
    assert result_dup["matched_by"] == "local", "Expected the clear top match to stay on the fast local path"
    print("PASS: confirmed old logic would've escalated this; new logic correctly trusts the clear winner and stays local (no Gemini call).")

    # Measure the real-world impact: what fraction of realistic queries now
    # escalate vs. the old logic, using the dataset itself as a proxy for
    # real query variety (each row's own comment, run against all OTHER rows).
    import random
    random.seed(42)
    sample_rows = random.sample(engine_dup_check.rows, 40)
    old_escalate, new_escalate = 0, 0
    for row in sample_rows:
        top_r = [r for r in engine_dup_check.find_top_matches(row["comment"], TOP_K) if r["comment"] != row["comment"]]
        if not top_r:
            old_escalate += 1
            new_escalate += 1
            continue
        t1 = top_r[0]["_score"]
        t2 = top_r[1]["_score"] if len(top_r) > 1 else 0.0
        old_confident = t1 >= 0.45 and (t1 - t2) >= 0.08
        if not old_confident:
            old_escalate += 1
        if not engine_dup_check.local_confidence(top_r):
            new_escalate += 1
    print(f"\nEscalation-rate comparison over {len(sample_rows)} sampled real queries (self-excluded):")
    print(f"  OLD (raw score-margin) logic: {old_escalate}/{len(sample_rows)} escalate ({100*old_escalate/len(sample_rows):.0f}%)")
    print(f"  NEW (template-agreement) logic: {new_escalate}/{len(sample_rows)} escalate ({100*new_escalate/len(sample_rows):.0f}%)")
    assert new_escalate < old_escalate, "Expected the new logic to escalate meaningfully less often than the old logic"

    # ---- Part B: regression coverage on the existing local-only behaviors ----
    print("\n" + "=" * 100)
    print("PART B: regression - existing local-match behaviors unchanged")
    print("=" * 100)
    engine2 = SearchEngine(DATA_DIR, gemini_classify=None)

    # Tightened 2026-08-26: the old assertion ("supported, OR matched_by in
    # (gemini, local_fallback)") accepted every reachable outcome and so could
    # never fail. engine2 has no Gemini, so exactly two outcomes exist now - a
    # confident local Supported match, or an ambiguous one that is unresolved
    # with no template and no steps. Assert that pairing instead.
    sample = supported_rows[200]
    result = engine2.evaluate(sample["comment"])
    print("\nSupported real historical comment:", sample["comment"][:80])
    print("supported:", result["supported"], "| matched_by:", result["matched_by"], "| template:", result["template_id"])
    if result["matched_by"] == "local":
        assert result["supported"] is True
        assert result["template_id"] is not None
    else:
        assert result["matched_by"] == "local_fallback"
        assert result["supported"] is False
        assert result["template_id"] is None and result["steps"] == []

    partial_rows = [r for r in engine2.rows if r["status"] == "template_exists_not_in_education_mvp"]
    if partial_rows:
        sample2 = partial_rows[0]
        top2m = engine2.find_top_matches(sample2["comment"], TOP_K)
        if engine2.local_confidence(top2m):
            result2 = engine2.evaluate(sample2["comment"])
            print("\nOut-of-MVP-scope comment (confident local match):", sample2["comment"][:80])
            print("supported:", result2["supported"], "| verdict:", result2["verdict_label"])
            assert result2["supported"] is False

    result4 = engine2.evaluate("zzz qqq xyz nonsense query")
    print("\nGibberish query, no local match at all, Gemini not configured for this check:")
    engine_gibberish = SearchEngine(DATA_DIR, gemini_classify=None, gemini_configured=False)
    result4 = engine_gibberish.evaluate("zzz qqq xyz nonsense query")
    print("supported:", result4["supported"], "| verdict:", result4["verdict_label"])
    assert result4["supported"] is False
    assert result4["matched_historical_comment"] is None

    # ---- Part C: reported regression - ambiguous query must not report Supported ----
    # Added 2026-08-26. Reported case: "please provide the photograph with white
    # background" scores 0.333 locally (clears LOCAL_CONFIDENCE_FLOOR = 0.25) but
    # its near-top cluster splits across T9 and T13, so local_confidence() is
    # False. With Gemini unavailable, the old MIN_SCORE (0.15) fallback still
    # returned "Supported -> T9 (Document/Missing)" plus a full step guide - a
    # green badge for a template the engine had no basis to pick over T13.
    print("\n" + "=" * 100)
    print("PART C: ambiguous local match + Gemini unavailable -> Not supported")
    print("=" * 100)
    engine_amb = SearchEngine(DATA_DIR, gemini_classify=None, gemini_configured=False)
    amb_query = "please provide the photograph with white background"
    top_amb = engine_amb.find_top_matches(amb_query, TOP_K)
    cluster_templates = sorted(
        {r.get("resolved_template_id")
         for r in top_amb if r["_score"] >= top_amb[0]["_score"] - CLUSTER_TOLERANCE},
        key=lambda t: (t is None, t),
    )
    print("\nQuery:", amb_query)
    print(f"  top-1 score {top_amb[0]['_score']:.3f} vs floor {LOCAL_CONFIDENCE_FLOOR} -> clears the floor")
    print(f"  near-top cluster resolves to {cluster_templates} -> disagreement, so not confident")
    assert top_amb[0]["_score"] >= LOCAL_CONFIDENCE_FLOOR, "repro needs a top score above the floor"
    assert len(cluster_templates) > 1, "repro needs the near-top cluster to disagree on template"
    assert engine_amb.local_confidence(top_amb) is False

    result_amb = engine_amb.evaluate(amb_query)
    print("supported:", result_amb["supported"], "| verdict:", result_amb["verdict_label"],
          "| matched_by:", result_amb["matched_by"], "| template:", result_amb["template_id"])
    assert result_amb["supported"] is False, "ambiguous + no Gemini must not report Supported"
    assert result_amb["verdict_label"] == "Not supported"
    assert result_amb["template_id"] is None, "no template may be suggested when the match was rejected"
    assert result_amb["steps"] == [], "no step guide may be shown for an unresolved query"
    assert "Local best guess" not in result_amb["verdict_reason"]
    assert "Gemini escalation was unavailable" in result_amb["verdict_reason"]
    print("PASS: the reported ambiguous query returns 'Not supported' with no template and no step guide.")

    # Same query with Gemini reachable still resolves - confirms the fix removed
    # only the untrustworthy tier, it did not disable escalation itself.
    engine_amb_gem = SearchEngine(DATA_DIR, gemini_classify=lambda q: {
        "template_id": "T9", "confidence": "high",
        "extracted_tags": [], "suggested_documents": ["Photograph"],
    })
    result_amb_gem = engine_amb_gem.evaluate(amb_query)
    print("\nSame query with Gemini reachable:")
    print("supported:", result_amb_gem["supported"], "| matched_by:", result_amb_gem["matched_by"],
          "| template:", result_amb_gem["template_id"])
    assert result_amb_gem["supported"] is True
    assert result_amb_gem["matched_by"] == "gemini"
    assert result_amb_gem["template_id"] == "T9"
    print("PASS: with Gemini reachable the same query still resolves - escalation path untouched.")

    # ---- Part D: no search index deployed (Vercel / a fresh clone) ----
    # Added 2026-08-27. search_index.json is gitignored - it carries real
    # historical comment text with third-party PII - so any deployment built from
    # the repo alone starts without it. Before this, the constructor's
    # json_decode(file_get_contents(<missing>)) handed back null and the very next
    # foreach was fatal: a 500 on every search request. Now the dropdown generator
    # keeps working and search honestly reports itself unavailable.
    print("\n" + "=" * 100)
    print("PART D: no search_index.json present -> 'Search unavailable', not a crash")
    print("=" * 100)
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as tmp:
        # Same data dir minus the index; templates/tag_values still present.
        for f in ("templates.json", "tag_values.json", "dropdown_tree.json"):
            shutil.copy(os.path.join(DATA_DIR, f), os.path.join(tmp, f))
        assert not os.path.isfile(os.path.join(tmp, "search_index.json"))

        engine_noidx = SearchEngine(tmp, gemini_classify=None, gemini_configured=False)
        assert engine_noidx.has_index() is False
        r = engine_noidx.evaluate("please provide the degree certificate")
        print("matched_by:", r["matched_by"], "| verdict:", r["verdict_label"], "| supported:", r["supported"])
        assert r["matched_by"] == "no_index"
        assert r["verdict_label"] == "Search unavailable"
        assert r["supported"] is None, "must claim neither supported nor not-supported - it never looked"
        assert r["steps"] == [] and r["template_id"] is None
        assert "not present in this deployment" in r["verdict_reason"]
        # The misleading "nothing matched the dataset" line must not appear here.
        assert "closely match anything" not in r["verdict_reason"]
        print("PASS: missing index reports 'Search unavailable' instead of crashing or faking a verdict.")

        # Gemini needs no local index - it must still be tried, and still resolve.
        engine_noidx_gem = SearchEngine(tmp, gemini_classify=lambda q: {
            "template_id": "T9", "confidence": "high",
            "extracted_tags": [], "suggested_documents": ["Degree Certificate"],
        })
        r2 = engine_noidx_gem.evaluate("please provide the degree certificate")
        print("with Gemini reachable -> matched_by:", r2["matched_by"], "| template:", r2["template_id"])
        assert r2["matched_by"] == "gemini" and r2["template_id"] == "T9" and r2["supported"] is True
        assert r2["steps"], "Gemini path must still build a step guide with no local index"
        print("PASS: with no index but Gemini reachable, queries still resolve fully.")

    print("\nAll scenarios passed.")


if __name__ == "__main__":
    run_tests()
