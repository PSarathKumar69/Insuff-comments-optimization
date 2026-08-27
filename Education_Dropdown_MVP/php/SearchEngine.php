<?php
require_once __DIR__ . '/GeminiTriageClient.php';

/**
 * SearchEngine — the "support triage" feature: given a historical (or brand
 * new) actual insufficiency comment typed in free text, answer two things:
 *   1. Does today's dropdown system support generating an equivalent comment?
 *   2. If yes, exactly which dropdowns to click/select, in order, to do it.
 *
 * Redesigned 2026-08-15 per owner correction: the original version returned
 * a ranked list of similar historical comments with a status pill each,
 * leaving the user to interpret them. Needs a single clear verdict up front
 * (Supported / Not supported) followed by a step-by-step walkthrough.
 *
 * Hybrid matching, added 2026-08-15 (same day, second fix): the local
 * normalized-token-overlap match (instant, free, correct most of the time)
 * was found to mis-fire on short queries where generic words ("for", "the",
 * "verification") outweigh the one word that actually carries meaning - e.g.
 * "Requesting the extra TAT for verification" scored higher against an
 * unrelated Document-Missing row than against the correct TAT Approval
 * template (T60), because "verification" is common to almost every row.
 * Rather than replace the local matcher entirely with a live LLM call on
 * every keystroke-triggered search (adds latency + an external dependency to
 * every single check, and this project's own batch-classification log shows
 * Gemini hitting 429/503 errors repeatedly), this only escalates to
 * GeminiTriageClient when the local result is genuinely ambiguous.
 *
 * Confidence check, REVISED 2026-08-15 (third fix, same day): the first cut
 * of this compared raw scores between the top TWO HISTORICAL ROWS ("is the
 * #1 row's score meaningfully ahead of the #2 row's score?"). That was wrong
 * for this dataset: it's full of near-duplicate real comments (many
 * differently-worded rows all meaning "kindly provide X"), so the #1 and #2
 * rows are almost always near-tied in raw score EVEN WHEN they both resolve
 * to the exact same template - that's not ambiguity, that's just two
 * near-identical historical phrasings of the same answer. Under that logic,
 * roughly 80%+ of realistic queries got flagged "ambiguous" and sent to
 * Gemini on every single search, which is what made the feature feel slow.
 * Fixed to compare TEMPLATES, not raw scores: gather the near-top cluster of
 * candidates (within CLUSTER_TOLERANCE of the best score), and only escalate
 * if that cluster disagrees on which template it resolves to. If they all
 * point to the same template regardless of tiny score differences between
 * them, that's confident - no need to ask Gemini. Verified against the real
 * dataset this roughly halves the escalation rate while still correctly
 * escalating genuine cross-template ambiguity (the TAT case still escalates
 * under this logic, since its top candidates split between two different,
 * both-wrong templates).
 *
 * If Gemini is unavailable (no key configured, network error, timeout,
 * malformed response) this fails soft - it never throws or breaks the
 * feature - but as of 2026-08-26 failing soft means returning an honest
 * "Not supported / unresolved" verdict, NOT a caveated "Supported" guess
 * built from the ambiguous local match. See evaluate() for the full
 * rationale.
 */

class SearchEngine
{
    private array $rows;
    private array $templatesById;
    private array $tagValues;
    private GeminiTriageClient $gemini;

    // MIN_SCORE (0.15) removed 2026-08-26 - see evaluate() for why there is no
    // longer a weak-score fallback tier below LOCAL_CONFIDENCE_FLOOR.
    // A local match below this is too weak to trust at all, regardless of
    // whether the near-top candidates happen to agree on a template.
    private const LOCAL_CONFIDENCE_FLOOR = 0.25;
    // Candidates within this of the top score are considered "tied" for
    // purposes of checking template agreement (not "tied" in absolute score).
    private const CLUSTER_TOLERANCE = 0.05;
    // How many top candidates to pull per query - wide enough to catch every
    // near-duplicate historical phrasing that could be part of the same tie.
    private const TOP_K = 8;

