<?php
/**
 * Local-development router for PHP's built-in server ONLY. Not used by Vercel,
 * not part of the app.
 *
 * Vercel serves public/ as the site root (vercel.json "outputDirectory") and
 * api/*.php as serverless functions mounted at /api/*. PHP's built-in server has
 * a single document root, so with -t public it cannot see ../api at all. This
 * router bridges that one gap, so /api/data.php means the same thing in both
 * environments and public/app.js needs no environment switch.
 *
 *   php -S localhost:8000 -t public router.php
 */
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

if (preg_match('#^/api/([A-Za-z0-9_-]+\.php)$#', $path, $m)) {
    $target = __DIR__ . '/api/' . $m[1];
    if (is_file($target)) {
        require $target;
        return true;
    }
    http_response_code(404);
    header('Content-Type: application/json');
    echo json_encode(['error' => "No such endpoint: {$path}"]);
    return true;
}

// Any other *.php request that doesn't resolve to a real file: 404 it explicitly.
// Added 2026-08-27 (task #118): PHP's built-in server otherwise falls back to the
// document root's index file and answers with index.html and HTTP 200. That is how
// a stale cached app.js requesting the pre-move /data.php came back as a 200 full of
// HTML, which the frontend then tried to JSON.parse - a silent dead page rather than
// a visible failure. Fail honestly instead.
if (preg_match('#\.php$#', $path)) {
    http_response_code(404);
    header('Content-Type: application/json');
    echo json_encode([
        'error' => "No such endpoint: {$path}",
        'hint'  => 'The three endpoints live at /api/data.php, /api/generate.php and /api/search.php. If you are seeing this for a path without /api/, your browser is running a cached copy of app.js from before they moved - hard-reload the page.',
    ]);
    return true;
}

// Anything else: let the built-in server serve it from public/ as usual.
return false;
