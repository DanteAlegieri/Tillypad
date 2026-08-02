$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    throw "Python не найден"
}

& $Python -m pip install -r requirements.txt
& $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8020
