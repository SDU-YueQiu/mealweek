param(
  [int]$Port = 8765,
  [string]$Cert = "",
  [string]$Key = "",
  [int]$AlsoHttp = 0,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
  Write-Host "找不到 python，请先装 Python 3 并加入 PATH。" -ForegroundColor Red
  exit 1
}

$scheme = if ($Cert -and $Key) { "https" } else { "http" }
$url = "${scheme}://127.0.0.1:${Port}/"

# A hidden copy may already be serving (see start-bg.bat).  Do not die with an
# address-in-use traceback — point the browser at the running one instead.
$busy = $false
try {
  $busy = [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop)
} catch { $busy = $false }
if ($busy) {
  Write-Host ""
  Write-Host "  本周菜单" -ForegroundColor DarkYellow
  Write-Host "  ${Port} 端口已经有一个服务在跑了，直接用：" -ForegroundColor Green
  Write-Host "  电脑  ${url}"
  Write-Host "  手机  ${scheme}://<本机IP>:${Port}/"
  Write-Host "  要重启就先运行 stop-server.bat，再双击一次。" -ForegroundColor Yellow
  Write-Host ""
  if (-not $NoBrowser) { Start-Process $url | Out-Null }
  exit 0
}

if (-not $NoBrowser) {
  Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-Command", "Start-Sleep -Seconds 2; Start-Process '${url}'"
  ) | Out-Null
}

$serverArgs = @("-u", "server.py", "$Port")
if ($Cert) { $serverArgs += @("--cert", $Cert) }
if ($Key) { $serverArgs += @("--key", $Key) }
if ($AlsoHttp -gt 0) { $serverArgs += @("--also-http", "$AlsoHttp") }

Write-Host ""
Write-Host "  本周菜单" -ForegroundColor DarkYellow
Write-Host "  电脑  ${url}"
if ($AlsoHttp -gt 0) {
  Write-Host "  手机  先开 http://<本机IP>:${AlsoHttp}/setup 装证书，再开 https://<本机IP>:${Port}/"
} else {
  Write-Host "  手机  同一 wifi 打开终端里打印的 http://192.168.x.x:${Port}/"
}
Write-Host "  离线  ${scheme}://<本机IP>:${Port}/offline.html  （下载单文件包，关电脑也能用）"
if ($scheme -eq "http") {
  Write-Host "  注意  HTTP 下手机不能装成离线 App；请用离线包，或运行 start-https.bat。" -ForegroundColor Yellow
}
Write-Host "  停止  Ctrl+C"
Write-Host ""

& $py @serverArgs
