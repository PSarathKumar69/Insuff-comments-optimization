<?php
/**
 * CommentEngine — stitches a final Reason+Solution+Action insufficiency
 * comment from a dropdown selection path, using templates.json/tag_values.json
 * as the data source. Pure PHP, no framework/DB dependency, so Bridge's team
 * can drop this into their own stack unmodified or port the logic 1:1.
 *
 * Grammar rules implemented here (per project decisions):
 *  - DOCUMENTS is built from two buckets - REDESIGNED 2026-08-18 (replacing
 *    the 2026-08-17 GROUPS model entirely, per owner instruction after a live
 *    test exposed a real modeling bug): a **Mandatory** set (every document
 *    in it is always required together, AND) plus an **Any-one-of** pool
 *    (the candidate must submit at least one document from it, OR). This is
 *    NOT the same as "pick one whole alternative bundle" - the owner's own
 *    test case proved that distinction matters: given Mandatory = {Degree,
 *    Consent form, Diploma/Certificate} and Any-one-of = {All year
 *    marksheets, Authbridge ARN, Application Form}, the correct requirement
 *    is "submit all 3 mandatory docs, PLUS any one of the other 3" - NOT
 *    "submit either this group of 3, or that group of 3" (which the old
 *    GROUPS model produced and the owner flagged as "completely wrong").
 *    See combinedDocumentSentence() below for the exact rendering.
 *
 *    A document can only live in ONE of the two buckets, never both -
 *    generate() rejects any overlap. Either bucket may be empty. A single
 *    document in either bucket alone stays a plain noun phrase substituted
 *    inline - there's no real choice/list to bullet with just one option.
 *    THREE DIFFERENT multi-document override formats exist for the
 *    remaining shapes, each its own dedicated method (Mandatory-only added
 *    2026-08-26, same day as Any-one-of-only, after the owner asked for the
 *    identical treatment on both - see each method's own docblock for the
 *    full history): BOTH buckets non-empty uses combinedDocumentSentence()
 *    (a "Mandatory (All N required):" section + an "Additional Document
 *    (Submit ANY ONE of the following):" section, each with its own
 *    bullets); Any-one-of-only with 2+ documents uses anyOneOfOnlySentence()
 *    (ONE lead-in sentence stating both the Reason and the choice, followed
 *    directly by bare bullets, no header line, no trailing "or" per
 *    bullet); Mandatory-only with 2+ documents uses mandatoryOnlySentence()
 *    (the same shape as anyOneOfOnlySentence(), just AND phrasing instead
 *    of OR - "both X and Y" / "all of X, Y, and Z" no longer reads as plain
 *    inline prose once 2+ documents are involved, per the owner's explicit
 *    correction, so it's now bulleted just like the OR case).
 *  - Article handling ("a"/"an") is avoided entirely by design — templates
 *    are phrased to not require it ("Kindly provide <DOCUMENTS>" not
 *    "Kindly provide a <DOCUMENTS>"), since DOCUMENTS values are themselves
 *    full noun phrases (e.g. "Highest Passing Education Marksheet or Degree").
 *  - CONTEXT resolution: "course_vs" templates render "{COURSE_NAME} from
 *    {VS} ({YEAR_FROM}–{YEAR_TO})" (year range added Phase 2, 2026-08-18, to
 *    resolve the "where's the year?" ambiguity manager feedback flagged -
 *    mandatory, same as any other needed tag; an identical YEAR_FROM/YEAR_TO
 *    collapses to one year instead of showing e.g. "(2019–2019)"). A
 *    separate QUALIFICATION_TYPE tag ("Undergraduate (UG)" etc.) was added
 *    alongside this in Phase 2 but REMOVED 2026-08-18 per owner feedback
 *    ("remove this 'Undergraduate (UG)' - this is unnecessary") - COURSE_NAME
 *    itself was converted from free text to a cleaned picklist of real
 *    course names (e.g. "Bachelor of Technology (B.Tech)") that already
 *    state the qualification level, making the separate UG/PG/Diploma/PhD
 *    tag redundant rather than clarifying; "check_only" templates render
 *    just the auto-filled CHECK_NAME.
 *  - No raw <TAG> or {TAG} is ever allowed to reach the final output — if a
 *    required tag has no value, generate() throws so the caller can prompt
 *    the user rather than silently leaking a placeholder.
 */

class CommentEngine
{
    private array $templates;
    private array $tagValues;

    public function __construct(string $dataDir)
    {
        $this->templates = json_decode(file_get_contents($dataDir . '/templates.json'), true);
        $this->tagValues = json_decode(file_get_contents($dataDir . '/tag_values.json'), true);
    }

    private function findTemplate(string $id): ?array
    {
        foreach ($this->templates as $t) {
            if ($t['id'] === $id) return $t;
        }
        return null;
    }

    /**
     * Joins a list with a trailing conjunction, Oxford-comma style to match
     * the reference prototype exactly: "A and B" for 2 items, "A, B, and C"
     * (comma before the conjunction) for 3+.
     */
    private function joinList(array $items, string $mode = 'AND'): string
    {
        $items = array_values(array_filter($items, fn($x) => trim((string)$x) !== ''));
        if (count($items) === 0) return '';
        if (count($items) === 1) return $items[0];
        $last = array_pop($items);
        $conjunction = str_starts_with($mode, 'OR') ? 'or' : 'and';
        if (count($items) === 1) {
            return $items[0] . " $conjunction " . $last;
        }
        return implode(', ', $items) . ", $conjunction " . $last;
    }