    private const SCOPE_FIELD_LABELS = [
        'course_vs' => ['COURSE_NAME' => 'Course / degree name', 'VS' => 'Institute name'],
        'vs_only'   => ['VS' => 'Institute / employer name'],
        // Added 2026-08-18 (fourth fix): course_vs_optional REPLACES the old
        // course_vs/check_only Scope choice for 8 merged template pairs (see
        // CommentEngine.php's course_vs_optional branch for the root-cause
        // writeup). Unlike plain course_vs, these fields are NOT mandatory -
        // buildSteps() below phrases them as optional-together rather than
        // required, and includes YEAR_FROM/YEAR_TO here too (since those are
        // no longer in needed_tags for these templates - they're conditional
        // on course/institute being filled in, same as CommentEngine.php).
        'course_vs_optional' => [
            'COURSE_NAME' => 'Course / degree name',
            'VS' => 'Institute name',
            'YEAR_FROM' => 'Year started',
            'YEAR_TO' => 'Year completed',
        ],
    ];

    // Tags that are structural (auto-filled, or resolved into CONTEXT/DOCUMENTS
    // separately) and never get their own "fill in this field" step.
    // NOTE (fixed 2026-08-19, fifth pass): COURSE_NAME/VS used to be in this
    // list unconditionally, on the assumption they're always rendered by the
    // course_vs/vs_only/course_vs_optional branch above. That's false for a
    // "check_only" template that uses VS as a plain generic tag (T65 -
    // institute name for an address request) - it would silently get no step
    // at all. COURSE_NAME/VS are now context-conditionally skipped instead,
    // see buildSteps()'s $contextHandledTags.
    private const SKIP_TAGS = ['CHECK_NAME', 'CONTEXT', 'FORM_COMPANY_NAME'];

    public function __construct(string $dataDir)
    {
        // search_index.json is deliberately NOT committed to version control - it
        // holds 8,284 real historical comments carrying third-party PII (see the
        // repo .gitignore and Education_Dropdown_MVP/README.md). Any deployment
        // built from the repo alone (Vercel, a fresh clone) therefore starts
        // WITHOUT it. Added 2026-08-27: treat that as an empty index rather than
        // letting file_get_contents() warn and json_decode(false) hand back null,
        // which used to make the very next foreach fatal - a 500 on every search
        // request instead of a usable app with one feature switched off.
        $indexPath = $dataDir . '/search_index.json';
        $this->rows = is_readable($indexPath)
            ? (json_decode(file_get_contents($indexPath), true) ?: [])
            : [];
        $templates = json_decode(file_get_contents($dataDir . '/templates.json'), true);
        $this->tagValues = json_decode(file_get_contents($dataDir . '/tag_values.json'), true);
        $this->templatesById = [];
        foreach ($templates as $t) {
            $this->templatesById[$t['id']] = $t;
        }
        // dataDir is .../Education_Dropdown_MVP/data - the project's .env
        // (holding the distinct TRIAGE_GEMINI_API_KEY) lives two levels up.
        $this->gemini = new GeminiTriageClient($dataDir . '/../..');
    }

    private function normalize(string $s): array
    {
        $s = strtolower($s);
        $s = preg_replace('/[^a-z0-9\s]/', ' ', $s);
        $tokens = preg_split('/\s+/', trim($s));
        return array_values(array_filter($tokens, fn($t) => strlen($t) > 2));
    }

    private function score(array $queryTokens, array $rowTokens): float
    {
        if (empty($queryTokens) || empty($rowTokens)) return 0.0;
        $qSet = array_unique($queryTokens);
        $rSet = array_unique($rowTokens);
        $intersect = count(array_intersect($qSet, $rSet));
        $union = count(array_unique(array_merge($qSet, $rSet)));
        return $union > 0 ? $intersect / $union : 0.0;
    }

    /** Top-K closest historical rows by normalized-token overlap, scores > 0 only, sorted desc. */
    private function findTopMatches(string $query, int $k = 5): array
    {
        $qTokens = $this->normalize($query);
        if (empty($qTokens)) return [];

        $scored = [];
        foreach ($this->rows as $row) {
            $s = $this->score($qTokens, $this->normalize($row['comment']));
            if ($s > 0) {
                $row['_score'] = $s;
                $scored[] = $row;
            }
        }
        usort($scored, fn($a, $b) => $b['_score'] <=> $a['_score']);
        return array_slice($scored, 0, $k);
    }

    private function fieldLabel(string $tag): string
    {
        $label = str_replace('_', ' ', $tag);
        return ucwords(strtolower($label));
    }

