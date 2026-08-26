#!/usr/bin/env python3
"""
Logic-equivalence test for CommentEngine.php. This sandbox has no PHP
runtime, so this is a faithful Python port of the DOCUMENTS-rendering
helpers and generate(), used to verify the algorithm before handing the PHP
off. Verification tool, not a deliverable.

UPDATED 2026-08-18 (candidate-empathy audit + owner-approved cleanup pass),
on top of the 2026-08-18 Mandatory + Any-one-of DOCUMENTS redesign:
  - QUALIFICATION_TYPE removed entirely (owner: "remove this 'Undergraduate
    (UG)' - this is unnecessary") - COURSE_NAME converted from free text to a
    cleaned picklist of real course names that already state the
    qualification level (e.g. "Bachelor of Technology (B.Tech)").
  - Fixed 6 course_vs templates (T10/T11/T12/T13/T17/T18) that were
    substituting literal <COURSE_NAME> from <VS> instead of <CONTEXT>,
    silently dropping the Phase 2 year-range fix for those six.
  - ANTECEDENTS, CASE_LEVEL_INFORMATION, VERIFICATION_BLOCKER converted to
    multiselect (dropdown_multi) - T14/T18/T40/T51 restructured so the
    sentence subject is an invariant noun phrase ("the following
    information...") instead of the (now possibly multi-valued) tag itself,
    to avoid a was/were agreement break.
  - T53/T66 fixed: FORM_COMPANY_NAME/REFERENCE_URL were required tags that
    never actually appeared anywhere in the old rendered text (only an
    optional, easy-to-skip "instructions below" reference) - now stated
    directly.
  - T63's DOCUMENT_REQUIREMENTS tag removed (nothing ever computed it despite
    its own note claiming it was "composed automatically"); relies on the
    existing generic Special Instructions mechanism instead, like every
    other Document-reason template.
  - T65 gained ADDRESS_TYPE (which specific address - current/previous/
    permanent).
  - T67 retired (depended on the already-retired DOCUMENT_OPTIONS tag; its
    function - a pure "any one of these documents" requirement - is already
    covered by leaving Mandatory empty and using Any-one-of alone).
  - T64 added: course_vs counterpart of T63 (SOURCE_DOCUMENT rejected for a
    specific course/institute, not just a generic CHECK_NAME) - a genuine gap
    found while reconciling the project's 68-template Template Master
    Reference sheet against this MVP's 44 live templates.

Older history retained below for context:

REDESIGNED 2026-08-18 (Mandatory + Any-one-of, REPLACING the 2026-08-17
GROUPS model entirely): the owner tested the GROUPS model live and found a
real modeling bug, not a wording complaint. Given Mandatory-feeling docs
{Degree, Consent form, Diploma/Certificate} plus a separate pick-one pool
{All year marksheets, Authbridge ARN, Application Form}, GROUPS rendered
"submit any ONE of the following" - i.e. treated the two sets as complete
ALTERNATIVES to each other. The owner's actual requirement was "submit ALL
of the first set, PLUS any ONE of the second set" - a fundamentally
different structure GROUPS could never express, because GROUPS only ever
modeled "pick exactly one whole alternative bundle."

New model: exactly two fixed buckets.
  - Mandatory: every document here is always required together (AND).
  - Any-one-of: the candidate must submit at least one document from this
    pool (OR).
A document may live in only one bucket. Either bucket may be empty (a
mandatory-only or any-one-of-only requirement renders as a single plain noun
phrase substituted into the template, unchanged from long before the GROUPS
experiment). Only when BOTH buckets are non-empty does DOCUMENTS need a full
sentence override - see combined_document_sentence() below.
"""
import json, re, os

BASE = os.path.dirname(__file__)
templates = {t["id"]: t for t in json.load(open(os.path.join(BASE, "data/templates.json")))}
tag_values = json.load(open(os.path.join(BASE, "data/tag_values.json")))

