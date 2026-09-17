# Script cài đặt ODBC Driver 17 for SQL Server
# Chạy với quyền Admin

Write-Host "Checking for ODBC Driver 17 for SQL Server..." -ForegroundColor Cyan

# Kiểm tra driver đã cài chưa
$driverName = "ODBC Driver 17 for SQL Server"
$driverCheck = Get-OdbcDriver -Name $driverName -ErrorAction SilentlyContinue

if ($driverCheck) {
    Write-Host "[OK] ODBC Driver 17 already installed!" -ForegroundColor Green
    exit 0
}

Write-Host "[INFO] ODBC Driver 17 not found. Installing..." -ForegroundColor Yellow

# Download driver (nếu cần)
$tempDir = [System.IO.Path]::GetTempPath()
$installerUrl = "https://go.microsoft.com/fwlink/?LinkId=2257008"
$installerPath = Join-Path $tempDir "msodbc17.msi"

Write-Host "Downloading ODBC Driver 17..." -ForegroundColor Cyan
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -ErrorAction Stop
    Write-Host "[OK] Download complete" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Download failed: $_" -ForegroundColor Red
    exit 1
}

# Cài driver
Write-Host "Installing ODBC Driver 17..." -ForegroundColor Cyan
try {
    Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$installerPath`" /qn /norestart" -NoNewWindow -Wait
    Write-Host "[OK] Installation complete!" -ForegroundColor Green

    # Cleanup
    Remove-Item -Path $installerPath -ErrorAction SilentlyContinue

    exit 0
} catch {
    Write-Host "[ERROR] Installation failed: $_" -ForegroundColor Red
    exit 1
}