    /**
     * Builds the ordered click-by-click guide for a template, given a flat
     * tag => suggested-value map and an optional ordered list of suggested
     * documents. Source-agnostic: the caller passes either a matched
     * historical row's own extracted_tags/suggested_documents, or Gemini's
     * extracted values - the guide-building logic doesn't care which.
     */
    private function buildSteps(array $tpl, array $extractedTags, array $suggestedDocuments): array
    {
        $path = $tpl['dropdown_path'];
        $steps = [];
        $n = 1;

        // Step-text labels renamed 2026-08-24 to match the current UI
        // (Category/Sub-Category/Reason/Scope) - these used to say "Insuff
        // Category"/"Category" from before that day's UI relabeling, which
        // had drifted out of sync with the actual on-screen field labels.
        // dropdown_path's own JSON key names (insuff_category, reason,
        // reason_detail, scope_label) are unchanged.
        $steps[] = ['step' => $n++, 'instruction' => "Set \"Category\" to \"{$path['insuff_category']}\"."];

        if ($path['reason_step_shown']) {
            $steps[] = ['step' => $n++, 'instruction' => "Set \"Sub-Category\" to \"{$path['reason']}\"."];
        }
        $steps[] = ['step' => $n++, 'instruction' => "Set \"Reason\" to \"{$path['reason_detail']}\"."];

        // Scenario step REMOVED 2026-08-26 (owner: "remove the Scenario Tag
        // from the UI - it doesn't make any sense"). This step existed
        // 2026-08-24 through 2026-08-26 for Document/Information's Reason
        // buckets, which used to resolve through a nested Scenario map
        // rather than straight to a template. dropdown_path.reason_detail
        // now already carries the combined "{Reason} - {Scenario}" text for
        // those 21 templates (dropdown_path.reason_scenario is nulled out
        // on all of them), so the single "Set Reason" step above already
        // states the full, final pick with no separate step needed.

        if ($path['needs_scope_choice']) {
            $steps[] = ['step' => $n++, 'instruction' => "Set \"Scope\" to \"{$path['scope_label']}\"."];
        }

        if ($tpl['context_mode'] === 'course_vs' || $tpl['context_mode'] === 'vs_only') {
            foreach (self::SCOPE_FIELD_LABELS[$tpl['context_mode']] as $tag => $label) {
                $suggestion = $extractedTags[$tag] ?? null;
                $instruction = "Enter the \"$label\"" . ($suggestion ? " (suggested from this comment: \"$suggestion\")" : '') . '.';
                $steps[] = ['step' => $n++, 'instruction' => $instruction];
            }
        } elseif ($tpl['context_mode'] === 'course_vs_optional') {
            // Added 2026-08-18 (fourth fix): these 4 fields are optional-together
            // (fill in Course/Institute/Year all four, or leave all four blank) -
            // phrased differently from the mandatory course_vs case above so the
            // step guide doesn't wrongly tell the user these are required.
            $anySuggested = false;
            foreach (self::SCOPE_FIELD_LABELS['course_vs_optional'] as $tag => $label) {
                if (!empty($extractedTags[$tag])) { $anySuggested = true; break; }
            }
            $intro = $anySuggested
                ? 'This historical comment names a specific course/institute - fill in the following (all four together):'
                : 'If this requirement is tied to a specific course/degree, fill in the following (all four together); otherwise leave them blank:';
            $steps[] = ['step' => $n++, 'instruction' => $intro];
            foreach (self::SCOPE_FIELD_LABELS['course_vs_optional'] as $tag => $label) {
                $suggestion = $extractedTags[$tag] ?? null;
                $instruction = "  - \"$label\"" . ($suggestion ? " (suggested from this comment: \"$suggestion\")" : ' (optional)') . '.';
                $steps[] = ['step' => $n++, 'instruction' => $instruction];
            }
            // Added 2026-08-26: if the historical comment doesn't name a
            // course/institute, CommentEngine.php now requires picking at
            // least one "Qualification Level" (UG/PG/Highest degree/etc.)
            // instead of leaving the case fully generic - mirror that
            // requirement here so the step guide doesn't tell the agent
            // they're done after leaving all four fields blank.
            if (!$anySuggested) {
                $steps[] = ['step' => $n++, 'instruction' => 'Since no course/institute is named, also pick at least one "Qualification Level" (UG/PG/Highest degree/etc.) - required whenever the four fields above are all left blank.'];
            }
        }

        // Fixed 2026-08-19 (fifth pass): mirrors app.js's CONTEXT_HANDLED_TAGS -
        // only skip COURSE_NAME/VS/YEAR_FROM/YEAR_TO here if the branch above
        // already produced a step for them.
        $contextHandledTags = match ($tpl['context_mode']) {
            'course_vs' => ['COURSE_NAME', 'VS'],
            'vs_only' => ['VS'],
            'course_vs_optional' => ['COURSE_NAME', 'VS', 'YEAR_FROM', 'YEAR_TO'],
            default => [],
        };

        foreach ($tpl['needed_tags'] as $tag) {
            if (in_array($tag, self::SKIP_TAGS, true) || in_array($tag, $contextHandledTags, true)) continue;

            if ($tag === 'DOCUMENTS') {
                // Historical suggested_documents is a flat list mined from one real
                // comment - it doesn't distinguish "always required" from "pick one of",
                // so the honest suggestion is to put them all in Mandatory (that's how
                // the historical comment actually read - every document in it, required
                // together). If the real case ALSO needs a pick-one-of-these on top of
                // that, that's an Any-one-of selection the user adds themselves, not
                // something inferable from a single historical example.
                //
                // Rewritten 2026-08-18 for the Mandatory + Any-one-of redesign (replacing
                // the GROUPS/"Add alternative (OR)" mechanic entirely - see
                // CommentEngine.php's class docblock for why: a live test showed "pick
                // one whole alternative group" was the wrong semantics for a case that
                // was actually "all of these mandatory PLUS any one of these").
                if (count($suggestedDocuments) === 0) {
                    $steps[] = ['step' => $n++, 'instruction' => 'In Mandatory documents, check the required document(s).'];
                } elseif (count($suggestedDocuments) === 1) {
                    $steps[] = ['step' => $n++, 'instruction' => "In Mandatory documents, check \"{$suggestedDocuments[0]}\"."];
                } else {
                    $list = implode(', ', $suggestedDocuments);
                    $steps[] = ['step' => $n++, 'instruction' => "In Mandatory documents, check all of: {$list} (they were all required together in this historical comment). Only use the Any-one-of section if the real case ALSO needs a pick-one-of-these requirement on top of that - the final comment will state both parts clearly (\"...mandatory documents: A, B, and C. Along with these, submit any ONE of: D, E, or F.\")."];
                }
                continue;
            }

            // VS falling through to here (added 2026-08-19, fifth pass) means a
            // check_only template uses it as a plain generic tag (T65) rather
            // than via a context_mode branch - use the same friendly label the
            // context branches use instead of the generic titlecase fallback ("Vs").
            $label = $tag === 'VS' ? 'Institute name' : $this->fieldLabel($tag);
            $suggestion = $extractedTags[$tag] ?? null;
            $instruction = "Fill in \"$label\"" . ($suggestion ? " (suggested from this comment: \"$suggestion\")" : '') . '.';
            $steps[] = ['step' => $n++, 'instruction' => $instruction];
        }

        if ($tpl['reason_category'] === 'Document') {
            $steps[] = ['step' => $n++, 'instruction' => 'Optionally tick any relevant "Special instructions" (e.g. duly signed, both-side colour copy).'];
        }

        $steps[] = ['step' => $n, 'instruction' => 'The final comment renders automatically in the live preview as you complete the fields above — no separate "generate" click needed.'];

        return $steps;
    }