    /**
     * Renders the Mandatory bucket - always an AND-list, never has an
     * "either/or" in it by definition (every document in this bucket is
     * required together, unconditionally). Keeps the same "both"/"all of"
     * emphasis this project has used since before the GROUPS experiment -
     * that phrasing was never the source of the ambiguity bug, so there's no
     * reason to change it now that GROUPS is gone.
     *   1 doc  -> the document name, unchanged
     *   2 docs -> "both X and Y"
     *   3+ docs -> "all of X, Y, and Z"
     */
    private function mandatoryPhrase(array $docs): string
    {
        if (count($docs) === 0) return '';
        if (count($docs) === 1) return $docs[0];
        if (count($docs) === 2) return 'both ' . $this->joinList($docs, 'AND');
        return 'all of ' . $this->joinList($docs, 'AND');
    }

    /**
     * Renders the Any-one-of bucket for use INLINE, substituted directly into
     * a template's <DOCUMENTS> placeholder. Only reaches the "2+ docs" case
     * below (a real either/or choice) as a fallback value for $documentsRendered
     * when combinedDocumentSentence() or anyOneOfOnlySentence() has ALREADY
     * taken over the visible output (see needsCombinedDocumentSentence()/
     * needsAnyOneOfOnlySentence()) - for the plain-substitution path, this is
     * now called only when there's a single Any-one-of document and Mandatory
     * is empty (no real choice to state). Matches the original T67 "Kindly
     * provide any one of the following documents..." phrasing style.
     *   1 doc  -> the document name, unchanged (no real choice to state)
     *   2+ docs -> "either X, Y, or Z"
     */
    private function anyOneOfInline(array $docs): string
    {
        if (count($docs) === 0) return '';
        if (count($docs) === 1) return $docs[0];
        return 'either ' . $this->joinList($docs, 'OR');
    }

    /**
     * Renders the Any-one-of bucket for use inside the COMBINED sentence
     * (see combinedDocumentSentence() below), where it follows "submit ...".
     *   1 doc  -> the document name, unchanged
     *   2+ docs -> "any ONE of: X, Y, or Z"
     */
    private function anyOneOfClause(array $docs): string
    {
        if (count($docs) === 0) return '';
        if (count($docs) === 1) return $docs[0];
        return 'any ONE of: ' . $this->joinList($docs, 'OR');
    }

    /**
     * Whether DOCUMENTS needs the full combined-sentence override (see
     * combinedDocumentSentence()) instead of a single substituted noun
     * phrase - true only when BOTH buckets have at least one document. See
     * needsAnyOneOfOnlySentence() below for the separate Any-one-of-only
     * case (own dedicated format, not this one).
     */
    private function needsCombinedDocumentSentence(array $mandatory, array $anyOneOf): bool
    {
        return count($mandatory) > 0 && count($anyOneOf) > 0;
    }

    /**
     * Whether DOCUMENTS needs the dedicated Any-one-of-ONLY sentence (see
     * anyOneOfOnlySentence()) - true when Mandatory is empty and Any-one-of
     * has 2+ documents (a real either/or choice). A single Any-one-of
     * document is excluded - no real choice to bullet, so it stays a plain
     * noun phrase via anyOneOfInline(), same as a single Mandatory document.
     *
     * Added 2026-08-26 (owner live-tested a pure Any-one-of case - "The case
     * is missing either Degree or Highest Passing Education Marksheet
     * for..." - and asked why it wasn't using "our agreed format"). First
     * attempt routed this through combinedDocumentSentence() with the
     * Mandatory section simply omitted, reusing its "Additional Document
     * (Submit ANY ONE of the following):" header - owner then gave an exact
     * target output showing that's NOT what they wanted for this shape:
     * no separate header line at all, no trailing ", or" per bullet, AND a
     * lead-in that explicitly states the Reason ("...missing documents:")
     * unlike combinedDocumentSentence()'s generic "Kindly submit the
     * following documents for X:" default (owner: "in your comment there is
     * No Missing docs reason, but it is there in mine"). Given a
     * deliberately different lead-in/no-header/no-trailing-or shape,
     * this is now a fully separate method rather than a generalization of
     * combinedDocumentSentence() - the original both-buckets-populated case
     * is completely untouched by this change.
     */
    private function needsAnyOneOfOnlySentence(array $mandatory, array $anyOneOf): bool
    {
        return count($mandatory) === 0 && count($anyOneOf) >= 2;
    }

    /**
     * Whether DOCUMENTS needs the dedicated Mandatory-ONLY sentence (see
     * mandatoryOnlySentence()) - true when Any-one-of is empty and Mandatory
     * has 2+ documents (a genuine multi-document AND-list). A single
     * Mandatory document is excluded - nothing to bullet with just one item,
     * so it stays a plain noun phrase via mandatoryPhrase(), unchanged.
     *
     * Added 2026-08-26 (owner live-tested a pure Mandatory case - "The case
     * is missing both Secondary School Certificate (SSC) and All year
     * marksheets for..." - and flagged it as "not in the expected format",
     * explicitly asking for the same correction already applied to the
     * Any-one-of-only case). Mirrors needsAnyOneOfOnlySentence()/
     * anyOneOfOnlySentence() exactly, just for the AND case instead of OR:
     * ONE lead-in sentence stating both the Reason and the Action, followed
     * directly by bare bullets, no header line, no trailing conjunction.
     * The combined Mandatory+Any-one-of case (needsCombinedDocumentSentence())
     * and the Any-one-of-only case are both checked first in generate() and
     * remain completely untouched by this addition.
     */
    private function needsMandatoryOnlySentence(array $mandatory, array $anyOneOf): bool
    {
        return count($anyOneOf) === 0 && count($mandatory) >= 2;
    }

