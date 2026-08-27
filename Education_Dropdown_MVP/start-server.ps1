# Local dev server. router.php maps /api/*.php to ../api/ so the URLs match
# what Vercel serves (see router.php and vercel.json).
php -S localhost:8000 -t public router.php
