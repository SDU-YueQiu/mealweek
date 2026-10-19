param(
  [string]$IP = "192.168.1.10",
  [int]$Years = 5
)

# Generates a local CA + a server cert for $IP / 127.0.0.1 / localhost.
# Output: rootCA.pem, server.pem, server-key.pem in this folder.
# No external tools needed (works offline).

$ErrorActionPreference = "Stop"
$out = $PSScriptRoot

function To-Pem([byte[]]$bytes, [string]$label) {
  $b64 = [Convert]::ToBase64String($bytes, [Base64FormattingOptions]::InsertLineBreaks)
  return "-----BEGIN $label-----`n$b64`n-----END $label-----`n"
}

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

Write-Host "creating server cert for $IP ..."
$srv = New-SelfSignedCertificate `
  -Type Custom `
  -Subject "CN=$IP" `
  -TextExtension @("2.5.29.17={text}DNS=localhost&IPAddress=$IP&IPAddress=127.0.0.1") `
  -KeySpec KeyExchange `
  -KeyExportPolicy Exportable `
  -KeyLength 2048 `
  -HashAlgorithm SHA256 `
  -Signer $ca `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears($Years)

$caPem = To-Pem $ca.RawData "CERTIFICATE"
$srvPem = To-Pem $srv.RawData "CERTIFICATE"

$rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($srv)
$pkcs8 = $rsa.ExportPkcs8PrivateKey()
$keyPem = To-Pem $pkcs8 "PRIVATE KEY"

Set-Content -Path (Join-Path $out "rootCA.pem") -Value $caPem -Encoding ascii -NoNewline
Set-Content -Path (Join-Path $out "server.pem") -Value $srvPem -Encoding ascii -NoNewline
Set-Content -Path (Join-Path $out "server-key.pem") -Value $keyPem -Encoding ascii -NoNewline

# DER copy for Android's certificate installer
[System.IO.File]::WriteAllBytes((Join-Path $out "rootCA.crt"), $ca.RawData)

# Trust the CA for this Windows user so Edge/Chrome accept it
try {
  Import-Certificate -FilePath (Join-Path $out "rootCA.crt") -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
  Write-Host "CA installed into CurrentUser\Root"
} catch {
  Write-Host "CA install skipped: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "done:"
Write-Host "  rootCA.pem / rootCA.crt   -> install on the phone as a CA certificate"
Write-Host "  server.pem / server-key.pem -> server.py --cert/--key"
Write-Host "  SAN: $IP, 127.0.0.1, localhost"
