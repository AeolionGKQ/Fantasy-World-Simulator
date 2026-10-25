<#
Build the Android APK: web assets -> Capacitor sync -> Gradle -> signature check -> dist\.

  .\build-apk.ps1            release APK, signed with the key named in keystore.properties
  .\build-apk.ps1 -Debug     debug APK (installable next to nothing else: different signature)
  .\build-apk.ps1 -Install   also install it on the phone connected over USB

Tools default to D:\Android (JDK 21, Android SDK, Python 3.14); override with FANTASY_JDK and
ANDROID_HOME. JDK 21 is used even when JAVA_HOME points elsewhere: Gradle 8.14 cannot run on a
newer JDK ("Unsupported class file major version"). Gradle runs with a short TEMP folder: on this machine the default user TEMP makes
the Gradle daemon fail with "Unable to establish loopback connection".
#>
param([switch]$Debug, [switch]$Install)
$ErrorActionPreference = "Stop"
$android = $PSScriptRoot
$web = Join-Path $android "..\apps\web"
$env:JAVA_HOME = if ($env:FANTASY_JDK) { $env:FANTASY_JDK } else { "D:\Android\jdk-21" }
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = "D:\Android\Sdk" }
$shortTemp = "D:\Android\tmp"
New-Item -ItemType Directory -Force $shortTemp | Out-Null
$env:TEMP = $shortTemp; $env:TMP = $shortTemp

function Step($name, [scriptblock]$block) {
  Write-Host "==> $name"
  & $block
  if ($LASTEXITCODE -ne 0) { throw "$name failed (exit $LASTEXITCODE)" }
}

Push-Location $web
try {
  # Its own output folder: apps/web/dist is the desktop build that main tracks in git.
  Step "Type check" { npx tsc -b }
  Step "Web build" { npx vite build --outDir dist-android --emptyOutDir }
  Step "Capacitor sync" { npx cap sync android }
} finally { Pop-Location }

$variant = if ($Debug) { "debug" } else { "release" }
if (-not $Debug -and -not (Test-Path (Join-Path $android "keystore.properties"))) {
  throw "keystore.properties is missing: a release APK cannot be signed (see android\SYNC.md)."
}
Push-Location $android
try {
  Step "Gradle assemble $variant" { .\gradlew.bat ("assemble" + (Get-Culture).TextInfo.ToTitleCase($variant)) --console=plain }
} finally { Pop-Location }

$apk = Join-Path $android "app\build\outputs\apk\$variant\app-$variant.apk"
$buildTools = Get-ChildItem (Join-Path $env:ANDROID_HOME "build-tools") | Sort-Object Name | Select-Object -Last 1
Step "Signature check" { & (Join-Path $buildTools.FullName "apksigner.bat") verify --print-certs $apk }

$version = (Get-Content (Join-Path $web "package.json") -Raw | ConvertFrom-Json).version
$dist = Join-Path $android "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$suffix = if ($Debug) { "-debug" } else { "" }
$target = Join-Path $dist "FantasySimulator-v$version-android$suffix.apk"
Copy-Item $apk $target -Force
$hash = (Get-FileHash $target -Algorithm SHA256).Hash.ToLower()
"{0}  {1}" -f $hash, (Split-Path $target -Leaf) | Set-Content "$target.sha256" -Encoding ascii
Write-Host ("==> {0} ({1:N1} MB)`n    SHA-256 {2}" -f $target, ((Get-Item $target).Length / 1MB), $hash)

if ($Install) {
  Step "Install on phone" { & (Join-Path $env:ANDROID_HOME "platform-tools\adb.exe") install -r $target }
}