    /** Builds the response for a confident, purely-local match (existing 3-way status logic, unchanged). */
    private function evaluateFromLocalMatch(string $query, array $match): array
    {
        $base = [
            'query' => $query,
            'matched_by' => 'local',
            'matched_historical_comment' => $match['comment'],
            'match_score' => round($match['_score'], 2),
            'match_seen_count' => $match['count'],
        ];

        if ($match['status'] === 'template_exists_not_in_education_mvp') {
            return $base + [
                'supported' => false,
                'verdict_label' => 'Not supported (yet)',
                'verdict_reason' => "The closest historical match resolves to template {$match['resolved_template_id']}, which exists in the wider template set but isn't wired into this Education build (it's an Employment/Address-specific template). Not available to select today.",
                'template_id' => $match['resolved_template_id'],
                'steps' => [],
            ];
        }

        if ($match['status'] === 'not_supported' || !$match['resolved_template_id']) {
            return $base + [
                'supported' => false,
                'verdict_label' => 'Not supported',
                'verdict_reason' => 'The closest historical match itself was never resolved to a template (it was one of the ~0.25% "Not Captured" rows) - this comment likely needs a new template rather than an existing one.',
                'template_id' => null,
                'steps' => [],
            ];
        }

        $tpl = $this->templatesById[$match['resolved_template_id']] ?? null;
        if ($tpl === null) {
            return $base + [
                'supported' => false,
                'verdict_label' => 'Not supported',
                'verdict_reason' => "Internal: resolved template {$match['resolved_template_id']} was not found in templates.json.",
                'template_id' => $match['resolved_template_id'],
                'steps' => [],
            ];
        }

        return $base + [
            'supported' => true,
            'verdict_label' => 'Supported',
            'verdict_reason' => "Matches template {$tpl['id']} ({$tpl['insuff_category']} / {$tpl['reason_category']} / {$tpl['reason_sub_type']}) - here's how to build it.",
            'template_id' => $tpl['id'],
            'steps' => $this->buildSteps($tpl, $match['extracted_tags'] ?? [], $match['suggested_documents'] ?? []),
        ];
    }

