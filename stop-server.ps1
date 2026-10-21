$procs = Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
  Where-Object { $_.CommandLine -and $_.CommandLine -match 'server\.py' }

if (-not $procs) {
  Write-Host "没有在跑的本周菜单服务。" -ForegroundColor Yellow
  exit 0
}

foreach ($p in $procs) {
  Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host ("已停止服务 " + $p.ProcessId) -ForegroundColor Green
}
