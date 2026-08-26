<?php
/**
 * GeminiTriageClient — real-time semantic fallback for the support-triage
 * feature, called only when the fast local token-overlap match (in
 * SearchEngine.php) is weak or ambiguous. Added 2026-08-15 after a reported
 * bug: "Requesting the extra TAT for verification" matched a Document-
 * Missing template at 33% score instead of the correct TAT Approval
 * template (T60), because plain token overlap treats generic words ("for",
 * "the", "verification") as equally significant as the one word that
 * actually signals intent ("TAT"). Rather than replace the local matcher
 * (which is instant, free, and correct most of the time) or run Gemini on
 * every single query (adds latency + an external dependency to every click,
 * and this project's own batch-classification log shows Gemini hitting
 * 429/503 errors repeatedly), this only escalates the hard cases.
 *
 * Uses a DISTINCT API key (TRIAGE_GEMINI_API_KEY) from the one used by the
 * offline build/classification scripts (GEMINI_API_KEY) - both live in the
 * same project .env, but are kept separate per owner instruction so this
 * live, user-facing feature's quota/billing is never shared with or
 * exhausted by the batch pipeline's usage, and vice versa.
 *
 * Fails soft: any network error, timeout, non-200 response, or malformed
 * JSON returns null so the caller (SearchEngine::evaluate()) can fall back
 * to the local match with a clear "Gemini was unavailable" note rather than
 * breaking the feature.
 */

class GeminiTriageClient
{
    private ?string $apiKey;
    private string $model;
    // Kept tight since this blocks an interactive page (unlike the batch
    // scripts' 45-minute retry loops): if the network can't reach Gemini at
    // all (e.g. a corporate proxy blocking generativelanguage.googleapis.com
    // - confirmed to happen from this project's own dev sandbox), fail fast
    // and fall back to the local answer instead of making the user wait.
    private const TIMEOUT_SECONDS = 6;
    private const CONNECT_TIMEOUT_SECONDS = 3;

    public function __construct(string $projectRoot)
    {
        $this->apiKey = self::loadEnvValue($projectRoot . '/.env', 'TRIAGE_GEMINI_API_KEY');
        $this->model = getenv('TRIAGE_GEMINI_MODEL') ?: 'gemini-flash-lite-latest';
    }

    public function isConfigured(): bool
    {
        // BUG FIX 2026-08-26: this only ever checked for an API key, never
        // whether the PHP build actually has the curl extension loaded. On a
        // PHP install without ext-curl (confirmed on the owner's local
        // machine - "Call to undefined function curl_init()"), classify()
        // would reach curl_init() and throw an uncaught \Error (undefined-
        // function calls are \Error, not \Exception, in PHP 7+ - nothing
        // downstream catches that), fatally killing the whole search.php
        // request instead of the "fails soft" behavior this class's own
        // docblock promises. Treating a missing curl extension as simply
        // "not configured" makes SearchEngine::evaluate() take the same
        // graceful local-only fallback path it already uses for a missing
        // API key, with zero other code changes needed.
        return !empty($this->apiKey) && extension_loaded('curl');
    }