    /** Builds the response for a Gemini-resolved query (only reached when the local match was weak/ambiguous). */
    private function evaluateFromGemini(string $query, array $gem, ?array $localTop): array
    {
        $base = [
            'query' => $query,
            'matched_by' => 'gemini',
            'gemini_confidence' => $gem['confidence'] ?? null,
        ];
        if ($localTop !== null) {
            $base['matched_historical_comment'] = $localTop['comment'];
            $base['match_score'] = round($localTop['_score'], 2);
            $base['match_seen_count'] = $localTop['count'];
        }

        $tid = $gem['template_id'] ?? 'no_match';
        if ($tid === 'no_match' || $tid === '') {
            return $base + [
                'supported' => false,
                'verdict_label' => 'Not supported',
                'verdict_reason' => 'Gemini reviewed this comment against all ' . count($this->templatesById) . ' templates and found no confident fit' . (!empty($gem['reasoning']) ? ": {$gem['reasoning']}" : '.') . ' This likely needs a new template.',
                'template_id' => null,
                'steps' => [],
            ];
        }

        $tpl = $this->templatesById[$tid] ?? null;
        if ($tpl === null) {
            // Gemini returned a template_id we don't recognize (hallucination) - fail soft to "not supported" rather than crash.
            return $base + [
                'supported' => false,
                'verdict_label' => 'Not supported',
                'verdict_reason' => "Gemini suggested template $tid, which isn't a valid template in this build - treating as unresolved. This likely needs a new template.",
                'template_id' => null,
                'steps' => [],
            ];
        }

        $extractedTags = [];
        foreach (($gem['extracted_tags'] ?? []) as $t) {
            $tag = $t['tag'] ?? null;
            if (!$tag) continue;
            $extractedTags[$tag] = $t['matched_dropdown_value'] ?? $t['raw_value'] ?? null;
        }
        $suggestedDocuments = array_values(array_filter($gem['suggested_documents'] ?? []));

        return $base + [
            'supported' => true,
            'verdict_label' => 'Supported',
            'verdict_reason' => "Gemini matched this to template {$tpl['id']} ({$tpl['insuff_category']} / {$tpl['reason_category']} / {$tpl['reason_sub_type']}, confidence: {$gem['confidence']}) - here's how to build it.",
            'template_id' => $tpl['id'],
            'steps' => $this->buildSteps($tpl, $extractedTags, $suggestedDocuments),
        ];
    }

    /** Response when neither local nor Gemini could resolve anything (or Gemini wasn't configured/reachable). */
    private function notSupportedNoMatch(string $query, bool $geminiAttempted, bool $geminiAvailable): array
    {
        // Reworded 2026-08-26: the Gemini-unavailable branch is now the ONLY
        // outcome when the local match is ambiguous and Gemini can't be reached,
        // so it gets its own wording. The default "nothing matched, may need a new
        // template" sentence is actively wrong there - something usually DID match,
        // it just couldn't be trusted, and the fix for the agent is to pick the
        // path manually, not to request a new template.
        $reason = "This doesn't closely match anything in the classified historical dataset, so there's no confident way to tell which template (if any) would cover it. It may need a new template.";
        if ($geminiAttempted && !$geminiAvailable) {
            $reason = 'The closest keyword matches were either too weak or split across more than one template to trust, and Gemini escalation was unavailable to break the tie - so this is reported as unresolved rather than as a best guess. Pick the dropdown path manually, or escalate.';
        }
        return [
            'query' => $query,
            'matched_by' => $geminiAttempted ? ($geminiAvailable ? 'gemini' : 'local_fallback') : 'local',
            'supported' => false,
            'verdict_label' => 'Not supported',
            'verdict_reason' => $reason,
            'template_id' => null,
            'steps' => [],
            'matched_historical_comment' => null,
            'match_score' => 0.0,
        ];
    }