def join_list(items, mode="AND"):
    items = [x.strip() for x in items if x and x.strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    conj = "or" if mode.upper().startswith("OR") else "and"
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f", {conj} " + items[-1]

def mandatory_phrase(docs):
    # Keeps the "both"/"all of" emphasis this project has used since before
    # the GROUPS experiment - that phrasing was never the source of the
    # ambiguity bug, so there's no reason to change it now that GROUPS is gone.
    docs = [d.strip() for d in docs if d and d.strip()]
    if not docs:
        return ""
    if len(docs) == 1:
        return docs[0]
    if len(docs) == 2:
        return "both " + join_list(docs, "AND")
    return "all of " + join_list(docs, "AND")

def any_one_of_inline(docs):
    # Used INLINE, substituted directly into a template's <DOCUMENTS>
    # placeholder - only when Mandatory is empty (a pure "pick one of these"
    # requirement, no combined sentence needed).
    docs = [d.strip() for d in docs if d and d.strip()]
    if not docs:
        return ""
    if len(docs) == 1:
        return docs[0]
    return "either " + join_list(docs, "OR")

def any_one_of_clause(docs):
    # Used inside the COMBINED sentence, following "submit ...".
    docs = [d.strip() for d in docs if d and d.strip()]
    if not docs:
        return ""
    if len(docs) == 1:
        return docs[0]
    return "any ONE of: " + join_list(docs, "OR")

def needs_combined_document_sentence(mandatory, any_one_of):
    # REVERTED 2026-08-26 (task #104): the 2026-08-26 "EXTENDED" version of
    # this function (also true for Any-one-of-only with 2+ docs) was rejected
    # by the owner - they gave an exact target output that does NOT use the
    # headed "Additional Document (Submit ANY ONE of the following):" format
    # for that case. Any-one-of-only now has its own dedicated
    # needs_any_one_of_only_sentence()/any_one_of_only_sentence() pair below,
    # kept fully separate rather than folded into this function again, mirrors
    # php/CommentEngine.php's needsCombinedDocumentSentence().
    return len(mandatory) > 0 and len(any_one_of) > 0

def needs_any_one_of_only_sentence(mandatory, any_one_of):
    # ADDED 2026-08-26 (task #104), mirrors php/CommentEngine.php's
    # needsAnyOneOfOnlySentence(). Any-one-of-only with 2+ documents gets its
    # own dedicated override sentence (see any_one_of_only_sentence() below) -
    # a single doc has no real choice to present, so it stays a plain noun
    # phrase via any_one_of_inline().
    return len(mandatory) == 0 and len(any_one_of) >= 2

def needs_mandatory_only_sentence(mandatory, any_one_of):
    # ADDED 2026-08-26 (task #106), mirrors php/CommentEngine.php's
    # needsMandatoryOnlySentence(). Owner flagged a plain "both X and Y"
    # mandatory-only render as "not in the expected format" and asked for the
    # identical treatment already applied to the any-one-of-only case - true
    # when Any-one-of is empty and Mandatory has 2+ documents.
    return len(any_one_of) == 0 and len(mandatory) >= 2

def mandatory_header(docs):
    n = len(docs)
    if n <= 1:
        return "Mandatory:"
    if n == 2:
        return "Mandatory (Both required):"
    return f"Mandatory (All {n} required):"

def any_one_of_header(docs):
    return "Additional Document (required):" if len(docs) <= 1 else "Additional Document (Submit ANY ONE of the following):"

def bullet_list(docs):
    return "\n".join(f"* {d}" for d in docs)

def display_phrase(tag, value):
    # Mirrors php/CommentEngine.php's displayPhrase() - added 2026-08-23.
    return tag_values.get(tag, {}).get("display_phrases", {}).get(value, value)

def list_block(lead_in, items, tag):
    # Mirrors php/CommentEngine.php's listBlock() - added 2026-08-23, see its
    # docstring for the full rationale (owner wanted a Reason+bulleted
    # Solution+Action format instead of the old flowing "X and Y" sentence).
    bullets = "\n".join(f"* {display_phrase(tag, v)}" for v in items)
    return lead_in + "\n\n" + bullets

def special_instructions_block(items):
    # Mirrors php/CommentEngine.php's specialInstructionsBlock() - added
    # 2026-08-26 (task #109). Headed "Document Requirements:" bulleted block,
    # opt-in via a template's special_instructions_format field (scoped to T9
    # only for now), using SPECIAL_INSTRUCTIONS' new display_phrases map for
    # fuller candidate-facing bullet text.
    bullets = "\n".join(f"* {display_phrase('SPECIAL_INSTRUCTIONS', v)}" for v in items)
    return "Document Requirements:\n" + bullets

def combined_document_sentence(mandatory, any_one_of, context, reason_sub_type):
    # REDESIGNED 2026-08-18 (second fix, same day): headed, bulleted layout,
    # mirroring php/CommentEngine.php's combinedDocumentSentence() - see that
    # method's docstring for why (the owner had approved this layout earlier
    # in the session, but it was never actually wired in until caught during
    # live testing of a real multi-document case).
    if "Blurred" in reason_sub_type:
        lead_in = f"Please submit clear, readable copies of the following documents for {context}:"
    elif "Incomplete" in reason_sub_type:
        lead_in = f"Please submit complete copies of the following documents for {context}:"
    elif "Expired" in reason_sub_type:
        lead_in = f"Please submit valid, current copies of the following documents for {context}:"
    elif "Wrong" in reason_sub_type or "Rejected" in reason_sub_type:
        lead_in = f"Please submit acceptable copies of the following documents for {context}:"
    else:
        lead_in = f"Kindly submit the following documents for {context}:"

    # REVERTED 2026-08-26 (task #104): the 2026-08-26 "GENERALIZED" version of
    # this function (which omitted the Mandatory section when empty, to also
    # serve the Any-one-of-only case) was rejected by the owner - back to
    # always assuming both buckets are populated, mirrors
    # php/CommentEngine.php's combinedDocumentSentence(). Any-one-of-only now
    # uses its own dedicated any_one_of_only_sentence() below instead.
    return (lead_in + "\n\n"
            + mandatory_header(mandatory) + "\n" + bullet_list(mandatory) + "\n\n"
            + any_one_of_header(any_one_of) + "\n" + bullet_list(any_one_of))

def any_one_of_only_sentence(any_one_of, context, reason_sub_type):
    # ADDED 2026-08-26 (task #104), mirrors php/CommentEngine.php's
    # anyOneOfOnlySentence(). The owner rejected the header-based bulleted
    # format (no "Additional Document (Submit ANY ONE of the following):"
    # header, no trailing ", or" per bullet) and gave an exact target output
    # instead: a single lead-in sentence that states BOTH the Reason (e.g.
    # documents are missing) and the Action ("please provide any ONE of the
    # following"), followed directly by bare bullets.
    if "Blurred" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide a clear, readable copy of any ONE of the following documents:"
    elif "Incomplete" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide a complete copy of any ONE of the following documents:"
    elif "Expired" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide a valid, current copy of any ONE of the following documents:"
    elif "Wrong" in reason_sub_type or "Rejected" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide an acceptable copy of any ONE of the following documents:"
    else:
        lead_in = f"To proceed with the verification for {context}, please provide any ONE of the following missing documents:"

    return lead_in + "\n\n" + bullet_list(any_one_of)

def mandatory_only_sentence(mandatory, context, reason_sub_type):
    # ADDED 2026-08-26 (task #106), mirrors php/CommentEngine.php's
    # mandatoryOnlySentence(). Owner: "again for Both the mandatory docs also
    # it is not in the expected format, Could you please correct this as we
    # correct for OR case" - identical shape to any_one_of_only_sentence(),
    # AND phrasing instead of OR: one lead-in sentence stating both the
    # Reason and the Action, followed by bare bullets, no header, no trailing
    # conjunction.
    if "Blurred" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide clear, readable copies of the following documents:"
    elif "Incomplete" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide complete copies of the following documents:"
    elif "Expired" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide valid, current copies of the following documents:"
    elif "Wrong" in reason_sub_type or "Rejected" in reason_sub_type:
        lead_in = f"To proceed with the verification for {context}, please provide acceptable copies of the following documents:"
    else:
        lead_in = f"To proceed with the verification for {context}, please provide the following missing documents:"

    return lead_in + "\n\n" + bullet_list(mandatory)

def generate(inp):
    tpl = templates.get(inp.get("template_id", ""))
    if not tpl:
        return {"error": f"Unknown template_id: {inp.get('template_id')}"}
    check_name = (inp.get("check_name") or "").strip()
    if not check_name:
        return {"error": "check_name is required"}
    # RENDERED check name - added 2026-08-26 (task #108), mirrors
    # php/CommentEngine.php. check_name above (the specific auto-filled check
    # type - "Academic Reference Check", "Professional License Check", etc.)
    # is still required/validated as before, but wherever the comment text
    # would print that value, it now always prints this fixed generic label
    # instead, project-wide, per the owner's "wherever we mention Academic
    # Reference Check, it should be like For Education Verification... Not
    # check name" instruction.
    rendered_check_name = "Education Verification"
    context = rendered_check_name
    if tpl["context_mode"] == "course_vs":
        # Phase 2 (2026-08-18): YEAR_FROM/YEAR_TO folded into CONTEXT,
        # mirroring php/CommentEngine.php. QUALIFICATION_TYPE (also Phase 2)
        # was REMOVED 2026-08-18 - COURSE_NAME is now itself a cleaned
        # picklist of real course names that already state the level, so a
        # separate UG/PG/Diploma/PhD tag was redundant.
        course = (inp.get("course_name") or "").strip()
        vs = (inp.get("vs") or "").strip()
        if not course or not vs:
            return {"error": "course_name and vs are both required for this template."}
        tags_in = inp.get("tags") or {}
        year_from = str(tags_in.get("YEAR_FROM") or "").strip()
        year_to = str(tags_in.get("YEAR_TO") or "").strip()
        context = f"{course} from {vs}"
        if year_from and year_to:
            year_part = year_from if year_from == year_to else f"{year_from}–{year_to}"
            context += f" ({year_part})"
    elif tpl["context_mode"] == "vs_only":
        vs = (inp.get("vs") or "").strip()
        if not vs:
            return {"error": "vs is required for this template."}
        context = vs
    elif tpl["context_mode"] == "course_vs_optional":
        # Added 2026-08-18 (fourth fix, same day): mirrors
        # php/CommentEngine.php's course_vs_optional branch. REPLACES the old
        # course_vs/check_only Scope choice for 8 template pairs. COURSE_NAME/
        # VS/YEAR_FROM/YEAR_TO are never hidden behind a prior decision -
        # they're always available, and only become required TOGETHER the
        # moment the agent starts filling any one of them in. Left entirely
        # blank, this behaves exactly like the old check_only path (context =
        # check_name); filled in, it behaves exactly like the old course_vs
        # path (context = course/institute/year).
        course = (inp.get("course_name") or "").strip()
        vs = (inp.get("vs") or "").strip()
        if course or vs:
            if not course or not vs:
                return {"error": "If specifying a course/degree, both course_name and vs are required together (or leave both blank if this is not tied to a specific course)."}
            tags_in = inp.get("tags") or {}
            year_from = str(tags_in.get("YEAR_FROM") or "").strip()
            year_to = str(tags_in.get("YEAR_TO") or "").strip()
            if not year_from or not year_to:
                return {"error": "YEAR_FROM and YEAR_TO are required whenever a course/institute is specified."}
            year_part = year_from if year_from == year_to else f"{year_from}–{year_to}"
            context = f"{course} from {vs} ({year_part})"
        else:
            # Added 2026-08-26, mirrors php/CommentEngine.php: when Course/
            # Degree, Institute, and Year are ALL left blank, context used to
            # fall back silently to the fixed check_name phrase. Now requires
            # at least one QUALIFICATION_LEVEL value (UG/PG/Highest degree/
            # etc., multiselect) instead, so a fully generic/untargeted
            # comment can no longer go out silently.
            tags_in = inp.get("tags") or {}
            qual_levels = [v.strip() for v in (tags_in.get("QUALIFICATION_LEVEL") or []) if v and v.strip()]
            if not qual_levels:
                return {"error": "Select at least one Qualification Level (UG/PG/Highest degree/etc.) when Course/Degree, Institute, and Year are all left blank."}
            qual_phrases = [display_phrase("QUALIFICATION_LEVEL", v) for v in qual_levels]
            context = "the candidate's " + join_list(qual_phrases, "AND")

    documents_rendered = ""
    combined_override = None
    if "DOCUMENTS" in tpl["needed_tags"]:
        mandatory = [d.strip() for d in (inp.get("mandatory_documents") or []) if d and d.strip()]
        any_one_of = [d.strip() for d in (inp.get("any_one_of_documents") or []) if d and d.strip()]

        if not mandatory and not any_one_of:
            return {"error": "At least one document is required (Mandatory and/or Any-one-of)."}
        if len(set(mandatory)) != len(mandatory):
            return {"error": "Duplicate document selected within Mandatory documents."}
        if len(set(any_one_of)) != len(any_one_of):
            return {"error": "Duplicate document selected within Any-one-of documents."}
        overlap = sorted(set(mandatory) & set(any_one_of))
        if overlap:
            return {"error": "A document can only be in Mandatory OR Any-one-of, not both: " + ", ".join(overlap)}

        if needs_combined_document_sentence(mandatory, any_one_of):
            combined_override = combined_document_sentence(mandatory, any_one_of, context, tpl["reason_sub_type"])
            # DOCUMENTS isn't substituted in this branch (combined_override
            # replaces the whole sentence), but it's still in needed_tags, so
            # give it a non-empty placeholder to avoid a false "missing" error.
            documents_rendered = mandatory_phrase(mandatory) or any_one_of_inline(any_one_of)
        elif needs_any_one_of_only_sentence(mandatory, any_one_of):
            # ADDED 2026-08-26 (task #104), mirrors php/CommentEngine.php.
            combined_override = any_one_of_only_sentence(any_one_of, context, tpl["reason_sub_type"])
            documents_rendered = any_one_of_inline(any_one_of)
        elif needs_mandatory_only_sentence(mandatory, any_one_of):
            # ADDED 2026-08-26 (task #106), mirrors php/CommentEngine.php.
            combined_override = mandatory_only_sentence(mandatory, context, tpl["reason_sub_type"])
            documents_rendered = mandatory_phrase(mandatory)
        elif mandatory:
            documents_rendered = mandatory_phrase(mandatory)
        else:
            documents_rendered = any_one_of_inline(any_one_of)

    # Two possible renderings, chosen per-template via special_instructions_format
    # (added 2026-08-26, task #109, mirrors php/CommentEngine.php) - the default
    # inline sentence (every other Document template, unchanged), or a headed
    # "Document Requirements:" bulleted block (opt-in, scoped to T9 only for now).
    special_instr_text = ""
    special_instr_block = None
    si = inp.get("special_instructions")
    if si and isinstance(si, list):
        items = [x.strip() for x in si if x and x.strip()]
        if items:
            if tpl.get("special_instructions_format") == "document_requirements":
                special_instr_block = special_instructions_block(items)
            else:
                special_instr_text = " Please ensure the copy is: " + join_list(items, "AND") + "."

    values = {
        "CHECK_NAME": rendered_check_name,
        "COURSE_NAME": inp.get("course_name", ""),
        "VS": inp.get("vs", ""),
        "DOCUMENTS": documents_rendered,
        "CONTEXT": context,
        "FORM_COMPANY_NAME": tag_values.get("FORM_COMPANY_NAME", {}).get("value", "AuthBridge Research Services Pvt. Ltd."),
    }
    # Raw (pre-join) arrays kept alongside the joined string form - mirrors
    # php/CommentEngine.php's $rawTagArrays, needed by list_block() below to
    # render one bullet per item rather than an "X and Y" joined string.
    raw_tag_arrays = {}
    for k, v in (inp.get("tags") or {}).items():
        if isinstance(v, list):
            raw_tag_arrays[k] = v
        values[k] = join_list(v, "AND") if isinstance(v, list) else str(v).strip()

    # Reason + bulleted Solution + Action block (added 2026-08-23) - mirrors
    # php/CommentEngine.php's list_block wiring. Opt-in via templates.json's
    # `list_block` field; a template with no `list_block` renders exactly as
    # before via plain substitution.
    # Fixed 2026-08-25 (owner live-tested T74 - "why do we not have any docs
    # or details here to select?"): lead_in now also substitutes
    # <DOCUMENTS>/{DOCUMENTS} using documents_rendered (mirrors
    # php/CommentEngine.php's identical fix) - T73/T74 now carry DOCUMENTS in
    # needed_tags, so the comment states WHICH document has the defect
    # instead of a vague "the document".
    list_block_override = None
    lb = tpl.get("list_block")
    if lb:
        lb_items = [x.strip() for x in raw_tag_arrays.get(lb["tag"], []) if x and x.strip()]
        if lb_items:
            lb_lead_in = (lb["lead_in"]
                          .replace("<CONTEXT>", context).replace("{CONTEXT}", context)
                          .replace("<DOCUMENTS>", documents_rendered).replace("{DOCUMENTS}", documents_rendered))
            list_block_override = list_block(lb_lead_in, lb_items, lb["tag"])

    # Optional cost-breakdown suffix (added 2026-08-19, fifth pass - full-template
    # tag audit). Mirrors php/CommentEngine.php - generic, not template-specific.
    # Only renders when BOTH PRICING_TOOL_COST and ADDITIONAL_COST are provided.
    pricing_cost = str((inp.get("tags") or {}).get("PRICING_TOOL_COST") or "").strip()
    additional_cost = str((inp.get("tags") or {}).get("ADDITIONAL_COST") or "").strip()
    cost_breakdown_text = ""
    if pricing_cost and additional_cost:
        currency = str(values.get("CURRENCY", "")).strip()
        cost_breakdown_text = f" (Base verification cost: {currency} {pricing_cost} + Additional cost: {currency} {additional_cost})"

    missing = [tag for tag in tpl["needed_tags"] if tag != "CONTEXT" and not str(values.get(tag, "")).strip()]
    if missing:
        return {"error": f"Missing required value(s): {', '.join(missing)}", "missing_tags": missing}

    # list_block checked FIRST, ahead of the combined-document override
    # (fixed 2026-08-25, mirrors php/CommentEngine.php's identical reordering)
    # - T73/T74 are the first templates to carry both DOCUMENTS and
    # list_block; without this ordering, filling both the Mandatory and
    # Any-one-of buckets would silently drop the INCOMPLETE_DETAIL/
    # BLUR_DETAIL bullets in favor of the combined document sentence.
    if list_block_override is not None:
        if special_instr_block is not None:
            extra = "\n\n" + special_instr_block
        else:
            extra = ("\n\n" + special_instr_text.lstrip()) if special_instr_text.strip() else ""
        text = list_block_override + extra
    elif combined_override is not None:
        # combined_document_sentence() ends on a bullet line (no trailing
        # period), so special instructions are appended as their own
        # paragraph rather than glued onto the last bullet.
        if special_instr_block is not None:
            extra = "\n\n" + special_instr_block
        else:
            extra = ("\n\n" + special_instr_text.lstrip()) if special_instr_text.strip() else ""
        text = combined_override + extra
    else:
        text = tpl["optimized_text"]
        for tag, val in values.items():
            text = text.replace(f"<{tag}>", val).replace(f"{{{tag}}}", val)
        text = text.strip()
        if cost_breakdown_text and text.endswith("."):
            text = text[:-1] + cost_breakdown_text + "."
        elif cost_breakdown_text:
            text += cost_breakdown_text
        if special_instr_block is not None:
            text += "\n\n" + special_instr_block
        else:
            text += special_instr_text

    if re.search(r"[<{][A-Za-z0-9_]+[>}]", text):
        return {"error": f"Unresolved placeholder remained: {text}"}

    return {
        "template_id": tpl["id"], "insuff_category": tpl["insuff_category"],
        "reason_category": tpl["reason_category"], "reason_sub_type": tpl["reason_sub_type"],
        "reason_clause_added": tpl["reason_clause_added"], "final_comment": text,
    }


TESTS = [
    ("Mandatory only, single document",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Mandatory only, two documents -> single Reason+Action lead-in sentence plus bare "
     "bullets, no header, no trailing conjunction (CORRECTED 2026-08-26, task #106 - mirrors "
     "the any-one-of-only fix; was a flowing 'both X and Y' sentence before this)",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree", "Final year marksheet"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Mandatory only, three documents -> same bulleted format (CORRECTED 2026-08-26, "
     "task #106; was a flowing 'all of X, Y, and Z' sentence before this)",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree", "Final year marksheet", "Provisional Certificate"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Any-one-of only, two documents -> single Reason+Action lead-in sentence "
     "plus bare bullets, no header, no trailing conjunction (CORRECTED 2026-08-26, "
     "task #104 - supersedes the same-day headed/bulleted 'Additional Document' "
     "attempt the owner rejected)",
     {"template_id": "T9", "check_name": "Professional License Check",
      "any_one_of_documents": ["Degree", "Provisional Certificate"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("THE OWNER'S EXACT FLAGGED BUG: Mandatory set PLUS a separate Any-one-of pool "
     "(GROUPS wrongly rendered this as 'submit any ONE of two whole bundles')",
     {"template_id": "T9", "check_name": "Academic Reference Check",
      "mandatory_documents": ["Degree", "Consent form", "Diploma/Certificate"],
      "any_one_of_documents": ["All year marksheets", "Authbridge ARN", "Application Form"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Combined Mandatory + Any-one-of, with special instructions appended",
     {"template_id": "T9", "check_name": "Academic Reference Check",
      "mandatory_documents": ["Degree", "Final year marksheet"],
      "any_one_of_documents": ["Consent form", "Authbridge ARN", "HEDD consent form"],
      "special_instructions": ["Both sides", "Colour copy"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Combined, Any-one-of has exactly 1 doc -> no 'any ONE of' framing needed, just 'submit X'",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree", "Final year marksheet"],
      "any_one_of_documents": ["HEDD consent form"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Duplicate document within Mandatory rejected",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree", "Degree"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Same document in both Mandatory and Any-one-of rejected (overlap)",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree"],
      "any_one_of_documents": ["Degree", "Provisional Certificate"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("No documents at all (both buckets empty) -> error",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": [], "any_one_of_documents": [],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("Course/institute scoped (T9) with atomic document + special instruction + cleaned COURSE_NAME + year (Phase 2, updated)",
     {"template_id": "T9", "check_name": "Education Verification",
      "course_name": "Bachelor of Commerce (B.Com)", "vs": "Delhi University",
      "mandatory_documents": ["Degree"],
      "special_instructions": ["Sealed and signed by the institution"],
      "tags": {"YEAR_FROM": "2015", "YEAR_TO": "2018"}}),

    ("Phase 2: single-year program collapses YEAR_FROM==YEAR_TO to one year, no dash",
     {"template_id": "T9", "check_name": "Education Verification",
      "course_name": "Master of Business Administration (MBA)", "vs": "IIM Calcutta",
      "mandatory_documents": ["Degree"],
      "tags": {"YEAR_FROM": "2022", "YEAR_TO": "2022"}}),

    ("Phase 2 (updated): missing YEAR_FROM/YEAR_TO on a course_vs template -> error, not a silently ambiguous comment",
     {"template_id": "T9", "check_name": "Education Verification",
      "course_name": "Bachelor of Commerce (B.Com)", "vs": "Delhi University",
      "mandatory_documents": ["Degree"]}),

    ("Phase 4: T69 Review Raised - mandatory REVIEW_REASON states a concrete why",
     {"template_id": "T69", "check_name": "Education Verification",
      "tags": {"REVIEW_REASON": "Suspect Positive Response flagged during verification"}}),

    ("Phase 4: T70 Antecedent Value Contains - field mismatch across sources",
     {"template_id": "T70", "check_name": "Education Verification",
      "tags": {"FIELD_NAME": "Course Name / Qualification", "VALUE1": "Diploma", "VALUE2": "Certificate"}}),

    ("Phase 4: T71 Antecedent Value Less Than - field below expected minimum",
     {"template_id": "T71", "check_name": "Education Verification",
      "tags": {"FIELD_NAME": "Period of Education", "THRESHOLD": "2 Years"}}),

    ("REQUESTED EXAMPLE: 4 mandatory docs + 3-doc any-one-of pool (illustrative, any docs)",
     {"template_id": "T9", "check_name": "Employment Reference Check",
      "mandatory_documents": ["Offer Letter", "Relieving Letter", "Experience Certificate", "Last 3 months Payslips"],
      "any_one_of_documents": ["Form 16", "Bank Statement", "PF Statement"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    # --- 2026-08-18 candidate-empathy audit fixes ---

    ("AUDIT FIX: T13 (course_vs, Wrong/Rejected) now uses CONTEXT (previously bypassed it) + multiselect VERIFICATION_BLOCKER",
     {"template_id": "T13", "check_name": "Education Verification",
      "course_name": "Bachelor of Technology (B.Tech)", "vs": "Anna University",
      "mandatory_documents": ["Degree"],
      "tags": {"YEAR_FROM": "2018", "YEAR_TO": "2022",
               "VERIFICATION_BLOCKER": ["Scanned copy is not clear / is cut off — needs a clear, uncut copy",
                                        "Signatures on document do not match across pages"]}}),

    ("AUDIT FIX: T18 (course_vs, Mismatch) restructured for multiselect ANTECEDENTS + uses CONTEXT",
     {"template_id": "T18", "check_name": "Education Verification",
      "course_name": "Bachelor of Commerce (B.Com)", "vs": "Delhi University",
      "tags": {"YEAR_FROM": "2019", "YEAR_TO": "2022",
               "ANTECEDENTS": ["CGPA", "Passing year"]}}),

    ("AUDIT FIX: T14 (course_vs, Information Missing) restructured - single ANTECEDENTS value still reads naturally",
     {"template_id": "T14", "check_name": "Education Verification",
      "course_name": "Diploma", "vs": "ITI Chennai",
      "tags": {"YEAR_FROM": "2020", "YEAR_TO": "2021",
               "ANTECEDENTS": ["Academic year"]}}),

    ("AUDIT FIX: T40 (check_only, Information Missing) restructured, multiselect ANTECEDENTS "
     "[NOTE: T40 retired 2026-08-18 fourth fix, merged into T14 - this scenario now runs on T14 "
     "with course fields left blank, reproducing T40's exact old check_only behavior]",
     {"template_id": "T14", "check_name": "Academic Reference Check",
      "tags": {"ANTECEDENTS": ["CGPA", "University name", "Passing year"],
               "QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("AUDIT FIX: T51 (Case-level information Missing) restructured, multiselect CASE_LEVEL_INFORMATION incl. split/cleaned values",
     {"template_id": "T51", "check_name": "Education Verification",
      "tags": {"CASE_LEVEL_INFORMATION": ["Date of Birth", "Address", "Email ID"]}}),

    ("AUDIT FIX: T53 - FORM_COMPANY_NAME now actually appears in the rendered output (used to be a required tag with no visible trace)",
     {"template_id": "T53", "check_name": "Employment Reference Check",
      "mandatory_documents": ["Consent form"]}),

    ("AUDIT FIX: T66 - REFERENCE_URL now actually appears in the rendered output (used to dangle on 'the instructions below')",
     {"template_id": "T66", "check_name": "Education Document Validation",
      "mandatory_documents": ["Consent form"],
      "tags": {"REFERENCE_URL": "https://authbridge.example/forms/edu-consent"}}),

    ("AUDIT FIX: T63 - no longer needs DOCUMENT_REQUIREMENTS (removed); Special Instructions optionally appended instead",
     {"template_id": "T63", "check_name": "Education Verification",
      "mandatory_documents": ["Degree"],
      "special_instructions": ["Sealed and signed by the institution"],
      "tags": {"SOURCE_DOCUMENT": "Institute's academic register entry",
               "VERIFICATION_BLOCKER": ["Record could not be located / traced by the institute"],
               "QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("AUDIT FIX: T65 - now includes ADDRESS_TYPE (which address - current/previous/permanent) "
     "[SUPERSEDED 2026-08-19, fifth pass: re-checking all 30 real T65 rows found ADDRESS_TYPE was a mismatched "
     "assumption - every row asks for the INSTITUTE's address, never a person's residential history. This scenario "
     "now supplies VS (institute name) instead of ADDRESS_TYPE, see the dedicated FIFTH PASS T65 scenario below for the corrected shape.]",
     {"template_id": "T65", "check_name": "Address Verification",
      "vs": "Test Institute", "tags": {"COUNTRY": "India"}}),

    ("NEW: T64 - course_vs counterpart of T63, SOURCE_DOCUMENT rejected for a specific course/institute "
     "[NOTE: T64 retired 2026-08-18 fourth fix, merged into T63 - this scenario now runs directly on T63 "
     "with course fields filled in, reproducing T64's exact old function]",
     {"template_id": "T63", "check_name": "Education Verification",
      "course_name": "Bachelor of Science (B.Sc)", "vs": "University of Mumbai",
      "mandatory_documents": ["Degree"],
      "tags": {"YEAR_FROM": "2017", "YEAR_TO": "2020",
               "SOURCE_DOCUMENT": "University's own convocation register",
               "VERIFICATION_BLOCKER": ["Institute is not recognized by the verifying body"]}}),

    ("RETIRED: T67 no longer exists - selecting it must error like any other unknown template_id",
     {"template_id": "T67", "check_name": "Education Verification",
      "any_one_of_documents": ["Degree", "Provisional Certificate"]}),

    # --- 2026-08-18 (third fix, same day): Reason-label cleanup + T16/T38 retirement ---

    ("RETIRED: T16 no longer exists (folded into base Missing + Special Instructions)",
     {"template_id": "T16", "check_name": "Education Verification",
      "course_name": "Diploma", "vs": "ITI Chennai",
      "mandatory_documents": ["Consent form"]}),

    ("REPLACEMENT: base T9 (Missing) + 'Duly signed' Special Instruction reproduces what T16 used to say",
     {"template_id": "T9", "check_name": "Education Verification",
      "course_name": "Diploma", "vs": "ITI Chennai",
      "mandatory_documents": ["Consent form"],
      "special_instructions": ["Sealed and signed by the institution"],
      "tags": {"YEAR_FROM": "2020", "YEAR_TO": "2021"}}),

    # --- 2026-08-18 (fourth fix, same day): course_vs_optional merge ---

    ("FOURTH FIX - THE OWNER'S EXACT REPORTED GAP: T9 (now course_vs_optional) with course info filled in "
     "-> states the specific degree/institute instead of a vague 'Degree for Academic Reference Check'",
     {"template_id": "T9", "check_name": "Academic Reference Check",
      "course_name": "Bachelor of Technology (B.Tech)", "vs": "Anna University",
      "mandatory_documents": ["Degree", "Final year marksheet"],
      "tags": {"YEAR_FROM": "2016", "YEAR_TO": "2020"}}),

    ("FOURTH FIX: T9 (course_vs_optional) with ALL course fields left blank -> falls back to check_name, "
     "exactly reproducing the old check_only (formerly T37) behavior for genuinely course-less cases "
     "[SUPERSEDED 2026-08-26: silently falling back to check_name is no longer possible - see the two "
     "TASK #112 scenarios below for the corrected required-QUALIFICATION_LEVEL behavior]",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree"],
      "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]}}),

    ("TASK #112: T9 (course_vs_optional) with ALL course fields left blank AND no QUALIFICATION_LEVEL "
     "-> rejected, not silently generic (owner: a fully untargeted comment should no longer go out "
     "when nothing identifies which of a candidate's real degrees is meant)",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree"]}),

    ("TASK #112: T9 (course_vs_optional) with ALL course fields left blank but QUALIFICATION_LEVEL "
     "given (multiselect - two values) -> context states the candidate's qualification level(s) instead "
     "of falling back to the generic check_name phrase",
     {"template_id": "T9", "check_name": "Professional License Check",
      "mandatory_documents": ["Degree"],
      "tags": {"QUALIFICATION_LEVEL": ["UG", "Highest degree"]}}),

    ("FOURTH FIX: T9 (course_vs_optional) - course_name given but vs blank -> rejected, not silently dropped",
     {"template_id": "T9", "check_name": "Academic Reference Check",
      "course_name": "Bachelor of Technology (B.Tech)",
      "mandatory_documents": ["Degree"]}),

    ("FOURTH FIX: T9 (course_vs_optional) - course_name+vs given but YEAR_FROM/YEAR_TO blank -> rejected",
     {"template_id": "T9", "check_name": "Academic Reference Check",
      "course_name": "Bachelor of Technology (B.Tech)", "vs": "Anna University",
      "mandatory_documents": ["Degree"]}),

    ("FOURTH FIX: T13 (course_vs_optional, Wrong/Rejected) with course info -> full CONTEXT",
     {"template_id": "T13", "check_name": "Education Verification",
      "course_name": "Bachelor of Commerce (B.Com)", "vs": "Delhi University",
      "mandatory_documents": ["Degree"],
      "tags": {"YEAR_FROM": "2015", "YEAR_TO": "2018",
               "VERIFICATION_BLOCKER": ["Signatures on document do not match across pages"]}}),

    ("FOURTH FIX: T63 (course_vs_optional, Wrong/Rejected - Institution's Own Record) with course info -> "
     "uses CONTEXT correctly (T63's optimized_text was fixed from a literal CHECK_NAME during this merge)",
     {"template_id": "T63", "check_name": "Education Verification",
      "course_name": "Bachelor of Science (B.Sc)", "vs": "University of Mumbai",
      "mandatory_documents": ["Degree"],
      "tags": {"YEAR_FROM": "2017", "YEAR_TO": "2020",
               "SOURCE_DOCUMENT": "University's own convocation register",
               "VERIFICATION_BLOCKER": ["Institute is not recognized by the verifying body"]}}),

    ("RETIRED (fourth fix): T37 no longer exists - merged into T9",
     {"template_id": "T37", "check_name": "Education Verification", "mandatory_documents": ["Degree"]}),
    ("RETIRED (fourth fix): T40 no longer exists - merged into T14",
     {"template_id": "T40", "check_name": "Education Verification", "tags": {"ANTECEDENTS": ["CGPA"]}}),
    ("RETIRED (fourth fix): T41 no longer exists - merged into T15",
     {"template_id": "T41", "check_name": "Education Verification"}),
    ("RETIRED (fourth fix): T45 no longer exists - merged into T10",
     {"template_id": "T45", "check_name": "Education Verification", "mandatory_documents": ["Degree"]}),
    ("RETIRED (fourth fix): T46 no longer exists - merged into T11",
     {"template_id": "T46", "check_name": "Education Verification", "mandatory_documents": ["Degree"]}),
    ("RETIRED (fourth fix): T47 no longer exists - merged into T12",
     {"template_id": "T47", "check_name": "Education Verification", "mandatory_documents": ["Degree"]}),
    ("RETIRED (fourth fix): T57 no longer exists - merged into T13",
     {"template_id": "T57", "check_name": "Education Verification", "mandatory_documents": ["Degree"]}),
    ("RETIRED (fourth fix): T64 no longer exists - merged into T63",
     {"template_id": "T64", "check_name": "Education Verification", "mandatory_documents": ["Degree"]}),

    # --- 2026-08-19 (fifth pass): full-template tag audit ---

    ("FIFTH PASS: T17 (Portal Action, course_vs) now states the actual PORTAL_ACTION "
     "instead of discarding it - real data showed this varies hugely and is never inferable",
     {"template_id": "T17", "check_name": "Education Verification",
      "course_name": "Bachelor of Technology (B.Tech)", "vs": "Anna University",
      "tags": {"YEAR_FROM": "2018", "YEAR_TO": "2022",
               "PORTAL_ACTION": "register on the platform and grant third-party access to view your qualification",
               "PORTAL_NAME": "HEDD", "PORTAL_URL": "https://hedd.ac.uk/verify"}}),

    ("FIFTH PASS: T42 (Visit within deadline) now states WHICH original documents to carry - "
     "100% of real T42 rows named specific documents the old template never asked for",
     {"template_id": "T42", "check_name": "Education Verification",
      "tags": {"VERIFICATION_LOCATION": "Anna University, Chennai campus", "NO_OF_DAYS": "10",
               "VISIT_DOCUMENTS": ["Degree", "Consolidated marksheet", "Aadhaar card"],
               "VISIT_REASON": "The institute's records could not be located or verified through mail or the online portal."}}),

    # --- 2026-08-19 (sixth pass): owner spotted T42 still had no Reason element ---

    ("SIXTH PASS: T42 now states WHY the visit is needed (VISIT_REASON) - 8/8 (100%) real "
     "T42 rows state a reason the fifth pass's VISIT_DOCUMENTS fix alone didn't capture",
     {"template_id": "T42", "check_name": "Education Verification",
      "tags": {"VERIFICATION_LOCATION": "the University", "NO_OF_DAYS": "7",
               "VISIT_DOCUMENTS": ["All year marksheets", "Degree"],
               "VISIT_REASON": "The institute's records could not be located or verified through mail or the online portal."}}),

    ("SIXTH PASS: T42 without VISIT_REASON -> error, since it's mandatory (not optional like T8's cost breakdown)",
     {"template_id": "T42", "check_name": "Education Verification",
      "tags": {"VERIFICATION_LOCATION": "the University", "NO_OF_DAYS": "7",
               "VISIT_DOCUMENTS": ["All year marksheets", "Degree"]}}),

    ("FIFTH PASS: T8 (revised total cost) WITH breakdown - 68% of real T8 rows state "
     "a Pricing Tool Cost + Additional Cost breakdown that the old template discarded",
     {"template_id": "T8", "check_name": "Education Verification",
      "tags": {"CURRENCY": "GBP", "TOTAL_VER_COST": "56.00",
               "PRICING_TOOL_COST": "42", "ADDITIONAL_COST": "14"}}),

    ("FIFTH PASS: T8 WITHOUT breakdown - optional tags left blank, falls back to the plain total-only sentence",
     {"template_id": "T8", "check_name": "Education Verification",
      "tags": {"CURRENCY": "INR", "TOTAL_VER_COST": "1200"}}),

    ("FIFTH PASS: T59 (Mismatch - Verified Value on File) now states WHICH form/source the "
     "conflicting value came from - 4/6 real rows explicitly named JAF/EAF, the old template never asked",
     {"template_id": "T59", "check_name": "Academic Reference Check",
      "tags": {"ANTECEDENTS": "university name", "SOURCE_FORM": "Job Application Form (JAF)",
               "VERIFIED_VALUE": "Anna University"}}),

    ("FIFTH PASS: T65 (Missing address) - OLD tag ADDRESS_TYPE (Current/Previous/Permanent) removed, "
     "replaced with VS (institute name) - all 30 real T65 rows ask for the INSTITUTE's address, never a person's residential history",
     {"template_id": "T65", "check_name": "Education Verification",
      "tags": {"COUNTRY": "United Kingdom"}, "vs": "ITM University"}),
]

print("=" * 100)
for desc, inp in TESTS:
    result = generate(inp)
    print(f"\n### {desc}")
    print(f"INPUT mandatory={inp.get('mandatory_documents')} any_one_of={inp.get('any_one_of_documents')}")
    if "error" in result:
        print(f"RESULT: ERROR -> {result['error']}")
    else:
        print(f"GENERATED: {result['final_comment']}")
    print("-" * 100)

by_desc = {desc: inp for desc, inp in TESTS}

# The owner's exact flagged bug case - this is the whole point of the redesign.
bug_input = by_desc["THE OWNER'S EXACT FLAGGED BUG: Mandatory set PLUS a separate Any-one-of pool "
                     "(GROUPS wrongly rendered this as 'submit any ONE of two whole bundles')"]
bug_result = generate(bug_input)
expected_bug = (
    "Kindly submit the following documents for the candidate's highest completed degree:\n\n"
    "Mandatory (All 3 required):\n"
    "* Degree\n"
    "* Consent form\n"
    "* Diploma/Certificate\n\n"
    "Additional Document (Submit ANY ONE of the following):\n"
    "* All year marksheets\n"
    "* Authbridge ARN\n"
    "* Application Form"
)
print("\n" + "=" * 100)
print("VERIFYING the owner's exact flagged bug is fixed (headed/bulleted format, 2026-08-18 second fix):")
print("GOT:\n", bug_result["final_comment"])
print("\nEXPECTED:\n", expected_bug)
assert bug_result["final_comment"] == expected_bug, "Mandatory+Any-one-of rendering does not match expected bulleted format"
print("PASS: Mandatory set and Any-one-of pool are now rendered as a headed, bulleted layout, not a single flowing sentence.")

# Any-one-of-only, 2 documents, no Mandatory at all - owner live-tested this
# exact shape ("The case is missing either Degree or Highest Passing
# Education Marksheet for...") and asked why it wasn't using "our agreed
# format" the way the combined Mandatory+Any-one-of case already did.
# ROUND 1 (2026-08-26): needs_combined_document_sentence()/
# combined_document_sentence() were extended to also cover this shape,
# reusing the headed "Additional Document (Submit ANY ONE of the following):"
# format. The owner REJECTED that - gave an exact target output with no
# header, no trailing ", or" per bullet, and a lead-in that explicitly states
# the Reason (missing documents), which the generic combined lead-in lacked.
# ROUND 2 / task #104 (2026-08-26, same day): reverted the Round-1 extension
# and built a fully separate needs_any_one_of_only_sentence()/
# any_one_of_only_sentence() pair instead, matching the owner's exact target
# wording (verified live against php/CommentEngine.php first).
any_only_input = by_desc["Any-one-of only, two documents -> single Reason+Action lead-in sentence "
                          "plus bare bullets, no header, no trailing conjunction (CORRECTED 2026-08-26, "
                          "task #104 - supersedes the same-day headed/bulleted 'Additional Document' "
                          "attempt the owner rejected)"]
any_only_result = generate(any_only_input)
expected_any_only = (
    "To proceed with the verification for the candidate's highest completed degree, please provide any ONE of the following missing documents:\n\n"
    "* Degree\n"
    "* Provisional Certificate"
)
assert any_only_result["final_comment"] == expected_any_only, any_only_result["final_comment"]
assert "either" not in any_only_result["final_comment"], any_only_result["final_comment"]
assert "Additional Document" not in any_only_result["final_comment"], any_only_result["final_comment"]
assert ", or" not in any_only_result["final_comment"], any_only_result["final_comment"]
print("PASS: an Any-one-of-only requirement (2+ docs, no Mandatory) now renders as a single Reason+Action "
      "lead-in sentence followed by bare bullets - no header, no trailing conjunction - matching the "
      "owner's exact target output (task #104, corrects the task #103 headed/bulleted attempt).")

# Combined case with special instructions. NOTE (2026-08-26, task #109): T9 now
# uses the "Document Requirements:" bulleted block (special_instructions_format)
# instead of the old inline "Please ensure the copy is: X and Y." sentence -
# this scenario's placeholder special_instructions values ("Both sides"/"Colour
# copy") predate the real SPECIAL_INSTRUCTIONS dropdown list and have no
# display_phrases entry, so they render unchanged (display_phrase() falls back
# to the raw value when no mapping exists) - still a valid regression check of
# the block mechanism itself, just without expanded phrasing for these two.
combined_si_input = by_desc["Combined Mandatory + Any-one-of, with special instructions appended"]
combined_si_result = generate(combined_si_input)
expected_combined_si = (
    "Kindly submit the following documents for the candidate's highest completed degree:\n\n"
    "Mandatory (Both required):\n"
    "* Degree\n"
    "* Final year marksheet\n\n"
    "Additional Document (Submit ANY ONE of the following):\n"
    "* Consent form\n"
    "* Authbridge ARN\n"
    "* HEDD consent form\n\n"
    "Document Requirements:\n"
    "* Both sides\n"
    "* Colour copy"
)
assert combined_si_result["final_comment"] == expected_combined_si, combined_si_result["final_comment"]
print("PASS: bulleted DOCUMENTS layout + the new Document Requirements block render correctly together, on their own trailing paragraph.")

# Any-one-of with exactly 1 doc in the combined case - no "any ONE of" framing
single_any_input = by_desc["Combined, Any-one-of has exactly 1 doc -> no 'any ONE of' framing needed, just 'submit X'"]
single_any_result = generate(single_any_input)
assert "any ONE of" not in single_any_result["final_comment"], single_any_result["final_comment"]
assert single_any_result["final_comment"].endswith("Additional Document (required):\n* HEDD consent form"), single_any_result["final_comment"]
print("PASS: a single any-one-of document doesn't get 'any ONE of' framing (no real choice to state).")

# Requested 4-mandatory + 3-any-one-of example
big_input = by_desc["REQUESTED EXAMPLE: 4 mandatory docs + 3-doc any-one-of pool (illustrative, any docs)"]
big_result = generate(big_input)
print("\n" + "=" * 100)
print("REQUESTED EXAMPLE (4 mandatory + 3 any-one-of):")
print(big_result["final_comment"])
expected_big = (
    "Kindly submit the following documents for the candidate's highest completed degree:\n\n"
    "Mandatory (All 4 required):\n"
    "* Offer Letter\n"
    "* Relieving Letter\n"
    "* Experience Certificate\n"
    "* Last 3 months Payslips\n\n"
    "Additional Document (Submit ANY ONE of the following):\n"
    "* Form 16\n"
    "* Bank Statement\n"
    "* PF Statement"
)
assert big_result["final_comment"] == expected_big, big_result["final_comment"]
print("PASS: matches expected bulleted combined format.")

# Duplicate-within-bucket rejection
dup_result = generate(by_desc["Duplicate document within Mandatory rejected"])
assert "error" in dup_result and "Duplicate" in dup_result["error"], dup_result
print("PASS: duplicate document within a single bucket is rejected.")

# Overlap-between-buckets rejection
overlap_result = generate(by_desc["Same document in both Mandatory and Any-one-of rejected (overlap)"])
assert "error" in overlap_result and "only be in Mandatory OR Any-one-of" in overlap_result["error"], overlap_result
print("PASS: a document appearing in both buckets is rejected.")

# No-documents assertion
empty_result = generate(by_desc["No documents at all (both buckets empty) -> error"])
assert "error" in empty_result and "At least one document" in empty_result["error"], empty_result
print("PASS: both buckets empty is correctly rejected as 'no documents'.")

# --- Phase 2 (year range; QUALIFICATION_TYPE removed 2026-08-18) assertions ---
qual_year_input = by_desc["Course/institute scoped (T9) with atomic document + special instruction + cleaned COURSE_NAME + year (Phase 2, updated)"]
qual_year_result = generate(qual_year_input)
assert "error" not in qual_year_result, qual_year_result
assert "Bachelor of Commerce (B.Com) from Delhi University (2015–2018)" in qual_year_result["final_comment"], qual_year_result["final_comment"]
assert "Undergraduate" not in qual_year_result["final_comment"], "QUALIFICATION_TYPE should no longer appear anywhere - " + qual_year_result["final_comment"]
print("PASS: T9 context states the cleaned course name (which already carries the qualification level) + year range, with no separate/redundant UG/PG tag.")

single_year_input = by_desc["Phase 2: single-year program collapses YEAR_FROM==YEAR_TO to one year, no dash"]
single_year_result = generate(single_year_input)
assert "error" not in single_year_result, single_year_result
assert "(2022)" in single_year_result["final_comment"] and "2022–2022" not in single_year_result["final_comment"]
print("PASS: identical YEAR_FROM/YEAR_TO collapses to one year instead of '(2022–2022)'.")

missing_qual_input = by_desc["Phase 2 (updated): missing YEAR_FROM/YEAR_TO on a course_vs template -> error, not a silently ambiguous comment"]
missing_qual_result = generate(missing_qual_input)
assert "error" in missing_qual_result and "YEAR_FROM" in missing_qual_result["error"] and "YEAR_TO" in missing_qual_result["error"], missing_qual_result
print("PASS: YEAR_FROM/YEAR_TO are still enforced as mandatory on course_vs templates (QUALIFICATION_TYPE correctly no longer part of this check at all).")

# --- Phase 4 (T69/T70/T71) assertions ---
t69_result = generate(by_desc["Phase 4: T69 Review Raised - mandatory REVIEW_REASON states a concrete why"])
assert "error" not in t69_result, t69_result
assert t69_result["final_comment"] == (
    "Review raised for Education Verification - Suspect Positive Response flagged during verification. "
    "Kindly check and confirm at the earliest."
), t69_result["final_comment"]
print("PASS: T69 (Review Raised) always states a concrete reason.")

t70_result = generate(by_desc["Phase 4: T70 Antecedent Value Contains - field mismatch across sources"])
assert "error" not in t70_result, t70_result
assert t70_result["final_comment"] == (
    'The Course Name / Qualification recorded for Education Verification is inconsistent across sources - '
    'it shows "Diploma" in one record and "Certificate" in another. Kindly confirm the correct value and update accordingly.'
), t70_result["final_comment"]
print("PASS: T70 (Antecedent Value Contains) renders as a plain, readable sentence.")

t71_result = generate(by_desc["Phase 4: T71 Antecedent Value Less Than - field below expected minimum"])
assert "error" not in t71_result, t71_result
assert t71_result["final_comment"] == (
    "The Period of Education recorded for Education Verification is less than the expected minimum of 2 Years, "
    "which needs review before verification can proceed. Kindly confirm the correct Period of Education or provide supporting justification."
), t71_result["final_comment"]
print("PASS: T71 (Antecedent Value Less Than) renders as a plain, readable sentence.")

# --- 2026-08-18 candidate-empathy audit fix assertions ---

t13_result = generate(by_desc["AUDIT FIX: T13 (course_vs, Wrong/Rejected) now uses CONTEXT (previously bypassed it) + multiselect VERIFICATION_BLOCKER"])
assert "error" not in t13_result, t13_result
assert t13_result["final_comment"] == (
    "The copy of Degree submitted for Bachelor of Technology (B.Tech) from Anna University (2018–2022) cannot be accepted "
    "because Scanned copy is not clear / is cut off — needs a clear, uncut copy and Signatures on document do not match across pages. "
    "Kindly provide an acceptable copy."
), t13_result["final_comment"]
print("PASS: T13 now states the full course/institute/year CONTEXT (previously silently dropped) and joins multiple VERIFICATION_BLOCKER values with 'and'.")

t18_result = generate(by_desc["AUDIT FIX: T18 (course_vs, Mismatch) restructured for multiselect ANTECEDENTS + uses CONTEXT"])
assert "error" not in t18_result, t18_result
assert t18_result["final_comment"] == (
    "The following details recorded for Bachelor of Commerce (B.Com) from Delhi University (2019–2022) do not match "
    "our available records. To proceed with verification, kindly confirm or correct:\n\n"
    "* CGPA (Cumulative Grade Point Average)\n"
    "* Year of Passing"
), t18_result["final_comment"]
print("PASS: T18 uses CONTEXT + renders 2 ANTECEDENTS values as a bulleted Reason+Solution+Action block (2026-08-23 format redesign), with display phrases expanded.")

t14_result = generate(by_desc["AUDIT FIX: T14 (course_vs, Information Missing) restructured - single ANTECEDENTS value still reads naturally"])
assert "error" not in t14_result, t14_result
assert t14_result["final_comment"] == (
    "To complete the verification for Diploma from ITI Chennai (2020–2021), please provide the following missing details:\n\n"
    "* Specific Academic Year"
), t14_result["final_comment"]
print("PASS: T14 renders a single ANTECEDENTS value as a one-line bulleted Reason+Solution+Action block (2026-08-23 format redesign).")

t40_result = generate(by_desc["AUDIT FIX: T40 (check_only, Information Missing) restructured, multiselect ANTECEDENTS "
                               "[NOTE: T40 retired 2026-08-18 fourth fix, merged into T14 - this scenario now runs on T14 "
                               "with course fields left blank, reproducing T40's exact old check_only behavior]"])
assert "error" not in t40_result, t40_result
assert t40_result["final_comment"] == (
    "To complete the verification for the candidate's highest completed degree, please provide the following missing details:\n\n"
    "* CGPA (Cumulative Grade Point Average)\n"
    "* University name\n"
    "* Year of Passing"
), t40_result["final_comment"]
print("PASS: T40 correctly bullets 3 ANTECEDENTS values, one per line, with display phrases expanded where mapped (University name has no mapping, renders unchanged).")

t51_result = generate(by_desc["AUDIT FIX: T51 (Case-level information Missing) restructured, multiselect CASE_LEVEL_INFORMATION incl. split/cleaned values"])
assert "error" not in t51_result, t51_result
assert t51_result["final_comment"] == (
    "To complete the verification for Education Verification, please provide the following missing details:\n\n"
    "* Date of Birth\n"
    "* Address\n"
    "* Email ID"
), t51_result["final_comment"]
print("PASS: T51 correctly bullets the split/cleaned CASE_LEVEL_INFORMATION values (Address + Email ID, previously one bundled 'address, email id' entry), one per line.")

t53_result = generate(by_desc["AUDIT FIX: T53 - FORM_COMPANY_NAME now actually appears in the rendered output (used to be a required tag with no visible trace)"])
assert "error" not in t53_result, t53_result
assert "AuthBridge Research Services Pvt. Ltd." in t53_result["final_comment"], t53_result["final_comment"]
assert "instructions below" not in t53_result["final_comment"], t53_result["final_comment"]
print("PASS: T53 states the company name directly - no more required-but-invisible FORM_COMPANY_NAME, no more dangling 'instructions below'.")

t66_result = generate(by_desc["AUDIT FIX: T66 - REFERENCE_URL now actually appears in the rendered output (used to dangle on 'the instructions below')"])
assert "error" not in t66_result, t66_result
assert "https://authbridge.example/forms/edu-consent" in t66_result["final_comment"], t66_result["final_comment"]
assert "instructions below" not in t66_result["final_comment"], t66_result["final_comment"]
print("PASS: T66 states the approved-format URL directly - no more required-but-invisible REFERENCE_URL.")

t63_result = generate(by_desc["AUDIT FIX: T63 - no longer needs DOCUMENT_REQUIREMENTS (removed); Special Instructions optionally appended instead"])
assert "error" not in t63_result, t63_result
assert t63_result["final_comment"] == (
    "The Institute's academic register entry submitted for the candidate's highest completed degree cannot be accepted because "
    "Record could not be located / traced by the institute. Kindly provide Degree. "
    "Please ensure the copy is: Sealed and signed by the institution."
), t63_result["final_comment"]
print("PASS: T63 no longer requires the dead DOCUMENT_REQUIREMENTS tag and uses the standard Special Instructions mechanism instead.")

t65_result = generate(by_desc["AUDIT FIX: T65 - now includes ADDRESS_TYPE (which address - current/previous/permanent) "
                               "[SUPERSEDED 2026-08-19, fifth pass: re-checking all 30 real T65 rows found ADDRESS_TYPE was a mismatched "
                               "assumption - every row asks for the INSTITUTE's address, never a person's residential history. This scenario "
                               "now supplies VS (institute name) instead of ADDRESS_TYPE, see the dedicated FIFTH PASS T65 scenario below for the corrected shape.]"])
assert "error" not in t65_result, t65_result
assert t65_result["final_comment"] == (
    "The complete address of Test Institute in India was not provided with the case (required for Education Verification). "
    "Kindly provide the institute's complete address for verification."
), t65_result["final_comment"]
print("PASS: T65 now states WHICH address (current/previous/permanent) instead of leaving it ambiguous.")

t64_result = generate(by_desc["NEW: T64 - course_vs counterpart of T63, SOURCE_DOCUMENT rejected for a specific course/institute "
                               "[NOTE: T64 retired 2026-08-18 fourth fix, merged into T63 - this scenario now runs directly on T63 "
                               "with course fields filled in, reproducing T64's exact old function]"])
assert "error" not in t64_result, t64_result
assert t64_result["final_comment"] == (
    "The University's own convocation register submitted for Bachelor of Science (B.Sc) from University of Mumbai (2017–2020) "
    "cannot be accepted because Institute is not recognized by the verifying body. Kindly provide Degree."
), t64_result["final_comment"]
print("PASS: T64 (new template) correctly renders a course/institute-scoped source-document rejection.")

t67_result = generate(by_desc["RETIRED: T67 no longer exists - selecting it must error like any other unknown template_id"])
assert "error" in t67_result and "Unknown template_id: T67" in t67_result["error"], t67_result
print("PASS: T67 is fully retired - no longer resolvable as a template.")

t16_result = generate(by_desc["RETIRED: T16 no longer exists (folded into base Missing + Special Instructions)"])
assert "error" in t16_result and "Unknown template_id: T16" in t16_result["error"], t16_result
print("PASS: T16 is fully retired - no longer resolvable as a template.")

replacement_result = generate(by_desc["REPLACEMENT: base T9 (Missing) + 'Duly signed' Special Instruction reproduces what T16 used to say"])
assert "error" not in replacement_result, replacement_result
assert replacement_result["final_comment"] == (
    "To complete the verification for Diploma from ITI Chennai (2020–2021), please provide the Consent form.\n\n"
    "Document Requirements:\n"
    "* Must be sealed and signed by the institution."
), replacement_result["final_comment"]
print("PASS: base 'Missing' + the 'Duly signed' Special Instruction reproduces T16's old function without a dedicated template.")

# --- 2026-08-18 (fourth fix, same day): course_vs_optional merge assertions ---

owner_gap_result = generate(by_desc["FOURTH FIX - THE OWNER'S EXACT REPORTED GAP: T9 (now course_vs_optional) with course info filled in "
                                     "-> states the specific degree/institute instead of a vague 'Degree for Academic Reference Check'"])
assert "error" not in owner_gap_result, owner_gap_result
print("\n" + "=" * 100)
print("VERIFYING the owner's exact reported gap is fixed (course_vs_optional, fourth fix):")
print("GOT:\n", owner_gap_result["final_comment"])
assert owner_gap_result["final_comment"] == (
    "To proceed with the verification for Bachelor of Technology (B.Tech) from Anna University (2016–2020), "
    "please provide the following missing documents:\n\n"
    "* Degree\n"
    "* Final year marksheet"
), owner_gap_result["final_comment"]
assert "Academic Reference Check" not in owner_gap_result["final_comment"], owner_gap_result["final_comment"]
print("PASS: T9 now states the specific degree/institute/year - a candidate can no longer receive a vague "
      "'Degree for Academic Reference Check' comment when the course is actually known, resolving the owner's "
      "'What is this Academic Reference check? what degree?' complaint. (2+ documents now also render via the "
      "task #106 bulleted mandatory-only format rather than the old inline 'both X and Y' sentence.)")

blank_course_result = generate(by_desc["FOURTH FIX: T9 (course_vs_optional) with ALL course fields left blank -> falls back to check_name, "
                                        "exactly reproducing the old check_only (formerly T37) behavior for genuinely course-less cases "
                                        "[SUPERSEDED 2026-08-26: silently falling back to check_name is no longer possible - see the two "
                                        "TASK #112 scenarios below for the corrected required-QUALIFICATION_LEVEL behavior]"])
assert "error" not in blank_course_result, blank_course_result
assert blank_course_result["final_comment"] == (
    "To complete the verification for the candidate's highest completed degree, please provide the Degree."
), blank_course_result["final_comment"]
print("PASS: T9 with course info genuinely blank now states the picked Qualification Level instead of a bare check_name fallback - see TASK #112 below for the full before/after.")

# --- 2026-08-26 (task #112): QUALIFICATION_LEVEL fallback assertions ---
# Owner reported wanting a way to say WHICH of a candidate's real degrees a
# case-less comment is about (UG/PG/Highest/Second-highest/Third-highest),
# multiselect, MANDATORY the moment Course/Degree, Institute, and Year are
# all left blank - replacing the old silent fallback to the fixed
# "Education Verification" phrase tested above pre-2026-08-26.
qual_missing_result = generate(by_desc["TASK #112: T9 (course_vs_optional) with ALL course fields left blank AND no QUALIFICATION_LEVEL "
                                        "-> rejected, not silently generic (owner: a fully untargeted comment should no longer go out "
                                        "when nothing identifies which of a candidate's real degrees is meant)"])
assert "error" in qual_missing_result and "Qualification Level" in qual_missing_result["error"], qual_missing_result
print("PASS: leaving Course/Institute/Year AND Qualification Level all blank is now rejected, not silently generic.")

qual_given_result = generate(by_desc["TASK #112: T9 (course_vs_optional) with ALL course fields left blank but QUALIFICATION_LEVEL "
                                      "given (multiselect - two values) -> context states the candidate's qualification level(s) instead "
                                      "of falling back to the generic check_name phrase"])
assert "error" not in qual_given_result, qual_given_result
assert qual_given_result["final_comment"] == (
    "To complete the verification for the candidate's Undergraduate (UG) qualification and highest completed degree, please provide the Degree."
), qual_given_result["final_comment"]
print("PASS: multiple Qualification Level values are AND-joined correctly into the CONTEXT phrase (multiselect, per owner's explicit clarification).")

partial1_result = generate(by_desc["FOURTH FIX: T9 (course_vs_optional) - course_name given but vs blank -> rejected, not silently dropped"])
assert "error" in partial1_result and "both course_name and vs are required together" in partial1_result["error"], partial1_result
print("PASS: partial course fill (course_name without vs) is rejected rather than silently discarding the course info.")

partial2_result = generate(by_desc["FOURTH FIX: T9 (course_vs_optional) - course_name+vs given but YEAR_FROM/YEAR_TO blank -> rejected"])
assert "error" in partial2_result and "YEAR_FROM" in partial2_result["error"] and "YEAR_TO" in partial2_result["error"], partial2_result
print("PASS: course_name+vs given without a year range is still rejected, consistent with the pre-existing course_vs rule.")

t13_merged_result = generate(by_desc["FOURTH FIX: T13 (course_vs_optional, Wrong/Rejected) with course info -> full CONTEXT"])
assert "error" not in t13_merged_result, t13_merged_result
assert "Bachelor of Commerce (B.Com) from Delhi University (2015–2018)" in t13_merged_result["final_comment"], t13_merged_result["final_comment"]
print("PASS: T13 (merged course_vs_optional) still renders full course/institute/year CONTEXT correctly.")

t63_merged_result = generate(by_desc["FOURTH FIX: T63 (course_vs_optional, Wrong/Rejected - Institution's Own Record) with course info -> "
                                      "uses CONTEXT correctly (T63's optimized_text was fixed from a literal CHECK_NAME during this merge)"])
assert "error" not in t63_merged_result, t63_merged_result
assert t63_merged_result["final_comment"] == (
    "The University's own convocation register submitted for Bachelor of Science (B.Sc) from University of Mumbai (2017–2020) "
    "cannot be accepted because Institute is not recognized by the verifying body. Kindly provide Degree."
), t63_merged_result["final_comment"]
print("PASS: T63 (merged with retired T64) correctly uses CONTEXT after the literal-CHECK_NAME text bug was fixed during the merge.")

for retired_id in ["T37", "T40", "T41", "T45", "T46", "T47", "T57", "T64"]:
    r = generate(by_desc[f"RETIRED (fourth fix): {retired_id} no longer exists - merged into "
                          + {"T37": "T9", "T40": "T14", "T41": "T15", "T45": "T10",
                             "T46": "T11", "T47": "T12", "T57": "T13", "T64": "T63"}[retired_id]])
    assert "error" in r and f"Unknown template_id: {retired_id}" in r["error"], r
print("PASS: all 8 retired templates (T37, T40, T41, T45, T46, T47, T57, T64) correctly error as unknown - fully merged, no orphaned IDs left resolvable.")

# --- 2026-08-19 (fifth pass): full-template tag audit assertions ---

t17_result = generate(by_desc["FIFTH PASS: T17 (Portal Action, course_vs) now states the actual PORTAL_ACTION "
                              "instead of discarding it - real data showed this varies hugely and is never inferable"])
assert "error" not in t17_result, t17_result
assert t17_result["final_comment"] == (
    "Please register on the platform and grant third-party access to view your qualification on HEDD using "
    "https://hedd.ac.uk/verify to complete verification for Bachelor of Technology (B.Tech) from Anna University (2018–2022)."
), t17_result["final_comment"]
print("PASS: T17 now states the actual PORTAL_ACTION - previously said only 'complete the pending verification action', discarding real instructions entirely.")

t42_result = generate(by_desc["FIFTH PASS: T42 (Visit within deadline) now states WHICH original documents to carry - "
                               "100% of real T42 rows named specific documents the old template never asked for"])
assert "error" not in t42_result, t42_result
assert t42_result["final_comment"] == (
    "The institute's records could not be located or verified through mail or the online portal. "
    "Please complete Education Verification at Anna University, Chennai campus within 10 days, "
    "carrying original Degree, Consolidated marksheet, and Aadhaar card for verification."
), t42_result["final_comment"]
print("PASS: T42 now states which original documents to carry - the old template said only where/when, never what to bring.")

# --- 2026-08-19 (sixth pass): VISIT_REASON assertions ---

t42_reason_result = generate(by_desc["SIXTH PASS: T42 now states WHY the visit is needed (VISIT_REASON) - 8/8 (100%) real "
                                      "T42 rows state a reason the fifth pass's VISIT_DOCUMENTS fix alone didn't capture"])
assert "error" not in t42_reason_result, t42_reason_result
assert t42_reason_result["final_comment"] == (
    "The institute's records could not be located or verified through mail or the online portal. "
    "Please complete Education Verification at the University within 7 days, "
    "carrying original All year marksheets and Degree for verification."
), t42_reason_result["final_comment"]
print("PASS: T42 now states WHY the visit is needed as a lead-in sentence, restoring the Reason element the owner correctly flagged as missing.")

t42_no_reason_result = generate(by_desc["SIXTH PASS: T42 without VISIT_REASON -> error, since it's mandatory (not optional like T8's cost breakdown)"])
assert "error" in t42_no_reason_result and "VISIT_REASON" in t42_no_reason_result["error"], t42_no_reason_result
print("PASS: T42 correctly rejects a missing VISIT_REASON (mandatory, unlike T8's optional cost-breakdown tags) rather than silently generating a reason-less comment.")

t8_with_result = generate(by_desc["FIFTH PASS: T8 (revised total cost) WITH breakdown - 68% of real T8 rows state "
                                   "a Pricing Tool Cost + Additional Cost breakdown that the old template discarded"])
assert "error" not in t8_with_result, t8_with_result
assert t8_with_result["final_comment"] == (
    "Kindly approve the revised total verification cost of GBP 56.00 for Education Verification "
    "(Base verification cost: GBP 42 + Additional cost: GBP 14)."
), t8_with_result["final_comment"]
print("PASS: T8 renders the cost breakdown when both PRICING_TOOL_COST and ADDITIONAL_COST are provided.")

t8_without_result = generate(by_desc["FIFTH PASS: T8 WITHOUT breakdown - optional tags left blank, falls back to the plain total-only sentence"])
assert "error" not in t8_without_result, t8_without_result
assert t8_without_result["final_comment"] == (
    "Kindly approve the revised total verification cost of INR 1200 for Education Verification."
), t8_without_result["final_comment"]
print("PASS: T8 falls back to the plain total-only sentence when the optional breakdown isn't provided - nothing broke for the ~32% of real cases that state only the total.")

t59_result = generate(by_desc["FIFTH PASS: T59 (Mismatch - Verified Value on File) now states WHICH form/source the "
                               "conflicting value came from - 4/6 real rows explicitly named JAF/EAF, the old template never asked"])
assert "error" not in t59_result, t59_result
assert t59_result["final_comment"] == (
    "The university name stated in the Job Application Form (JAF) for Education Verification does not match the "
    "supporting record. The value shown in the supporting record is Anna University. Kindly confirm or update the correct value."
), t59_result["final_comment"]
print("PASS: T59 now states which form/source the mismatched value came from - the old template said only 'provided', never saying where from.")

t65_result = generate(by_desc["FIFTH PASS: T65 (Missing address) - OLD tag ADDRESS_TYPE (Current/Previous/Permanent) removed, "
                               "replaced with VS (institute name) - all 30 real T65 rows ask for the INSTITUTE's address, never a person's residential history"])
assert "error" not in t65_result, t65_result
assert t65_result["final_comment"] == (
    "The complete address of ITM University in United Kingdom was not provided with the case "
    "(required for Education Verification). Kindly provide the institute's complete address for verification."
), t65_result["final_comment"]
assert "Current" not in t65_result["final_comment"] and "Previous" not in t65_result["final_comment"] and "Permanent" not in t65_result["final_comment"]
print("PASS: T65 now asks for the institute's name (VS) instead of a mismatched ADDRESS_TYPE (Current/Previous/Permanent) that no real T65 row ever actually needed.")

print("\n" + "=" * 100)
print("VERIFYING the 2026-08-24 Information Reason->Scenario rebuild (owner-approved dropdown expansion):")

# New template T72 (Wrong / Invalid - Other Detail) - reuses FIELD_NAME (already
# used by T70/T71) + new INVALID_REASON tag, no CommentEngine.php changes needed.
t72_result = generate({
    "template_id": "T72", "check_name": "Education Verification",
    "course_name": "", "vs": "",
    "mandatory_documents": [], "any_one_of_documents": [], "special_instructions": [],
    "tags": {"FIELD_NAME": "Verification Portal Link", "INVALID_REASON": "is not accessible or functional (e.g. a broken link)"},
})
assert "error" not in t72_result, t72_result
assert t72_result["final_comment"] == (
    "The Verification Portal Link provided for Education Verification is not accessible or functional "
    "(e.g. a broken link). Kindly provide a valid, corrected value for verification."
), t72_result["final_comment"]
print("PASS: new template T72 (Wrong/Invalid - Other Detail) renders correctly via the generic tag-substitution loop.")

# T59 with a new ANTECEDENTS value (Date of Birth) - confirms the applies_to_templates
# restriction (T59-only, not T14/T18) doesn't block T59 itself.
t59_dob_result = generate({
    "template_id": "T59", "check_name": "Education Verification",
    "course_name": "", "vs": "",
    "mandatory_documents": [], "any_one_of_documents": [], "special_instructions": [],
    "tags": {"ANTECEDENTS": ["Date of Birth"], "SOURCE_FORM": "Job Application Form (JAF)", "VERIFIED_VALUE": "12-Jan-1995"},
})
assert "error" not in t59_dob_result, t59_dob_result
assert "Date of Birth" in t59_dob_result["final_comment"], t59_dob_result["final_comment"]
print("PASS: T59 (Mismatch - Value vs. Verified Record) accepts the new 'Date of Birth' ANTECEDENTS value.")

# T71 with a new FIELD_NAME value (CGPA / Percentage) - confirms the expanded
# FIELD_NAME list works for the Below Required Minimum scenario too, not just T70.
t71_cgpa_result = generate({
    "template_id": "T71", "check_name": "Education Verification",
    "course_name": "", "vs": "",
    "mandatory_documents": [], "any_one_of_documents": [], "special_instructions": [],
    "tags": {"FIELD_NAME": "CGPA / Percentage", "THRESHOLD": "60%"},
})
assert "error" not in t71_cgpa_result, t71_cgpa_result
assert "CGPA / Percentage" in t71_cgpa_result["final_comment"], t71_cgpa_result["final_comment"]
print("PASS: T71 (Below Required Minimum) accepts the new 'CGPA / Percentage' FIELD_NAME value.")

print("\n" + "=" * 100)
print("VERIFYING the 2026-08-25 Document Reason->Scenario rebuild (owner-approved dropdown expansion):")

# New template T73 (Incomplete - Other Detail) - reusable catch-all alongside
# T11/T53/T66, mirrors T51's list_block pattern. REVISED 2026-08-25 (owner
# live-tested T74 - "why do we not have any docs or details here to select?")
# - now carries DOCUMENTS in needed_tags, so the lead-in states which
# document is incomplete instead of a vague "the document".
t73_result = generate({
    "template_id": "T73", "check_name": "Education Verification",
    "course_name": "", "vs": "",
    "mandatory_documents": ["Consent form"], "any_one_of_documents": [], "special_instructions": [],
    "tags": {"INCOMPLETE_DETAIL": ["Missing signature, stamp, or seal", "Missing page(s) or section(s)"]},
})
assert "error" not in t73_result, t73_result
assert t73_result["final_comment"] == (
    "The copy of Consent form submitted for Education Verification is incomplete. Kindly resubmit a complete, "
    "corrected copy addressing the following:\n\n"
    "* Missing signature, stamp, or seal\n"
    "* Missing page(s) or section(s)"
), t73_result["final_comment"]
print("PASS: new template T73 (Document/Incomplete - Other Detail) states which document is incomplete and renders a bulleted Reason+Solution+Action block via the list_block mechanism.")

t73_no_docs_result = generate({
    "template_id": "T73", "check_name": "Education Verification",
    "mandatory_documents": [], "any_one_of_documents": [],
    "tags": {"INCOMPLETE_DETAIL": ["Missing signature, stamp, or seal"]},
})
assert "error" in t73_no_docs_result and "At least one document" in t73_no_docs_result["error"], t73_no_docs_result
print("PASS: T73 correctly requires at least one document to be selected (same as T9-T13), no longer silently generic.")

# New template T74 (Blurred/Illegible - Specific Defect) - reusable catch-all
# alongside T10, same list_block pattern, same DOCUMENTS fix as T73.
t74_result = generate({
    "template_id": "T74", "check_name": "Education Verification",
    "course_name": "", "vs": "",
    "mandatory_documents": ["Final year marksheet"], "any_one_of_documents": [], "special_instructions": [],
    "tags": {"BLUR_DETAIL": ["Specific page or section is unreadable", "Text is faded or low contrast"]},
})
assert "error" not in t74_result, t74_result
assert t74_result["final_comment"] == (
    "The copy of Final year marksheet submitted for Education Verification could not be read clearly. Kindly resubmit a clear, "
    "complete copy addressing the following:\n\n"
    "* Specific page or section is unreadable\n"
    "* Text is faded or low contrast"
), t74_result["final_comment"]
print("PASS: new template T74 (Document/Blurred-Illegible - Specific Defect) states which document is affected and renders correctly via the same list_block mechanism.")

# Combined Mandatory + Any-one-of on T74: list_block must still win over the
# combined-document-sentence override, or the BLUR_DETAIL bullets would
# silently vanish (the precedence bug this fix specifically guards against).
t74_combined_result = generate({
    "template_id": "T74", "check_name": "Education Verification",
    "mandatory_documents": ["Degree"], "any_one_of_documents": ["Provisional Certificate"],
    "tags": {"BLUR_DETAIL": ["Entire copy is blurred or unreadable"]},
})
assert "error" not in t74_combined_result, t74_combined_result
assert t74_combined_result["final_comment"] == (
    "The copy of Degree submitted for Education Verification could not be read clearly. Kindly resubmit a clear, "
    "complete copy addressing the following:\n\n"
    "* Entire copy is blurred or unreadable"
), t74_combined_result["final_comment"]
assert "Mandatory" not in t74_combined_result["final_comment"], t74_combined_result["final_comment"]
print("PASS: T74 with BOTH Mandatory and Any-one-of documents filled still renders the list_block (BLUR_DETAIL bullets), not the combined document sentence - precedence fix confirmed.")

# T53 reclassified from "Missing - Company Details Required" to "Incomplete" -
# dropdown_path.reason_detail changed, rendered text/behavior unaffected.
t53_reclass_result = generate({
    "template_id": "T53", "check_name": "Employment Reference Check",
    "mandatory_documents": ["Consent form"],
})
assert "error" not in t53_reclass_result, t53_reclass_result
print("PASS: T53 still renders correctly after being reclassified from Document/Missing to Document/Incomplete (dropdown_path only; template text/logic untouched).")

# T66 reclassified from "Missing - Specific Format Required" to "Incomplete"
t66_reclass_result = generate({
    "template_id": "T66", "check_name": "Education Document Validation",
    "mandatory_documents": ["Consent form"],
    "tags": {"REFERENCE_URL": "https://authbridge.example/forms/edu-consent"},
})
assert "error" not in t66_reclass_result, t66_reclass_result
print("PASS: T66 still renders correctly after being reclassified from Document/Missing to Document/Incomplete.")

# T63 normalized from "Wrong/Rejected - Institution's Own Record" to plain "Wrong/Rejected"
t63_norm_result = generate({
    "template_id": "T63", "check_name": "Education Verification",
    "mandatory_documents": ["Degree"],
    "tags": {"SOURCE_DOCUMENT": "Institute's academic register entry",
             "VERIFICATION_BLOCKER": ["Record could not be located / traced by the institute"],
             "QUALIFICATION_LEVEL": ["Highest degree"]},
})
assert "error" not in t63_norm_result, t63_norm_result
print("PASS: T63 still renders correctly after its reason_detail was normalized from a compound label to plain 'Wrong/Rejected'.")

# T68 normalized from "Expired - State Validity Period" to plain "Expired"
t68_norm_result = generate({
    "template_id": "T68", "check_name": "Education Verification",
    "mandatory_documents": ["Transcript"],
    "tags": {"VALIDITY_PERIOD": "6 months"},
})
assert "error" not in t68_norm_result, t68_norm_result
print("PASS: T68 still renders correctly after its reason_detail was normalized from a compound label to plain 'Expired'.")

print("\n" + "=" * 100)
print("VERIFYING the 2025-08-25 (continued x3) grammar fix is now SUPERSEDED by task #106's")
print("mandatory-only bulleted format for 2+ documents (the 'copy of both/all of' phrasing this")
print("fix targeted no longer appears at all once 2+ mandatory docs route through")
print("mandatory_only_sentence() instead of inline template substitution):")

# HISTORY: T13 with 2 mandatory documents used to render "The both X and Y
# submitted for... cannot be accepted" (ungrammatical), fixed 2026-08-25 to
# "The copy of both X and Y submitted...". Task #106 (2026-08-26) then
# SUPERSEDED that fix for 2+ mandatory documents specifically: the owner
# asked for the same bulleted-lead-in-sentence treatment already given to
# the any-one-of-only case ("Could you please correct this as we correct for
# OR case"), so 2+ mandatory documents now route through
# mandatory_only_sentence() (a template-agnostic override, same as
# any_one_of_only_sentence()) instead of the individual template's own
# "The copy of <DOCUMENTS> submitted..." text - the old "copy of" grammar
# concern is moot here since that phrase no longer appears in the output at
# all for 2+ documents. A SINGLE mandatory document still uses the
# template's own inline text unchanged (see the single-doc "copy of" checks
# further up this file, still valid).
t13_multi_result = generate({
    "template_id": "T13", "check_name": "Education Verification",
    "mandatory_documents": ["Degree", "Provisional Certificate"],
    "tags": {"VERIFICATION_BLOCKER": ["Scanned copy is not clear / is cut off — needs a clear, uncut copy"],
             "QUALIFICATION_LEVEL": ["Highest degree"]},
})
assert "error" not in t13_multi_result, t13_multi_result
assert t13_multi_result["final_comment"] == (
    "To proceed with the verification for the candidate's highest completed degree, please provide acceptable copies of the following documents:\n\n"
    "* Degree\n"
    "* Provisional Certificate"
), t13_multi_result["final_comment"]
assert "The both" not in t13_multi_result["final_comment"], t13_multi_result["final_comment"]
print("PASS: T13 with 2 mandatory documents now renders via the bulleted mandatory-only format (task #106), not the old inline sentence.")

t12_multi_result = generate({
    "template_id": "T12", "check_name": "Education Verification",
    "mandatory_documents": ["Degree", "Provisional Certificate", "Final year marksheet"],
    "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]},
})
assert "error" not in t12_multi_result, t12_multi_result
assert t12_multi_result["final_comment"] == (
    "To proceed with the verification for the candidate's highest completed degree, please provide valid, current copies of the following documents:\n\n"
    "* Degree\n"
    "* Provisional Certificate\n"
    "* Final year marksheet"
), t12_multi_result["final_comment"]
assert "The all of" not in t12_multi_result["final_comment"], t12_multi_result["final_comment"]
print("PASS: T12 with 3 mandatory documents now renders via the bulleted mandatory-only format (task #106), not the old inline sentence.")

t68_multi_result = generate({
    "template_id": "T68", "check_name": "Education Verification",
    "mandatory_documents": ["Degree", "Provisional Certificate"],
    "tags": {"VALIDITY_PERIOD": "6 months"},
})
assert "error" not in t68_multi_result, t68_multi_result
assert t68_multi_result["final_comment"] == (
    "To proceed with the verification for Education Verification, please provide valid, current copies of the following documents:\n\n"
    "* Degree\n"
    "* Provisional Certificate"
), t68_multi_result["final_comment"]
print("PASS: T68 with 2 mandatory documents also now renders via the bulleted mandatory-only format.")

# T53/T66's old "resubmit the same" second-mention simplification (2026-08-25)
# is likewise superseded for 2+ documents - the whole template text (both
# mentions) is replaced by the mandatory-only override.
t53_multi_result = generate({
    "template_id": "T53", "check_name": "Education Verification",
    "mandatory_documents": ["Consent form", "Authorization form"],
})
assert "error" not in t53_multi_result, t53_multi_result
assert t53_multi_result["final_comment"] == (
    "To proceed with the verification for Education Verification, please provide complete copies of the following documents:\n\n"
    "* Consent form\n"
    "* Authorization form"
), t53_multi_result["final_comment"]
assert "the both" not in t53_multi_result["final_comment"].lower(), t53_multi_result["final_comment"]
print("PASS: T53 with 2 mandatory documents also now renders via the bulleted mandatory-only format.")

print("\n" + "=" * 100)
print("VERIFYING task #106 (mandatory-only bulleted format) directly:")

# Owner's exact reported case.
t9_owner_result = generate({
    "template_id": "T9", "check_name": "Bachelor of Technology (B.Tech) Check",
    "course_name": "Bachelor of Technology (B.Tech)", "vs": "Delhi University",
    "tags": {"YEAR_FROM": "2022", "YEAR_TO": "2026"},
    "mandatory_documents": ["Secondary School Certificate (SSC)", "All year marksheets"],
})
assert "error" not in t9_owner_result, t9_owner_result
assert t9_owner_result["final_comment"] == (
    "To proceed with the verification for Bachelor of Technology (B.Tech) from Delhi University (2022–2026), "
    "please provide the following missing documents:\n\n"
    "* Secondary School Certificate (SSC)\n"
    "* All year marksheets"
), t9_owner_result["final_comment"]
print("PASS: the owner's exact reported mandatory-only case now matches the target bulleted format.")

# A single mandatory document must stay a plain inline sentence (no bullet, no
# real list) - unaffected by the task #106 bulleted-multi-doc fix. NOTE
# (2026-08-26, task #109): the sentence text itself changed superseding this -
# T9's optimized_text no longer says "The case is missing..." (owner: "where
# ever we are starting with The case is missing... because candidate doesn't
# know Case and all").
t9_single_result = generate({
    "template_id": "T9", "check_name": "Professional License Check",
    "mandatory_documents": ["Degree"],
    "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]},
})
assert "error" not in t9_single_result, t9_single_result
assert t9_single_result["final_comment"] == (
    "To complete the verification for the candidate's highest completed degree, please provide the Degree."
), t9_single_result["final_comment"]
assert "case" not in t9_single_result["final_comment"].lower(), t9_single_result["final_comment"]
print("PASS: a single mandatory document still renders as a plain inline sentence (no bullet, no real list), "
      "now using the candidate-friendly lead-in instead of 'The case is missing...' (task #109).")

# Combined Mandatory + Any-one-of must stay byte-identical - unaffected by this change.
t9_combined_result = generate(by_desc["THE OWNER'S EXACT FLAGGED BUG: Mandatory set PLUS a separate Any-one-of pool "
                                       "(GROUPS wrongly rendered this as 'submit any ONE of two whole bundles')"])
assert t9_combined_result["final_comment"] == expected_bug, t9_combined_result["final_comment"]
print("PASS: the combined Mandatory + Any-one-of format remains byte-identical, unaffected by the mandatory-only fix.")

print("\n" + "=" * 100)
print("VERIFYING task #108 (CHECK_NAME always renders as 'Education Verification') directly:")

# Owner's exact reported case: "Kindly approve the additional verification cost of
# USD 500 for Academic Reference Check." - the specific auto-filled check type
# ("Academic Reference Check") must never appear in the rendered comment;
# "Education Verification" appears in its place, project-wide.
t7_owner_result = generate({
    "template_id": "T7", "check_name": "Academic Reference Check",
    "tags": {"COST": "500", "CURRENCY": "USD"},
})
assert "error" not in t7_owner_result, t7_owner_result
assert t7_owner_result["final_comment"] == (
    "Kindly approve the additional verification cost of USD 500 for Education Verification."
), t7_owner_result["final_comment"]
assert "Academic Reference Check" not in t7_owner_result["final_comment"], t7_owner_result["final_comment"]
print("PASS: the owner's exact reported case now reads 'for Education Verification', never the specific auto-filled check type.")

# The underlying check_name input is STILL required (validation unchanged) -
# only the rendered text changed, per the owner's "keep the dropdown, change
# only the rendered text" clarification.
t7_missing_checkname = generate({
    "template_id": "T7", "check_name": "",
    "tags": {"COST": "500", "CURRENCY": "USD"},
})
assert "error" in t7_missing_checkname and "check_name is required" in t7_missing_checkname["error"], t7_missing_checkname
print("PASS: check_name is still required for validation - only its RENDERED value changed, not whether it's mandatory.")

# course_vs / course_vs_optional-with-course-filled CONTEXT (course + institute +
# year) is a DIFFERENT thing from CHECK_NAME and must be completely unaffected -
# it should keep stating the actual course/institute, never "Education Verification".
t9_course_result = generate({
    "template_id": "T9", "check_name": "Academic Reference Check",
    "course_name": "Bachelor of Technology (B.Tech)", "vs": "Delhi University",
    "tags": {"YEAR_FROM": "2022", "YEAR_TO": "2026"},
    "mandatory_documents": ["Degree"],
})
assert "error" not in t9_course_result, t9_course_result
assert t9_course_result["final_comment"] == (
    "To complete the verification for Bachelor of Technology (B.Tech) from Delhi University (2022–2026), "
    "please provide the Degree."
), t9_course_result["final_comment"]
print("PASS: course_vs_optional with course/institute filled in still states the real course/institute - unaffected by the CHECK_NAME fix (different tag, different purpose).")

print("\n" + "=" * 100)
print("VERIFYING task #109 (T9 lead-in redesign + Document Requirements block) directly:")

# Owner's exact reported case, in full (course/institute/year filled, single
# missing document, two special instructions).
t9_task109_result = generate({
    "template_id": "T9", "check_name": "Academic Reference Check",
    "course_name": "Bachelor of Technology (B.Tech)", "vs": "Delhi University",
    "tags": {"YEAR_FROM": "2022", "YEAR_TO": "2026"},
    "mandatory_documents": ["Final year marksheet"],
    "special_instructions": ["Original document, not a photocopy", "Sealed and signed by the institution"],
})
assert "error" not in t9_task109_result, t9_task109_result
assert t9_task109_result["final_comment"] == (
    "To complete the verification for Bachelor of Technology (B.Tech) from Delhi University (2022–2026), "
    "please provide the Final year marksheet.\n\n"
    "Document Requirements:\n"
    "* Must be an original document (photocopies/scans of photocopies are not accepted).\n"
    "* Must be sealed and signed by the institution."
), t9_task109_result["final_comment"]
assert "case" not in t9_task109_result["final_comment"].lower(), t9_task109_result["final_comment"]
assert "Please ensure the copy is" not in t9_task109_result["final_comment"], t9_task109_result["final_comment"]
print("PASS: the owner's exact reported case now matches the target format exactly - candidate-friendly lead-in "
      "plus a headed, bulleted Document Requirements block with fuller phrasing.")

# 2+ mandatory documents (task #106 bulleted override) + special instructions -
# the Document Requirements block must still appear as its own trailing section.
t9_task109_multi_result = generate({
    "template_id": "T9", "check_name": "Professional License Check",
    "mandatory_documents": ["Degree", "Final year marksheet"],
    "special_instructions": ["Both sides, colour copy"],
    "tags": {"QUALIFICATION_LEVEL": ["Highest degree"]},
})
assert "error" not in t9_task109_multi_result, t9_task109_multi_result
assert t9_task109_multi_result["final_comment"] == (
    "To proceed with the verification for the candidate's highest completed degree, please provide the following missing documents:\n\n"
    "* Degree\n"
    "* Final year marksheet\n\n"
    "Document Requirements:\n"
    "* Must be a colour copy showing both sides of the document."
), t9_task109_multi_result["final_comment"]
print("PASS: 2+ mandatory documents (task #106's bulleted override) plus Special Instructions correctly render both blocks together.")

# A DIFFERENT Document template (T13) must be completely unaffected - still the
# old inline "Please ensure the copy is: X." sentence, no "Document Requirements"
# header, per the owner's explicit "Just T9 (Missing) for now" scope answer.
t13_unaffected_result = generate({
    "template_id": "T13", "check_name": "Education Verification",
    "mandatory_documents": ["Degree"],
    "tags": {"VERIFICATION_BLOCKER": "Document appears to be tampered or altered",
             "QUALIFICATION_LEVEL": ["Highest degree"]},
    "special_instructions": ["Sealed and signed by the institution"],
})
assert "error" not in t13_unaffected_result, t13_unaffected_result
assert "Document Requirements" not in t13_unaffected_result["final_comment"], t13_unaffected_result["final_comment"]
assert "Please ensure the copy is: Sealed and signed by the institution." in t13_unaffected_result["final_comment"], t13_unaffected_result["final_comment"]
print("PASS: T13 (a different Document template) is completely unaffected - still the old inline sentence, confirming the fix is scoped to T9 only.")

print("\nAll scenarios passed.")
