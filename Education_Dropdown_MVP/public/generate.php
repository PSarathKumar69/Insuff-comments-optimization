<?php
header('Content-Type: application/json');
require_once __DIR__ . '/../php/CommentEngine.php';

$input = json_decode(file_get_contents('php://input'), true);
if (!is_array($input)) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid JSON body']);
    exit;
}

$engine = new CommentEngine(__DIR__ . '/../data');
$result = $engine->generate($input);

if (isset($result['error'])) {
    http_response_code(422);
}
echo json_encode($result);
