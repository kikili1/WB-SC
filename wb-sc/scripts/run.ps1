$ErrorActionPreference = 'Stop'
try {
    $hookScript = Join-Path $PSScriptRoot 'status_hook.py'
    $python = Get-ChildItem -Path "$env:USERPROFILE/.workbuddy/binaries/python/versions/*/python.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $reader = [System.IO.StreamReader]::new([Console]::OpenStandardInput(), [System.Text.Encoding]::UTF8)
    try { $payload = $reader.ReadToEnd() } finally { $reader.Dispose() }
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    if ($python) {
        $payload | & $python.FullName -B $hookScript
    } else {
        $payload | & py -3 -B $hookScript
    }
} catch {
    [Console]::Error.WriteLine("WorkBuddy LED hook: " + $_.Exception.Message)
}
exit 0