    /**
     * Header line for the Mandatory bucket in the bulleted combined format
     * (see combinedDocumentSentence()) - varies by count so it never reads
     * "All 1 required".
     */
    private function mandatoryHeader(array $docs): string
    {
        $n = count($docs);
        if ($n <= 1) return 'Mandatory:';
        if ($n === 2) return 'Mandatory (Both required):';
        return "Mandatory (All $n required):";
    }

    /**
     * Header line for the Any-one-of bucket in the bulleted combined format.
     */
    private function anyOneOfHeader(array $docs): string
    {
        return count($docs) <= 1 ? 'Additional Document (required):' : 'Additional Document (Submit ANY ONE of the following):';
    }

    /** Renders a bucket as "* doc" bullet lines, one per line. */
    private function bulletList(array $docs): string
    {
        return implode("\n", array_map(fn($d) => "* $d", $docs));
    }

    /**
     * Looks up a friendlier reader-facing phrase for a dropdown value, used
     * only when rendering that value inside a bulleted list block (see
     * listBlock() below) - the dropdown option label itself stays short
     * (tag_values.json's `values` array), but a bullet in a generated
     * comment can afford to spell it out (e.g. ANTECEDENTS' "Bonafide/NOC"
     * -> "Bonafide Certificate / No Objection Certificate (NOC)"). Added
     * 2026-08-23 per the owner's own hand-written example format. Opt-in via
     * tag_values.json's `display_phrases` map - a value with no entry there
     * renders as-is, unchanged.
     */
    private function displayPhrase(string $tag, string $value): string
    {
        return $this->tagValues[$tag]['display_phrases'][$value] ?? $value;
    }

    /**
     * Builds the "Reason + bulleted Solution + Action" block used by
     * Information/Missing and Information/Mismatch templates whose subject
     * is a multiselect tag (ANTECEDENTS, CASE_LEVEL_INFORMATION) - added
     * 2026-08-23 after the owner flagged the old flowing-sentence format
     * ("The following information ... was not provided with the case: X
     * and Y. Kindly share...") as not matching the format they wanted, and
     * on a follow-up, that their own hand-written example was itself
     * missing the Reason element. `$leadIn` (from templates.json's
     * `list_block.lead_in`, with {CONTEXT} already substituted) carries
     * both the Reason ("...detail not provided...") and the Action ("...
     * please provide...") in one sentence; each bullet is the Solution -
     * exactly which piece of information, spelled out via displayPhrase().
     * Mirrors combinedDocumentSentence()'s bullet mechanics but for a single
     * flat AND-list rather than two Mandatory/Any-one-of buckets.
     */
    private function listBlock(string $leadIn, array $items, string $tag): string
    {
        $bullets = array_map(fn($v) => '* ' . $this->displayPhrase($tag, $v), $items);
        return $leadIn . "\n\n" . implode("\n", $bullets);
    }

    /**
     * Builds a headed "Document Requirements:" bulleted block for
     * SPECIAL_INSTRUCTIONS, replacing the old inline " Please ensure the
     * copy is: X and Y." sentence - opt-in via a template's
     * `special_instructions_format: "document_requirements"` field (see
     * generate() below). Each bullet is the fuller, candidate-facing
     * phrasing from SPECIAL_INSTRUCTIONS' `display_phrases` map (added
     * 2026-08-26, same mechanism as ANTECEDENTS' - see displayPhrase()) -
     * the dropdown option itself stays short for the agent, the bullet
     * spells it out for the candidate reading the comment.
     *
     * Added 2026-08-26: owner pasted a generated T9 comment and flagged both
     * that its opening ("The case is missing...") uses internal jargon a
     * candidate wouldn't recognize, and that its Special Instructions were
     * buried in a single run-on sentence ("Please ensure the copy is: X and
     * Y.") rather than clearly itemized. Gave an exact target output with a
     * "Document Requirements:" header and one bullet per instruction.
     * Confirmed via clarifying questions this is scoped to T9 only for now,
     * not every Document-category template (owner: "Just T9 (Missing) for
     * now") - every other template still uses the old inline sentence via
     * `$specialInstrText` below, completely unchanged.
     */
    private function specialInstructionsBlock(array $items): string
    {
        $bullets = array_map(fn($v) => '* ' . $this->displayPhrase('SPECIAL_INSTRUCTIONS', $v), $items);
        return "Document Requirements:\n" . implode("\n", $bullets);
    }

