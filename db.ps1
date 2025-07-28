# start_dev.ps1

# —————————————————————————————
# 1) Variables à adapter si besoin
# —————————————————————————————
$sshKey     = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$sshUser    = "mzilli"
$sshHost    = "isee-srv03.test.internal"
$remoteHost = "mongotest6-shard-00-00.yjqzz.mongodb.net"
$remotePort = 27017
$localPort  = 27018

$scriptDir   = $PSScriptRoot
$frontendDir = Join-Path $scriptDir "frontend"

# —————————————————————————————
# 2) Vérifie que wt.exe est dispo
# —————————————————————————————
if (-not (Get-Command wt.exe -ErrorAction SilentlyContinue)) {
    Write-Error "wt.exe introuvable. Assurez-vous que Windows Terminal est installé et que l'alias d'exécution 'wt' est activé."
    exit 1
}

# —————————————————————————————
# 3) Lance une seule Windows Terminal avec 3 onglets cmd.exe
# —————————————————————————————
# Onglet 1 : tunnel SSH
# Onglet 2 : API Uvicorn
# Onglet 3 : front-end npm

Start-Process wt.exe -ArgumentList @(
    # onglet 1 : tunnel SSH
    "cmd", "/k", "ssh -i `"$sshKey`" -p 22 -L ${localPort}:${remoteHost}:${remotePort} ${sshUser}@${sshHost} -N",
    ";",                       # sépare les onglets
    "new-tab", 
      "cmd", "/k", "cd /d `"$scriptDir`" && uvicorn app.main:app --reload --use-colors --env-file .env --host 127.0.0.1 --port 8000",
    ";",
    "new-tab",
      "cmd", "/k", "cd /d `"$frontendDir`" && npm install && npm run dev"
)
