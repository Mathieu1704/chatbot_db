# start_dev.ps1

# —————————————————————————————
# 1) Variables à adapter si besoin
# —————————————————————————————
# Chemin vers ta clé SSH
$sshKey     = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
# Utilisateur et hôte SSH
$sshUser    = "mzilli"
$sshHost    = "isee-srv03.test.internal"
# Hôte MongoDB (un shard explicite)
$remoteHost = "mongotest6-shard-00-00.yjqzz.mongodb.net"
$remotePort = 27017
# Port local du tunnel
$localPort  = 27018

# Le dossier du script, pour lancer uvicorn & npm au bon endroit
$scriptDir = $PSScriptRoot
$frontendDir = Join-Path $scriptDir "frontend" 

# —————————————————————————————
# 2) Ouvre le tunnel SSH dans une nouvelle fenêtre
# —————————————————————————————
Write-Host "Opening SSH tunnel (localhost:${localPort} -> ${remoteHost}:${remotePort})..."
Start-Process powershell `
  -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-Command",
    "ssh -i `"$sshKey`" -p 22 -L $localPort`:$remoteHost`:$remotePort $sshUser@$sshHost -N"
  )

# —————————————————————————————
# 3) Attendre que le tunnel soit prêt
# —————————————————————————————
Write-Host "Waiting for SSH tunnel to be ready..."
while (-not (Test-NetConnection -ComputerName 'localhost' -Port $localPort -WarningAction SilentlyContinue).TcpTestSucceeded) {
    Start-Sleep -Seconds 1
}
Write-Host "SSH tunnel established."

# —————————————————————————————
# 4) Lancement de l’API Uvicorn dans une nouvelle fenêtre
# —————————————————————————————
Write-Host "Starting Uvicorn server..."
Start-Process powershell `
  -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-Command",
    "Set-Location -Path `"$scriptDir`"; uvicorn app.main:app --reload --env-file .env --host 127.0.0.1 --port 8000"
  )

# —————————————————————————————
# 5) Lancement du front-end (npm run dev) dans une nouvelle fenêtre
# —————————————————————————————
Write-Host "Starting frontend (npm run dev)..."
Start-Process powershell `
  -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-Command",
    "Set-Location -Path `"$frontendDir`"; npm install; npm run dev"
  )