    /**
     * Builds the complete, self-contained BLOCK for the "both buckets used"
     * DOCUMENTS case - REPLACES the normal template substitution entirely
     * for this case (see generate()).
     *
     * REDESIGNED 2026-08-18 (second fix, same day): the owner had already
     * approved a headed, bulleted layout earlier this session ("Mandatory
     * (All 3 required): * doc * doc * doc" / "Additional Document (Submit
     * ANY ONE of the following): * doc * doc") over a flowing single
     * sentence - but that approval was never actually wired into this
     * method, which kept producing the old flowing-sentence format
     * ("Kindly submit the following mandatory documents for X: all of A, B,
     * and C. Along with these, submit any ONE of: D or E.") until the owner
     * caught it while testing a real multi-document case. Fixed here: a
     * lead-in line (still varying by reason - missing/blurred/incomplete/
     * expired/wrong-rejected - so the "why" is still stated) followed by a
     * blank line, a "Mandatory" section with one "* document" bullet per
     * line, a blank line, and an "Additional Document" section with one
     * "* document" bullet per line. `public/index.html`'s preview box
     * already has `white-space: pre-wrap` set, so these newlines render
     * correctly without any further UI change.
     *
     * Briefly generalized 2026-08-26 to also handle an empty Mandatory
     * bucket, then reverted the same day once the owner clarified the
     * Any-one-of-only case needed a genuinely different format (no header,
     * no trailing "or", a lead-in that states the Reason) rather than a
     * variant of this one - see anyOneOfOnlySentence() below, which now
     * owns that case exclusively. This method is unchanged from the
     * original 2026-08-18 redesign: always assumes BOTH buckets are
     * non-empty (guarded by needsCombinedDocumentSentence()).
     */
    private function combinedDocumentSentence(array $mandatory, array $anyOneOf, string $context, string $reasonSubType): string
    {
        $leadIn = match (true) {
            str_contains($reasonSubType, 'Blurred') => "Please submit clear, readable copies of the following documents for $context:",
            str_contains($reasonSubType, 'Incomplete') => "Please submit complete copies of the following documents for $context:",
            str_contains($reasonSubType, 'Expired') => "Please submit valid, current copies of the following documents for $context:",
            str_contains($reasonSubType, 'Wrong') || str_contains($reasonSubType, 'Rejected') => "Please submit acceptable copies of the following documents for $context:",
            default => "Kindly submit the following documents for $context:",
        };

        return $leadIn . "\n\n"
            . $this->mandatoryHeader($mandatory) . "\n"
            . $this->bulletList($mandatory) . "\n\n"
            . $this->anyOneOfHeader($anyOneOf) . "\n"
            . $this->bulletList($anyOneOf);
    }

    /**
     * Builds the complete, self-contained BLOCK for the Any-one-of-ONLY
     * DOCUMENTS case (Mandatory empty, 2+ Any-one-of documents) - REPLACES
     * the normal template substitution entirely for this case, same as
     * combinedDocumentSentence() does for the both-buckets case, but with a
     * deliberately different shape per the owner's exact target output
     * (2026-08-26): ONE lead-in sentence that already states both the
     * Reason (varies by reason_sub_type, e.g. "missing" documents) and the
     * Action ("please provide any ONE of the following") - no separate
     * "Additional Document (Submit ANY ONE of the following):" header line
     * (that header exists specifically to introduce a SECOND bucket
     * alongside a Mandatory one; with no Mandatory bucket here, the choice
     * framing belongs in the lead-in itself instead) - followed directly by
     * plain "* document" bullets with no trailing ", or" (the lead-in
     * already establishes it's a choice, so repeating "or" on every bullet
     * would be redundant).
     */
    private function anyOneOfOnlySentence(array $anyOneOf, string $context, string $reasonSubType): string
    {
        $leadIn = match (true) {
            str_contains($reasonSubType, 'Blurred') => "To proceed with the verification for $context, please provide a clear, readable copy of any ONE of the following documents:",
            str_contains($reasonSubType, 'Incomplete') => "To proceed with the verification for $context, please provide a complete copy of any ONE of the following documents:",
            str_contains($reasonSubType, 'Expired') => "To proceed with the verification for $context, please provide a valid, current copy of any ONE of the following documents:",
            str_contains($reasonSubType, 'Wrong') || str_contains($reasonSubType, 'Rejected') => "To proceed with the verification for $context, please provide an acceptable copy of any ONE of the following documents:",
            default => "To proceed with the verification for $context, please provide any ONE of the following missing documents:",
        };

        return $leadIn . "\n\n" . $this->bulletList($anyOneOf);
    }

    /**
     * Builds the complete, self-contained BLOCK for the Mandatory-ONLY
     * DOCUMENTS case (Any-one-of empty, 2+ Mandatory documents) - REPLACES
     * the normal template substitution entirely for this case, mirroring
     * anyOneOfOnlySentence() exactly but for the AND case: ONE lead-in
     * sentence stating both the Reason (varies by reason_sub_type) and the
     * Action ("please provide the following ... documents"), followed
     * directly by plain "* document" bullets - no header line, no trailing
     * conjunction (an AND-list bulleted with a trailing "and" on the
     * second-to-last line would be redundant with the lead-in already
     * establishing every item is required).
     */
    private function mandatoryOnlySentence(array $mandatory, string $context, string $reasonSubType): string
    {
        $leadIn = match (true) {
            str_contains($reasonSubType, 'Blurred') => "To proceed with the verification for $context, please provide clear, readable copies of the following documents:",
            str_contains($reasonSubType, 'Incomplete') => "To proceed with the verification for $context, please provide complete copies of the following documents:",
            str_contains($reasonSubType, 'Expired') => "To proceed with the verification for $context, please provide valid, current copies of the following documents:",
            str_contains($reasonSubType, 'Wrong') || str_contains($reasonSubType, 'Rejected') => "To proceed with the verification for $context, please provide acceptable copies of the following documents:",
            default => "To proceed with the verification for $context, please provide the following missing documents:",
        };

        return $leadIn . "\n\n" . $this->bulletList($mandatory);
    }