    /**
     * Decides whether the local top-K result is confident enough to trust
     * without asking Gemini. Confident means: the best score clears
     * LOCAL_CONFIDENCE_FLOOR, AND every candidate within CLUSTER_TOLERANCE of
     * that best score resolves to the SAME template (agreement on the
     * answer, not agreement on which literal historical row is closest -
     * near-duplicate rows of the same template tying on score is expected
     * and fine, not a sign of ambiguity).
     */
    private function localConfidence(array $top): bool
    {
        if (empty($top) || $top[0]['_score'] < self::LOCAL_CONFIDENCE_FLOOR) {
            return false;
        }
        $topScore = $top[0]['_score'];
        $cluster = array_filter($top, fn($r) => $r['_score'] >= $topScore - self::CLUSTER_TOLERANCE);
        $signatures = array_unique(array_map(fn($r) => ($r['resolved_template_id'] ?? '') . '|' . $r['status'], $cluster));
        return count($signatures) === 1;
    }

    /**
     * Main entry point. Returns:
     *   supported (bool), verdict_label, verdict_reason, matched_by ('local'|'gemini'|'local_fallback'),
     *   template_id (nullable), steps (array, empty if not supported),
     *   matched_historical_comment, match_score, match_seen_count
     */
    /** True when search_index.json was present and non-empty at construction. */
    public function hasIndex(): bool
    {
        return !empty($this->rows);
    }

    public function evaluate(string $query): array
    {
        // No index deployed (see __construct). Say so plainly instead of
        // reporting "doesn't match anything in the classified historical
        // dataset", which would be a lie about a dataset that isn't loaded -
        // and would send the agent off to request a new template for a query
        // the tool never actually looked at. Gemini is still tried first if
        // it's configured, since it needs no local index to resolve a query.
        if (!$this->hasIndex()) {
            $gem = $this->gemini->isConfigured()
                ? $this->gemini->classify($query, array_values($this->templatesById), $this->tagValues)
                : null;
            if ($gem !== null) {
                return $this->evaluateFromGemini($query, $gem, null);
            }
            return [
                'query' => $query,
                'matched_by' => 'no_index',
                'supported' => null,
                'verdict_label' => 'Search unavailable',
                'verdict_reason' => 'The historical comment index (data/search_index.json) is not present in this deployment, so a real comment cannot be matched to a dropdown path here. The dropdown generator itself is unaffected. See Education_Dropdown_MVP/README.md for how to supply the index.',
                'template_id' => null,
                'steps' => [],
                'matched_historical_comment' => null,
                'match_score' => 0.0,
            ];
        }

        $top = $this->findTopMatches($query, self::TOP_K);

        if ($this->localConfidence($top)) {
            return $this->evaluateFromLocalMatch($query, $top[0]);
        }
        // Local result is weak or ambiguous - escalate to Gemini.
        $geminiAvailable = $this->gemini->isConfigured();
        $gem = $geminiAvailable ? $this->gemini->classify($query, array_values($this->templatesById), $this->tagValues) : null;

        if ($gem !== null) {
            return $this->evaluateFromGemini($query, $gem, $top[0] ?? null);
        }

        // Gemini unavailable (not configured, or the call failed) and the local
        // match already failed localConfidence() - so nothing here can resolve
        // the query. Report it as unresolved.
        //
        // Changed 2026-08-26 (fifth fix): this used to fall back to the local
        // top-1 whenever it cleared a much weaker MIN_SCORE (0.15) floor, and
        // returned a full "Supported" verdict + step guide with a "Local best
        // guess" caveat appended to verdict_reason. In the UI that renders as a
        // green Supported badge and a numbered walkthrough - i.e. it looks
        // exactly like a confident answer - for a match the engine itself just
        // decided it could not trust. Reported case: "please provide the
        // photograph with white background" scored 0.333 (clears the 0.25
        // confidence floor) but its near-top cluster split across T9 and T13, so
        // localConfidence() failed; with Gemini unavailable it still came back
        // "Supported -> T9 (Document/Missing)". A support agent then follows a
        // step guide for the wrong template. An honest "Not supported /
        // unresolved" is the only safe verdict here: the agent escalates or
        // picks the dropdown path manually instead of trusting a coin flip.
        // MIN_SCORE was deleted rather than repurposed - it existed solely to
        // gate this fallback tier, and there is no longer any "trust it a
        // little" tier between localConfidence() (trust it) and unresolved
        // (don't). A second, lower threshold would just re-create the same
        // misleading middle ground under a new name.
        return $this->notSupportedNoMatch($query, true, false);
    }
}
