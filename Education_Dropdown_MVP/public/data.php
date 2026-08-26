<?php
/**
 * Single read-only endpoint that bundles dropdown_tree.json + templates.json +
 * tag_values.json for the frontend to bootstrap itself. Kept as one call to
 * avoid 3 round trips in the prototype; Bridge's team can split these however
 * their frontend build prefers.
 */
header('Content-Type: application/json');
$dir = __DIR__ . '/../data';
echo json_encode([
    'dropdown_tree' => json_decode(file_get_contents($dir . '/dropdown_tree.json'), true),
    'templates' => json_decode(file_get_contents($dir . '/templates.json'), true),
    'tag_values' => json_decode(file_get_contents($dir . '/tag_values.json'), true),
]);