    /**
     * $input keys expected:
     *   template_id      (string, required)
     *   check_name       (string, required - auto-filled header value)
     *   course_name      (string, required if context_mode = course_vs)
     *   vs               (string, required if context_mode = course_vs or vs_only)
     *   mandatory_documents  (array of strings, when DOCUMENTS is a needed tag - every document
     *                         here is always required together, AND. May be empty if the
     *                         requirement is purely "any one of" - see any_one_of_documents.)
     *   any_one_of_documents (array of strings, when DOCUMENTS is a needed tag - the candidate
     *                         must submit at least one document from this pool, OR. May be
     *                         empty if the requirement is purely mandatory. A document may
     *                         appear in only ONE of these two arrays, never both.)
     *   special_instructions (array of strings, optional)
     *   tags             (assoc array: other tag => value OR array-of-values (for
     *                     dropdown_multi tags - ANTECEDENTS, CASE_LEVEL_INFORMATION,
     *                     VERIFICATION_BLOCKER as of 2026-08-18 - joined with "and" via
     *                     joinList() automatically, see the generic tag-resolution loop
     *                     below), e.g. VERIFICATION_BLOCKER, ANTECEDENTS, IDENTIFIER_TYPE,
     *                     CASE_LEVEL_INFORMATION, COUNTRY, CURRENCY, COST, etc.
     *                     For course_vs templates this is also where YEAR_FROM and YEAR_TO
     *                     arrive (Phase 2, 2026-08-18) - both mandatory, folded into CONTEXT,
     *                     see the "Resolve CONTEXT" block below.)
     */
    public function generate(array $input): array
    {
        $tid = $input['template_id'] ?? '';
        $tpl = $this->findTemplate($tid);
        if (!$tpl) {
            return ['error' => "Unknown template_id: $tid"];
        }

        $checkName = trim($input['check_name'] ?? '');
        if ($checkName === '') {
            return ['error' => 'check_name is required (auto-filled from Bridge navigation header).'];
        }

        // RENDERED check name - added 2026-08-26 per owner instruction: "wherever
        // we mention Academic Reference Check, it should be like For Education
        // Verification like that, Not check name." $checkName above (whatever
        // specific check type - "Academic Reference Check", "Professional
        // License Check", etc. - Bridge's navigation header auto-fills) is STILL
        // required and validated as before (the underlying selection still
        // matters for tracking/routing), but wherever the comment text would
        // print that value, it now always prints this fixed generic label
        // instead - project-wide, per the owner's explicit "everywhere" scope
        // confirmation. This is the only place $checkName's literal value feeds
        // into rendered output (via $context's initial assignment below, and via
        // $values['CHECK_NAME'] further down) - course_vs/vs_only CONTEXT
        // (course/institute/year) is unrelated and untouched.
        $renderedCheckName = 'Education Verification';

        // Resolve CONTEXT
        //
        // Phase 2 addition (2026-08-18): manager feedback flagged degree
        // comments as ambiguous - "where is year option to select?" A
        // YEAR_FROM-YEAR_TO range (never a single year - owner explicitly
        // corrected an earlier single-year design: "Not single year, we have
        // to give them range FROM to TO") is folded into CONTEXT here so
        // every course_vs comment states it explicitly. Mandatory, validated
        // the same generic way as any other tag, via needed_tags further
        // down - see that check for why a missing value here doesn't need
        // its own special-cased error message.
        //
        // QUALIFICATION_TYPE (a separate "Undergraduate (UG)"/"Postgraduate
        // (PG)"/etc. tag also added in Phase 2) was REMOVED 2026-08-18 per
        // owner feedback ("remove this 'Undergraduate (UG)' - this is
        // unnecessary") - COURSE_NAME is now itself a cleaned picklist of
        // real course names (e.g. "Bachelor of Technology (B.Tech)") that
        // already state the qualification level, so the separate tag was
        // redundant rather than clarifying.
        $context = $renderedCheckName;
        if ($tpl['context_mode'] === 'course_vs') {
            $course = trim($input['course_name'] ?? '');
            $vs = trim($input['vs'] ?? '');
            if ($course === '' || $vs === '') {
                return ['error' => 'course_name and vs are both required for this template.'];
            }
            $yearFrom = trim($input['tags']['YEAR_FROM'] ?? '');
            $yearTo = trim($input['tags']['YEAR_TO'] ?? '');
            $context = "$course from $vs";
            if ($yearFrom !== '' && $yearTo !== '') {
                // Fixed 2026-08-19 (live-test bug, caught via real PHP execution -
                // not just static brace/paren checks): PHP's double-quoted string
                // interpolation greedily consumes bytes matching [a-zA-Z0-9_\x80-\xff]
                // after a $variable name - and the en dash "–" is a multi-byte UTF-8
                // character whose bytes all fall in that \x80-\xff range, so
                // "$yearFrom–$yearTo" silently swallowed the dash into an undefined
                // variable named "$yearFrom<dash-bytes>", losing $yearFrom's value
                // entirely (rendered "(2026)" instead of "(2022–2026)") and throwing
                // an "Undefined variable" warning that corrupted generate.php's JSON
                // response with leaked HTML. Fixed by explicitly delimiting the
                // variable name with {} so the tokenizer can't run past it.
                $yearPart = ($yearFrom === $yearTo) ? $yearFrom : "{$yearFrom}–{$yearTo}";
                $context .= " ($yearPart)";
            }
        } elseif ($tpl['context_mode'] === 'vs_only') {
            $vs = trim($input['vs'] ?? '');
            if ($vs === '') {
                return ['error' => 'vs is required for this template.'];
            }
            $context = $vs;
        } elseif ($tpl['context_mode'] === 'course_vs_optional') {
            // Added 2026-08-18 (fourth fix, same day): REPLACES the old hard
            // course_vs / check_only Scope choice for 8 template pairs
            // (T9/T37, T10/T45, T11/T46, T12/T47, T13/T57, T14/T40, T15/T41,
            // T63/T64), after the owner's live test proved that binary
            // choice was a genuine ambiguity trap, not just a wording nit:
            // "Require B.Tech-Computer Science Engineering (B.Tech)Degree,
            // Final year marksheet." - a real historical comment that
            // clearly names a course - was found already misclassified as
            // check_only (T37) in the mined dataset, and a systematic check
            // showed 60% of all real T37 rows (1,245 of 2,067) and 47% of
            // T57 rows likewise named a course/degree that the Scope choice
            // had no way to capture once "General to this check" was picked.
            //
            // Fix: COURSE_NAME/VS/YEAR_FROM/YEAR_TO are now ALWAYS available
            // to fill in (never hidden behind a prior Scope decision) but
            // OPTIONAL - they only become required TOGETHER the moment the
            // agent starts filling any one of them in, so a course is never
            // silently droppable once known, but a genuinely course-less
            // case still works exactly like the old check_only path.
            $course = trim($input['course_name'] ?? '');
            $vs = trim($input['vs'] ?? '');
            if ($course !== '' || $vs !== '') {
                if ($course === '' || $vs === '') {
                    return ['error' => 'If specifying a course/degree, both course_name and vs are required together (or leave both blank if this is not tied to a specific course).'];
                }
                $yearFrom = trim($input['tags']['YEAR_FROM'] ?? '');
                $yearTo = trim($input['tags']['YEAR_TO'] ?? '');
                if ($yearFrom === '' || $yearTo === '') {
                    return ['error' => 'YEAR_FROM and YEAR_TO are required whenever a course/institute is specified.'];
                }
                // Fixed 2026-08-19 (live-test bug, caught via real PHP execution -
                // not just static brace/paren checks): PHP's double-quoted string
                // interpolation greedily consumes bytes matching [a-zA-Z0-9_\x80-\xff]
                // after a $variable name - and the en dash "–" is a multi-byte UTF-8
                // character whose bytes all fall in that \x80-\xff range, so
                // "$yearFrom–$yearTo" silently swallowed the dash into an undefined
                // variable named "$yearFrom<dash-bytes>", losing $yearFrom's value
                // entirely (rendered "(2026)" instead of "(2022–2026)") and throwing
                // an "Undefined variable" warning that corrupted generate.php's JSON
                // response with leaked HTML. Fixed by explicitly delimiting the
                // variable name with {} so the tokenizer can't run past it.
                $yearPart = ($yearFrom === $yearTo) ? $yearFrom : "{$yearFrom}–{$yearTo}";
                $context = "$course from $vs ($yearPart)";
            } else {
                // Added 2026-08-26: when Course/Degree, Institute, and Year are
                // ALL left blank, $context used to fall back silently to
                // $renderedCheckName ("Education Verification") - a fully generic
                // phrase that gives the agent no way to say WHICH of a candidate's
                // multiple real degrees a case-less comment is actually about.
                // Owner: pick from UG/PG/Highest/Second-highest/Third-highest degree
                // (QUALIFICATION_LEVEL, multiselect) instead - MANDATORY in this
                // blank-course branch specifically (owner's explicit choice), so a
                // fully untargeted comment can no longer go out silently.
                $qualLevels = $clean_local = (function ($arr) {
                    if (!is_array($arr)) return [];
                    return array_values(array_filter(array_map('trim', $arr), fn($x) => $x !== ''));
                })($input['tags']['QUALIFICATION_LEVEL'] ?? []);
                if (count($qualLevels) === 0) {
                    return ['error' => 'Select at least one Qualification Level (UG/PG/Highest degree/etc.) when Course/Degree, Institute, and Year are all left blank.'];
                }
                $qualPhrases = array_map(fn($v) => $this->displayPhrase('QUALIFICATION_LEVEL', $v), $qualLevels);
                $context = "the candidate's " . $this->joinList($qualPhrases, 'AND');
            }
            // else (unreachable now that the blank branch above always sets
            // $context from QUALIFICATION_LEVEL or errors out): $context would
            // otherwise fall back to $renderedCheckName ("Education Verification"),
            // exactly like the old check_only path (2026-08-26 - see the
            // $renderedCheckName block above).
        }

        // Resolve DOCUMENTS (Mandatory + Any-one-of buckets - see class docblock,
        // redesigned 2026-08-18 to replace the GROUPS model after the owner's live
        // test proved "pick one whole alternative bundle" was the wrong semantics
        // for a case that was actually "all of these mandatory PLUS any one of these")
        $documentsRendered = '';
        $combinedDocumentOverride = null;
        if (in_array('DOCUMENTS', $tpl['needed_tags'], true)) {
            $clean = function ($arr) {
                if (!is_array($arr)) return [];
                return array_values(array_filter(array_map('trim', $arr), fn($x) => $x !== ''));
            };
            $mandatory = $clean($input['mandatory_documents'] ?? []);
            $anyOneOf = $clean($input['any_one_of_documents'] ?? []);

            if (count($mandatory) === 0 && count($anyOneOf) === 0) {
                return ['error' => 'At least one document is required (Mandatory and/or Any-one-of).'];
            }
            if (count(array_unique($mandatory)) !== count($mandatory)) {
                return ['error' => 'Duplicate document selected within Mandatory documents.'];
            }
            if (count(array_unique($anyOneOf)) !== count($anyOneOf)) {
                return ['error' => 'Duplicate document selected within Any-one-of documents.'];
            }
            $overlap = array_values(array_unique(array_intersect($mandatory, $anyOneOf)));
            if (count($overlap) > 0) {
                return ['error' => 'A document can only be in Mandatory OR Any-one-of, not both: ' . implode(', ', $overlap)];
            }

            if ($this->needsCombinedDocumentSentence($mandatory, $anyOneOf)) {
                $combinedDocumentOverride = $this->combinedDocumentSentence($mandatory, $anyOneOf, $context, $tpl['reason_sub_type']);
                // DOCUMENTS isn't substituted in this branch (the combined sentence
                // replaces the whole output), but it's still in needed_tags, so give
                // it a non-empty placeholder to avoid a false "missing" error below.
                $documentsRendered = $this->mandatoryPhrase($mandatory) ?: $this->anyOneOfInline($anyOneOf);
            } elseif ($this->needsAnyOneOfOnlySentence($mandatory, $anyOneOf)) {
                // Added 2026-08-26 - see anyOneOfOnlySentence()'s own docblock for
                // why this is a separate branch/method from the combined case above.
                $combinedDocumentOverride = $this->anyOneOfOnlySentence($anyOneOf, $context, $tpl['reason_sub_type']);
                $documentsRendered = $this->anyOneOfInline($anyOneOf);
            } elseif ($this->needsMandatoryOnlySentence($mandatory, $anyOneOf)) {
                // Added 2026-08-26 (same day, owner asked for the identical treatment
                // on the Mandatory-only/AND case that anyOneOfOnlySentence() already
                // gives the Any-one-of-only/OR case) - see mandatoryOnlySentence()'s
                // own docblock.
                $combinedDocumentOverride = $this->mandatoryOnlySentence($mandatory, $context, $tpl['reason_sub_type']);
                $documentsRendered = $this->mandatoryPhrase($mandatory);
            } elseif (count($mandatory) > 0) {
                $documentsRendered = $this->mandatoryPhrase($mandatory);
            } else {
                $documentsRendered = $this->anyOneOfInline($anyOneOf);
            }
        }

        // Resolve special instructions (Document/Missing branches only)
        //
        // Two possible renderings, chosen per-template via
        // `special_instructions_format` (added 2026-08-26, opt-in, scoped to
        // T9 only for now - see specialInstructionsBlock()'s docblock):
        // the default $specialInstrText inline sentence (every other Document
        // template, unchanged), or $specialInstrBlock, a headed "Document
        // Requirements:" bulleted block with fuller candidate-facing phrasing.
        $specialInstrText = '';
        $specialInstrBlock = null;
        if (!empty($input['special_instructions']) && is_array($input['special_instructions'])) {
            $items = array_values(array_filter(array_map('trim', $input['special_instructions']), fn($x) => $x !== ''));
            if (count($items)) {
                if (($tpl['special_instructions_format'] ?? null) === 'document_requirements') {
                    $specialInstrBlock = $this->specialInstructionsBlock($items);
                } else {
                    $specialInstrText = ' Please ensure the copy is: ' . $this->joinList($items, 'AND') . '.';
                }
            }
        }

        // Generic tag resolution for everything else the template needs
        $values = [
            'CHECK_NAME' => $renderedCheckName,
            'COURSE_NAME' => $input['course_name'] ?? '',
            'VS' => $input['vs'] ?? '',
            'DOCUMENTS' => $documentsRendered,
            'CONTEXT' => $context,
            'FORM_COMPANY_NAME' => $this->tagValues['FORM_COMPANY_NAME']['value'] ?? 'AuthBridge Research Services Pvt. Ltd.',
        ];
        // Raw (pre-join) arrays kept alongside the joined string form above -
        // listBlock() (added 2026-08-23) needs the actual list of values to
        // render one bullet per item; $values[$tag] alone only has the
        // "X and Y" prose-joined string by the time the loop below runs.
        $rawTagArrays = [];
        foreach (($input['tags'] ?? []) as $k => $v) {
            if (is_array($v)) { $rawTagArrays[$k] = $v; }
            $values[$k] = is_array($v) ? $this->joinList($v, 'AND') : trim((string)$v);
        }

        // Reason + bulleted Solution + Action block (added 2026-08-23) - see
        // listBlock()'s docblock. Opt-in via templates.json's `list_block`
        // field (tag + lead_in with a {CONTEXT} placeholder); a template with
        // no `list_block` renders exactly as before via plain substitution.
        //
        // Fixed 2026-08-25 (owner live-tested T74 - "why do we not have any
        // docs or details here to select?" - the generated comment said only
        // "The document submitted for X could not be read clearly", never
        // naming WHICH document): lead_in now also substitutes <DOCUMENTS>/
        // {DOCUMENTS} using the same $documentsRendered value computed above
        // (T73/T74 now carry DOCUMENTS in needed_tags, so the Mandatory/
        // Any-one-of checkbox builder renders for them in the UI same as
        // T9-T13). $documentsRendered is already populated by this point
        // regardless of which DOCUMENTS branch ran, including the combined
        // Mandatory+Any-one-of case (mandatoryPhrase()/anyOneOfInline()
        // fallback), so this substitution is safe even then.
        $listBlockOverride = null;
        if (!empty($tpl['list_block'])) {
            $lbTag = $tpl['list_block']['tag'];
            $lbItems = array_values(array_filter(array_map('trim', $rawTagArrays[$lbTag] ?? []), fn($x) => $x !== ''));
            if (count($lbItems) > 0) {
                $lbLeadIn = str_replace(
                    ['<CONTEXT>', '{CONTEXT}', '<DOCUMENTS>', '{DOCUMENTS}'],
                    [$context, $context, $documentsRendered, $documentsRendered],
                    $tpl['list_block']['lead_in']
                );
                $listBlockOverride = $this->listBlock($lbLeadIn, $lbItems, $lbTag);
            }
        }

        // Optional cost-breakdown suffix (added 2026-08-19, fifth pass - full-template
        // tag audit). PRICING_TOOL_COST/ADDITIONAL_COST are deliberately NOT in any
        // template's needed_tags (real T8 data shows ~32% of cases genuinely state
        // only the total) - generic, not template-specific, so any template asking
        // for a cost approval benefits automatically. Only renders when BOTH are
        // provided together; otherwise the plain total-only sentence is unchanged.
        $costBreakdownText = '';
        $pricingCost = trim((string)($input['tags']['PRICING_TOOL_COST'] ?? ''));
        $additionalCost = trim((string)($input['tags']['ADDITIONAL_COST'] ?? ''));
        if ($pricingCost !== '' && $additionalCost !== '') {
            $currency = trim((string)($values['CURRENCY'] ?? ''));
            $costBreakdownText = " (Base verification cost: $currency $pricingCost + Additional cost: $currency $additionalCost)";
        }

        // Validate every needed tag has a non-empty value before rendering
        $missing = [];
        foreach ($tpl['needed_tags'] as $tag) {
            if ($tag === 'CONTEXT') continue;
            if (!isset($values[$tag]) || trim((string)$values[$tag]) === '') {
                $missing[] = $tag;
            }
        }
        if (!empty($missing)) {
            return ['error' => 'Missing required value(s): ' . implode(', ', $missing), 'missing_tags' => $missing];
        }

        // Render: replace both <TAG> (raw template style) and {TAG} (reason-clause style) -
        // UNLESS the combined Mandatory+Any-one-of block, or the ANTECEDENTS/
        // CASE_LEVEL_INFORMATION/INCOMPLETE_DETAIL/BLUR_DETAIL list block,
        // overrides this entirely (a headed/bulleted layout doesn't fit
        // substituted mid-sentence like a plain noun phrase). Both bulleted
        // blocks end on a bullet line (no trailing period), so special
        // instructions are appended as their own paragraph, not glued onto
        // the last bullet.
        //
        // list_block checked FIRST, ahead of the combined-document override
        // (fixed 2026-08-25, same pass as the DOCUMENTS substitution above):
        // T73/T74 are the first templates to carry both DOCUMENTS and
        // list_block. If an agent fills both the Mandatory and Any-one-of
        // buckets on one of them, needsCombinedDocumentSentence() would also
        // return true - without this ordering, the combined document
        // sentence would silently replace the whole comment and DROP the
        // INCOMPLETE_DETAIL/BLUR_DETAIL bullets entirely (the actual point
        // of T73/T74), instead of just stating which documents are affected.
        // Every other list_block template (T14/T18/T51) has no DOCUMENTS in
        // its needed_tags, so this reordering is a no-op for them -
        // $combinedDocumentOverride is never non-null when $listBlockOverride
        // is also non-null except for T73/T74.
        // $specialInstrBlock (the new "Document Requirements:" bulleted form)
        // takes precedence over $specialInstrText (the old inline sentence)
        // wherever both could theoretically apply - they're mutually
        // exclusive per-template anyway (special_instructions_format decides
        // which one gets populated above), this is just the safe order.
        if ($listBlockOverride !== null) {
            $extra = $specialInstrBlock !== null ? ("\n\n" . $specialInstrBlock)
                : (trim($specialInstrText) !== '' ? ("\n\n" . ltrim($specialInstrText)) : '');
            $text = $listBlockOverride . $extra;
        } elseif ($combinedDocumentOverride !== null) {
            $extra = $specialInstrBlock !== null ? ("\n\n" . $specialInstrBlock)
                : (trim($specialInstrText) !== '' ? ("\n\n" . ltrim($specialInstrText)) : '');
            $text = $combinedDocumentOverride . $extra;
        } else {
            $text = $tpl['optimized_text'];
            foreach ($values as $tag => $val) {
                $text = str_replace("<$tag>", $val, $text);
                $text = str_replace("{{$tag}}", $val, $text);
            }
            // Cost breakdown (if present) is inserted before the trailing period so it
            // reads "...for Education Verification (Base cost: ... + Additional cost: ...)."
            // rather than after it.
            $text = trim($text);
            if ($costBreakdownText !== '' && str_ends_with($text, '.')) {
                $text = substr($text, 0, -1) . $costBreakdownText . '.';
            } elseif ($costBreakdownText !== '') {
                $text .= $costBreakdownText;
            }
            if ($specialInstrBlock !== null) {
                $text .= "\n\n" . $specialInstrBlock;
            } else {
                $text .= $specialInstrText;
            }
        }

        // Safety net: never let a raw placeholder reach the output
        if (preg_match('/[<{][A-Za-z0-9_]+[>}]/', $text, $m)) {
            return ['error' => 'Unresolved placeholder remained in output: ' . $m[0] . ' — check needed_tags/input mapping.'];
        }

        return [
            'template_id' => $tpl['id'],
            'insuff_category' => $tpl['insuff_category'],
            'reason_category' => $tpl['reason_category'],
            'reason_sub_type' => $tpl['reason_sub_type'],
            'reason_clause_added' => $tpl['reason_clause_added'],
            'final_comment' => $text,
        ];
    }
}
