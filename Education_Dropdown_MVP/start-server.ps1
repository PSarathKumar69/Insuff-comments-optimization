$env:Path = "C:\php;$env:Path"
Set-Location $PSScriptRoot
php -S localhost:8000 -t public
