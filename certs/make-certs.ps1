param(
  [string[]]$IP = @(),
  [int]$Years = 5,
  [switch]$NewCA,
  [switch]$Ensure
)

# Issues (or re-issues) the server certificate for this machine.
#
#   powershell -File certs\make-certs.ps1 -IP 192.168.1.9,192.168.1.7
#   powershell -File certs\make-certs.ps1 -Ensure        # add the current LAN IPs automatically
#   powershell -File certs\make-certs.ps1 -NewCA         # start over with a fresh CA
#
# The CA is reused when certs\rootCA.pem already exists, so the phone only has
# to install it once — a new IP just re-signs the server cert.
# Output: rootCA.pem, rootCA.crt, server.pem, server-key.pem in this folder.

$ErrorActionPreference = "Stop"
$out = $PSScriptRoot
$caPemPath = Join-Path $out "rootCA.pem"
$srvPemPath = Join-Path $out "server.pem"

function To-Pem([byte[]]$bytes, [string]$label) {
  $b64 = [Convert]::ToBase64String($bytes, [Base64FormattingOptions]::InsertLineBreaks)
  return "-----BEGIN $label-----`n$b64`n-----END $label-----`n"
}

function From-Pem([string]$path) {
  if (-not (Test-Path $path)) { return $null }
  $b64 = ((Get-Content $path -Raw) -replace "-----[^-]+-----", "" -replace "\s", "")
  return New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, [Convert]::FromBase64String($b64))
}

# LAN IPs this machine currently has (skip loopback / link-local / WSL).
function Get-LanIPs {
  Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
      $_.IPAddress -notlike "127.*" -and
      $_.IPAddress -notlike "169.254.*" -and
      $_.IPAddress -notlike "172.19.*"
    } |
    ForEach-Object { $_.IPAddress }
}

# -File 传进来的 "a,b" 是一整个字符串，这里拆回数组。
$IP = @($IP | ForEach-Object { $_ -split "," } | Where-Object { $_ })

if ($Ensure) {
  if (-not $IP -or $IP.Count -eq 0) { $IP = @(Get-LanIPs) }
  $cur = From-Pem $srvPemPath
  if ($cur) {
    $san = ($cur.Extensions | Where-Object { $_.Oid.Value -eq "2.5.29.17" })
    $text = if ($san) { $san.Format($false) } else { "" }
    $missing = @($IP | Where-Object { $text -notmatch [regex]::Escape($_) })
    if ($missing.Count -eq 0) {
      Write-Host "证书已覆盖当前 IP（$($IP -join ', ')），不用重新签。"
      exit 0
    }
    Write-Host "证书里缺少：$($missing -join ', ') —— 重新签一张（CA 不变）。"
  }
}

$want = @("127.0.0.1", "localhost") + @($IP | Where-Object { $_ })

# Reuse the CA on disk unless asked for a new one.
$ca = $null
if (-not $NewCA) {
  $disk = From-Pem $caPemPath
  if ($disk) {
    $ca = Get-ChildItem Cert:\CurrentUser\My |
      Where-Object { $_.Thumbprint -eq $disk.Thumbprint -and $_.HasPrivateKey } |
      Select-Object -First 1
    if (-not $ca) {
      throw "certs\rootCA.pem 对应的 CA 私钥不在 CurrentUser\My 里，跑一次 -NewCA 重建。"
    }
  }
}

if (-not $ca) {
  Write-Host "creating CA..."
  $ca = New-SelfSignedCertificate `
    -Type Custom `
    -Subject "CN=Meal Week Local CA" `
    -KeySpec Signature `
    -KeyExportPolicy Exportable `
    -KeyUsage CertSign, CRLSign, DigitalSignature `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears($Years) `
    -TextExtension @("2.5.29.19={critical}{text}ca=1&pathlength=1")
  Set-Content -Path $caPemPath -Value (To-Pem $ca.RawData "CERTIFICATE") -Encoding ascii -NoNewline
  [System.IO.File]::WriteAllBytes((Join-Path $out "rootCA.crt"), $ca.RawData)
  try {
    Import-Certificate -FilePath (Join-Path $out "rootCA.crt") -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    Write-Host "CA installed into CurrentUser\Root"
  } catch {
    Write-Host "CA install skipped: $($_.Exception.Message)"
  }
  Write-Host "  -> 手机上要装一次 certs\rootCA.crt（或 http://<IP>:8765/ca.crt）"
} else {
  Write-Host "reusing CA $($ca.Thumbprint)"
}

$sanParts = @()
foreach ($h in $want) {
  if ($h -match "^\d+\.\d+\.\d+\.\d+$") { $sanParts += "IPAddress=$h" } else { $sanParts += "DNS=$h" }
}
$sanExt = "2.5.29.17={text}" + ($sanParts -join "&")

Write-Host "issuing server cert for: $($want -join ', ')"
$srv = New-SelfSignedCertificate `
  -Type Custom `
  -Subject "CN=$($want[$want.Count - 1])" `
  -TextExtension @($sanExt) `
  -KeySpec KeyExchange `
  -KeyExportPolicy Exportable `
  -KeyLength 2048 `
  -HashAlgorithm SHA256 `
  -Signer $ca `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears($Years)

$rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($srv)
# PowerShell 5.1 的 .NET Framework 没有 ExportPkcs8PrivateKey，走 CNG blob。
if ($rsa.PSObject.Methods.Name -contains "ExportPkcs8PrivateKey") {
  $pkcs8 = $rsa.ExportPkcs8PrivateKey()
} else {
  $pkcs8 = $rsa.Key.Export([System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob)
}
Set-Content -Path $srvPemPath -Value (To-Pem $srv.RawData "CERTIFICATE") -Encoding ascii -NoNewline
Set-Content -Path (Join-Path $out "server-key.pem") -Value (To-Pem $pkcs8 "PRIVATE KEY") -Encoding ascii -NoNewline

Write-Host ""
Write-Host "done:"
Write-Host "  server.pem / server-key.pem -> server.py --cert/--key"
Write-Host "  SAN: $($want -join ', ')"
Write-Host "  手机上打开 https://$($want[$want.Count - 1]):8443/"
