<?php
header('Content-Type: application/json');
require_once __DIR__ . '/../php/SearchEngine.php';

// Redesigned 2026-08-15: returns a single Supported/Not-supported verdict +
// step-by-step dropdown guide (see SearchEngine::evaluate()), not a ranked
// list of similar historical comments.
$q = trim($_GET['q'] ?? '');
if ($q === '') {
    echo json_encode(['query' => '', 'supported' => null, 'verdict_label' => '', 'verdict_reason' => '', 'steps' => []]);
    exit;
}

$engine = new SearchEngine(__DIR__ . '/../data');
echo json_encode($engine->evaluate($q));
