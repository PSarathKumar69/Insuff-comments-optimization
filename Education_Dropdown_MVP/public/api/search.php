<?php
/**
 * Local-development shim. Not deployed - .vercelignore excludes public/api/ so
 * Vercel serves /api/search.php from the real serverless function in ../../api/.
 *
 * Why this exists (2026-08-27, task #121): the endpoints live outside the static
 * root so Vercel cannot hand out their source. That left the local server needing
 * a router argument (php -S ... -t public router.php) to reach them, and a server
 * started without it answers /api/search.php with index.html and HTTP 200 - blanking
 * every dropdown with no clue why. That mistake blocked three consecutive rounds
 * of debugging. This one line makes the plain, obvious command work too:
 *
 *   php -S localhost:8000 -t public
 *
 * Keep it a pure require of the real endpoint - no logic here, ever.
 */
require __DIR__ . '/../../api/search.php';
