$envPath = "D:\StudyAI\.env"
$lines = Get-Content $envPath
$pgPassword = ""
$pgUser = ""
foreach ($line in $lines) {
    if ($line -match "^POSTGRES_PASSWORD=(.+)$") { $pgPassword = $Matches[1] }
    if ($line -match "^POSTGRES_USER=(.+)$") { $pgUser = $Matches[1] }
}
Write-Host "User: $pgUser"
Write-Host "Password length: $($pgPassword.Length)"
$env:PGPASSWORD = $pgPassword
docker compose exec db psql -U $pgUser -c "SELECT 1;"