    /** Reads exactly one KEY=VALUE line from a .env file - never logs the value, never touches other keys. */
    private static function loadEnvValue(string $envPath, string $key): ?string
    {
        $fromEnv = getenv($key);
        if ($fromEnv !== false && $fromEnv !== '') return $fromEnv;
        if (!is_readable($envPath)) return null;
        $lines = file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || str_starts_with($line, '#')) continue;
            if (!str_contains($line, '=')) continue;
            [$k, $v] = explode('=', $line, 2);
            if (trim($k) === $key) {
                $v = trim($v);
                return $v === '' ? null : $v;
            }
        }
        return null;
    }

    private function buildTemplatesContext(array $templates): array
    {
        $out = [];
        foreach ($templates as $t) {
            $out[] = [
                'template_id' => $t['id'],
                'insuff_category' => $t['insuff_category'],
                'reason_category' => $t['reason_category'],
                'reason_sub_type' => $t['scenario_label'] ?? $t['reason_sub_type'],
                'example_phrasing' => $t['optimized_text'],
                'needed_tags' => $t['needed_tags'],
            ];
        }
        return $out;
    }

    private function buildTagValuesContext(array $tagValues): array
    {
        $out = [];
        foreach ($tagValues as $tag => $meta) {
            if (!empty($meta['values']) && is_array($meta['values'])) {
                $out[$tag] = array_values($meta['values']);
            }
        }
        return $out;
    }

    private function responseSchema(): array
    {
        return [
            'type' => 'OBJECT',
            'properties' => [
                'template_id' => ['type' => 'STRING', 'description' => 'One of the given template_id values, or the literal string "no_match".'],
                'confidence' => ['type' => 'STRING', 'enum' => ['High', 'Medium', 'Low', 'None']],
                'reasoning' => ['type' => 'STRING', 'description' => 'One short sentence: why this template (or no_match).'],
                'extracted_tags' => [
                    'type' => 'ARRAY',
                    'items' => [
                        'type' => 'OBJECT',
                        'properties' => [
                            'tag' => ['type' => 'STRING'],
                            'raw_value' => ['type' => 'STRING', 'description' => 'The value as it appears/implied in the query.'],
                            'matched_dropdown_value' => ['type' => 'STRING', 'description' => 'The closest value from that tag\'s allowed value list, if one was provided and a real match exists; omit otherwise.'],
                        ],
                        'required' => ['tag', 'raw_value'],
                    ],
                ],
                'suggested_documents' => [
                    'type' => 'ARRAY',
                    'items' => ['type' => 'STRING'],
                    'description' => 'Only when the chosen template needs DOCUMENTS: the atomic document name(s) implied by the query, from the DOCUMENTS value list given.',
                ],
            ],
            'required' => ['template_id', 'confidence', 'reasoning'],
        ];
    }

    private function buildPrompt(string $query, array $templatesCtx, array $tagValuesCtx): string
    {
        // Compact (not pretty-printed) - this is model input, not something a
        // human reads, and pretty-printing roughly doubles the character
        // count via indentation whitespace for zero benefit. Every token here
        // adds to request upload time and the model's processing time, both
        // of which are exactly what the owner asked to speed up.
        $templatesJson = json_encode($templatesCtx);
        $tagValuesJson = json_encode($tagValuesCtx);
        return <<<PROMPT
You are classifying one real insufficiency-verification comment against a fixed set of Education-department comment templates, for a background-verification company (AuthBridge).

A local keyword-overlap search already ran and could not confidently resolve this comment (either no template scored well, or two+ templates scored too close together to trust). Your job: read the comment's actual MEANING and pick the single best-fitting template - do not just match shared words. Common failure mode to avoid: a comment mentioning "TAT" or "extension" is about the TAT Approval category even if it shares no words with any Document/Information template; a comment about "cost" or "approve the additional charge" is about Cost Approval even if phrased very differently from the stored example text.

The candidate templates (id, category, reason, an example of how it phrases, and which tag fields it needs):
$templatesJson

Allowed values for tags that have a fixed dropdown (map extracted values to the closest one of these if applicable; if a tag isn't listed here, it's free text - just extract the raw value):
$tagValuesJson

The actual comment to classify:
"$query"

Return the single best-matching template_id (or "no_match" if truly nothing fits), your confidence, a one-sentence reason, and every tag value you can extract from the comment text itself (never invent a value that isn't implied by the comment).
PROMPT;
    }

    /**
     * @return array|null Decoded response ['template_id'=>..., 'confidence'=>..., 'reasoning'=>..., 'extracted_tags'=>[...], 'suggested_documents'=>[...]] or null on any failure.
     */
    public function classify(string $query, array $templates, array $tagValues): ?array
    {
        if (!$this->isConfigured()) return null;

        // BUG FIX 2026-08-26: everything below used to run unguarded. The
        // isConfigured() fix above is the real fix for the missing-curl
        // case specifically, but this try/catch is added as defense in
        // depth so ANY unexpected \Throwable here (a future PHP version
        // removing another function this relies on, an out-of-memory error
        // building the prompt for a huge templates array, etc.) degrades to
        // the documented "fails soft, return null" contract instead of
        // fatally killing the interactive search.php request it's called
        // from - this method having zero try/catch was the root cause of
        // "Support triage is not working" (an uncaught curl_init() \Error
        // took the whole request down instead of falling back to the local
        // match with a "Gemini unavailable" note).
        try {
            $prompt = $this->buildPrompt($query, $this->buildTemplatesContext($templates), $this->buildTagValuesContext($tagValues));

            $payload = [
                'contents' => [['parts' => [['text' => $prompt]]]],
                'generationConfig' => [
                    'temperature' => 0,
                    'responseMimeType' => 'application/json',
                    'responseSchema' => $this->responseSchema(),
                ],
            ];

            $url = "https://generativelanguage.googleapis.com/v1beta/models/{$this->model}:generateContent?key={$this->apiKey}";

            $ch = curl_init($url);
            curl_setopt_array($ch, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_POST => true,
                CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
                CURLOPT_POSTFIELDS => json_encode($payload),
                CURLOPT_TIMEOUT => self::TIMEOUT_SECONDS,
                CURLOPT_CONNECTTIMEOUT => self::CONNECT_TIMEOUT_SECONDS,
            ]);
            $raw = curl_exec($ch);
            $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            $curlErr = curl_error($ch);
            curl_close($ch);

            if ($raw === false || $curlErr !== '' || $httpCode !== 200) {
                return null;
            }

            $body = json_decode($raw, true);
            $text = $body['candidates'][0]['content']['parts'][0]['text'] ?? null;
            if ($text === null) return null;

            $parsed = json_decode($text, true);
            if (!is_array($parsed) || empty($parsed['template_id'])) return null;

            $parsed['extracted_tags'] = $parsed['extracted_tags'] ?? [];
            $parsed['suggested_documents'] = $parsed['suggested_documents'] ?? [];
            return $parsed;
        } catch (\Throwable $e) {
            return null;
        }
    }
}
