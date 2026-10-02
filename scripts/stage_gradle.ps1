param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$main = Join-Path $ProjectRoot 'app\src\main'
if (-not (Test-Path (Join-Path $ProjectRoot 'app\build.gradle'))) {
    throw "Briefcase Gradle project is missing: $ProjectRoot"
}
$javaDestination = Join-Path $main 'java\com\muselite\python'
$assetDestination = Join-Path $main 'assets'
$nativeDestination = Join-Path $main 'jniLibs\arm64-v8a'
$xmlDestination = Join-Path $main 'res\xml'
$pythonDestination = Join-Path $main 'python'
$pythonAppDestination = Join-Path $pythonDestination 'muselite_py'
$pythonPackageDestination = Join-Path $pythonDestination 'python'
$oldJavaDestination = Join-Path $main 'java\com\openminis'
$oldPythonDestination = Join-Path $pythonDestination 'openminis_py'
$expected = @{
    'vendor\assets\alpine-minirootfs.tar' = '5651126278f52f292d342794ee0c270c2d35e1859f70c06c65497986578115cf'
    'vendor\native_libs\arm64-v8a\libproot.so' = 'f6b0381ab9a066fa620fef0001737fd3cfaf9d22474f013ac48d7861411374ac'
    'vendor\native_libs\arm64-v8a\libproot-loader.so' = '44ef39c1e1a18c09f6e4c4b5d6f8bba82d30596598bd155ec162d05c5122ff04'
    'vendor\native_libs\arm64-v8a\libproot-loader32.so' = '25f6bd90bc5a3d3088026289a0d3eaf3e502bd2b00e5cb74fadd9791132efa34'
}
foreach ($item in $expected.GetEnumerator()) {
    $path = Join-Path $source $item.Key
    if (-not (Test-Path $path)) { throw "Missing Android resource: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value) {
        throw "Android resource checksum mismatch: $path"
    }
}
New-Item -ItemType Directory -Force $javaDestination,$assetDestination,$nativeDestination,$xmlDestination,
    $pythonAppDestination,$pythonPackageDestination | Out-Null
if (Test-Path $oldJavaDestination) { Remove-Item -LiteralPath $oldJavaDestination -Recurse -Force }
if (Test-Path $oldPythonDestination) { Remove-Item -LiteralPath $oldPythonDestination -Recurse -Force }
Copy-Item (Join-Path $source 'java\com\muselite\python\*.java') $javaDestination -Force
Copy-Item (Join-Path $source 'src\muselite_py\*.py') $pythonAppDestination -Force
Copy-Item (Join-Path $source 'src\python\*.py') $pythonPackageDestination -Force
Copy-Item (Join-Path $source 'res\xml\phone_accessibility.xml') $xmlDestination -Force
Copy-Item (Join-Path $source 'vendor\assets\alpine-minirootfs.tar') $assetDestination -Force
Copy-Item (Join-Path $source 'vendor\native_libs\arm64-v8a\*.so') $nativeDestination -Force
$appGradle = Join-Path $ProjectRoot 'app\build.gradle'
$manifest = Join-Path $main 'AndroidManifest.xml'
$manifestText = Get-Content $manifest -Raw
if (-not $manifestText.Contains('PhoneAccessibilityService')) {
    $permissions = @'
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />
    <queries><intent><action android:name="android.intent.action.MAIN" /><category android:name="android.intent.category.LAUNCHER" /></intent></queries>
'@
    $services = @'
        <service android:name="com.muselite.python.PhoneAccessibilityService" android:exported="true" android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE">
            <intent-filter><action android:name="android.accessibilityservice.AccessibilityService" /></intent-filter>
            <meta-data android:name="android.accessibilityservice" android:resource="@xml/phone_accessibility" />
        </service>
        <service android:name="com.muselite.python.PhoneTaskService" android:exported="false" android:foregroundServiceType="specialUse">
            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" android:value="User initiated accessibility agent task" />
        </service>
        <receiver android:name="com.muselite.python.SessionAlarmReceiver" android:exported="false" />
'@
    $manifestText = $manifestText.Replace('<application', $permissions + "`n    <application")
    $manifestText = $manifestText.Replace('</application>', $services + "`n    </application>")
    Set-Content -Path $manifest -Value $manifestText -Encoding utf8
}
$strings = Join-Path $main 'res\values\strings.xml'
$stringsText = Get-Content $strings -Raw
$description = '    <string name="phone_accessibility_description">Allow MuseLite to read the screen and perform taps, typing, and swipes when enabled by the user.</string>'
if ($stringsText.Contains('phone_accessibility_description')) {
    $stringsText = [regex]::Replace($stringsText, '(?m)^\s*<string name="phone_accessibility_description">[^\r\n]*', $description)
} else {
    $stringsText = $stringsText.Replace('</resources>', $description + "`n</resources>")
}
[System.IO.File]::WriteAllText($strings, $stringsText, (New-Object System.Text.UTF8Encoding $false))
$colors = Join-Path $main 'res\values\colors.xml'
$colorText = Get-Content $colors -Raw
$palette = @{
    colorPrimary = '#DCEBFF'
    colorPrimaryDark = '#F8FAFF'
    colorAccent = '#9EACE0'
    colorSplashScreenBackground = '#F8FAFF'
}
foreach ($entry in $palette.GetEnumerator()) {
    $pattern = '(<color name="' + $entry.Key + '">)[^<]*(</color>)'
    $colorText = [regex]::Replace($colorText, $pattern,
        ('$1' + $entry.Value + '$2'))
}
[System.IO.File]::WriteAllText($colors, $colorText, (New-Object System.Text.UTF8Encoding $false))
$gradleText = Get-Content $appGradle -Raw
$gradleText = $gradleText -replace 'minSdkVersion\s+\d+', 'minSdkVersion 30'
$metadata = Get-Content (Join-Path $source 'pyproject.toml') -Raw
$versionMatch = [regex]::Match($metadata, '(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"')
if (-not $versionMatch.Success) { throw 'pyproject.toml must contain a numeric app version' }
$appVersion = '{0}.{1}.{2}' -f $versionMatch.Groups[1].Value,
    $versionMatch.Groups[2].Value, $versionMatch.Groups[3].Value
$versionCode = [int]$versionMatch.Groups[1].Value * 1000000 +
    [int]$versionMatch.Groups[2].Value * 10000 + [int]$versionMatch.Groups[3].Value
$gradleText = $gradleText -replace 'versionCode\s+\d+', "versionCode $versionCode"
$gradleText = $gradleText -replace 'versionName\s+"[^"]+"', "versionName `"$appVersion`""
$proxyDeclaration = 'chaquopy.defaultConfig.staticProxy("toga_android.widgets.internal.webview")'
if (-not $gradleText.Contains($proxyDeclaration)) {
    $gradleText += "`n" + $proxyDeclaration + "`n"
}
$gradleText = $gradleText -replace "com\.openminis", "com.muselite"
[System.IO.File]::WriteAllText($appGradle, $gradleText, (New-Object System.Text.UTF8Encoding $false))
Write-Host "Android Java, Alpine and PRoot staged in $ProjectRoot"
