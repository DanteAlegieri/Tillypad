# Заполните IP VPS и выполните этот файл.

$VpsIp = "5.8.53.75"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File "$PSScriptRoot\deploy_vps.ps1" `
    -VpsHost $VpsIp `
    -VpsUser "root" `
    -RemotePath "/opt/restaurantos/gateway" `
    -ExpectedVersion "10.4.4"
