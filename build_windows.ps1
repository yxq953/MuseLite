$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot.TrimEnd('\')
$venvPython = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    python -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create Python virtual environment' }
    & $venvPython -m pip install 'briefcase==0.4.5' 'toga==0.5.6'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install Briefcase/Toga' }
}

$env:BRIEFCASE_HOME = Join-Path $project 'cache'
New-Item -ItemType Directory -Force $env:BRIEFCASE_HOME | Out-Null
$javaHome = Join-Path $env:BRIEFCASE_HOME 'tools\java17'
if (Test-Path (Join-Path $javaHome 'bin\java.exe')) { $env:JAVA_HOME = $javaHome }
$javaSocketTemp = Join-Path $project 'temp'
New-Item -ItemType Directory -Force $javaSocketTemp | Out-Null
if ($env:JAVA_TOOL_OPTIONS) { $env:JAVA_TOOL_OPTIONS += ' ' }
$env:JAVA_TOOL_OPTIONS += "-Djdk.net.unixdomain.tmpdir=$javaSocketTemp"

# Briefcase 0.4.5's automatic unzip hits MAX_PATH in this workspace. The
# official archive is verified, then extracted using Windows extended paths.
$tools = Join-Path $env:BRIEFCASE_HOME 'tools'
$sdk = Join-Path $tools 'android_sdk'
$sdkmanager = Join-Path $sdk 'cmdline-tools\19.0\bin\sdkmanager.bat'
if (-not (Test-Path $sdkmanager)) {
    New-Item -ItemType Directory -Force $tools | Out-Null
    $archive = Join-Path $tools 'commandlinetools-win-13114758_latest.zip'
    $sdkToolsHash = '98b565cb657b012dae6794cefc0f66ae1efb4690c699b78a614b4a6a3505b003'
    if ((Test-Path $archive) -and
        (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sdkToolsHash) {
        Remove-Item -LiteralPath $archive -Force
    }
    if (-not (Test-Path $archive)) {
        Invoke-WebRequest 'https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip' -OutFile $archive
    }
    & $venvPython (Join-Path $project 'scripts\unpack_sdk.py') $archive $sdk
    if ($LASTEXITCODE -ne 0) { throw 'Android SDK extraction failed' }
}

Push-Location $project
try {
    $gradle = Join-Path $project 'build\python\android\gradle'
    if (Test-Path (Join-Path $gradle 'app\build.gradle')) {
        & $venvPython -m briefcase update android --update-requirements
    } else {
        & $venvPython -m briefcase create android
    }
    if ($LASTEXITCODE -ne 0) { throw 'Briefcase create/update failed' }
    & (Join-Path $project 'scripts\stage_gradle.ps1') -ProjectRoot $gradle

    # PowerShell's HTTP client is reliable here; Gradle Wrapper's Java download
    # can stall after a partial response on this Windows network.
    $gradleZip = Join-Path $env:BRIEFCASE_HOME 'gradle-9.5.0-bin.zip'
    $gradleHash = '553c78f50dafcd54d65b9a444649057857469edf836431389695608536d6b746'
    if ((Test-Path $gradleZip) -and
        (Get-FileHash $gradleZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gradleHash) {
        Remove-Item -LiteralPath $gradleZip -Force
    }
    if (-not (Test-Path $gradleZip)) {
        Invoke-WebRequest 'https://services.gradle.org/distributions/gradle-9.5.0-bin.zip' -OutFile $gradleZip
    }
    if ((Get-FileHash $gradleZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gradleHash) {
        throw 'Gradle distribution checksum mismatch'
    }
    $wrapper = Join-Path $gradle 'gradle\wrapper\gradle-wrapper.properties'
    $url = 'file:///' + ($gradleZip.Replace('\','/'))
    $properties = Get-Content $wrapper
    $properties = $properties | ForEach-Object {
        if ($_ -like 'distributionUrl=*') { 'distributionUrl=' + $url } else { $_ }
    }
    $properties = $properties | Where-Object { $_ -notlike 'distributionSha256Sum=*' }
    $properties += 'distributionSha256Sum=' + $gradleHash
    Set-Content -Path $wrapper -Value $properties -Encoding ascii

    & $venvPython (Join-Path $project 'scripts\maven_proxy_build.py')
    if ($LASTEXITCODE -ne 0) { throw 'Briefcase build or package failed' }
    $apk = Get-ChildItem (Join-Path $project 'dist') -Filter '*.apk' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $apk) { throw 'Briefcase did not produce an APK' }
    & $venvPython (Join-Path $project 'scripts\verify_apk.py') $apk.FullName
    if ($LASTEXITCODE -ne 0) { throw 'APK content check failed' }
    $apk | Select-Object FullName,Length
} finally {
    Pop-Location
}
