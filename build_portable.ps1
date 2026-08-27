[CmdletBinding()]
param()

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)] [string]$FilePath,
        [Parameter(Mandatory = $true)] [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)] [string]$FailureMessage
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage（退出码：$LASTEXITCODE）"
    }
}

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "此脚本仅支持在 64 位 Windows 上构建。"
}
if (-not [System.Environment]::Is64BitOperatingSystem) {
    throw "不支持 32 位 Windows；请使用 64 位 Windows 构建。"
}
if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "请使用 Windows PowerShell 5.1 或 PowerShell 7。"
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionPath = Join-Path $ProjectRoot "VERSION"
if (-not (Test-Path -LiteralPath $VersionPath)) {
    throw "未找到 VERSION 文件。"
}
$AppVersion = (Get-Content -Raw -Encoding UTF8 -LiteralPath $VersionPath).Trim()
if ($AppVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION 必须使用 X.Y.Z 格式。"
}
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $ProjectRoot "FashionMallClient.spec"
$DistDirectory = Join-Path $ProjectRoot "dist"
$AppDirectory = Join-Path $DistDirectory "FashionMallAutomation"
$ExecutablePath = Join-Path $AppDirectory "FashionMallClient.exe"
$ReleaseDirectory = Join-Path $ProjectRoot "release"
$ArchiveName = "FashionMallAutomation-v$AppVersion-Windows-x64.zip"
$ArchivePath = Join-Path $ReleaseDirectory $ArchiveName
$ChecksumPath = Join-Path $ReleaseDirectory "FashionMallAutomation-v$AppVersion-Windows-x64.sha256"
$VersionedDocumentation = @(
    (Join-Path $ProjectRoot "README.md"),
    (Join-Path $ProjectRoot "使用说明.md"),
    (Join-Path $ProjectRoot "CHANGELOG.md")
)

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "未找到 .venv。请先在项目根目录创建 Python 3.13 虚拟环境。"
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "tests") -PathType Container)) {
    throw "缺少本机 tests 目录；发布构建不允许跳过单元测试。"
}

Write-Host "[1/8] 检查 Windows x64 构建环境..."
$PythonProbe = & $PythonPath -c "import platform, struct, sys; print('|'.join((sys.platform, platform.machine().lower(), str(struct.calcsize('P') * 8), '.'.join(map(str, sys.version_info[:3])))))"
if ($LASTEXITCODE -ne 0) {
    throw "无法读取 Python 构建环境（退出码：$LASTEXITCODE）。"
}
$PythonParts = ([string]$PythonProbe).Trim().Split('|')
if ($PythonParts.Count -ne 4 -or $PythonParts[0] -ne "win32" -or $PythonParts[2] -ne "64") {
    throw "必须使用 64 位 Windows Python 构建；当前环境：$PythonProbe"
}
if ($PythonParts[1] -notin @("amd64", "x86_64")) {
    throw "必须使用 x64 Python 构建 Windows-x64 发布包；当前架构：$($PythonParts[1])"
}
if (-not $PythonParts[3].StartsWith("3.13.")) {
    throw "项目要求 Python 3.13；当前版本：$($PythonParts[3])"
}

Write-Host "[2/8] 检查版本与文档..."
foreach ($DocumentPath in $VersionedDocumentation) {
    if (-not (Test-Path -LiteralPath $DocumentPath)) {
        throw "缺少发布文档：$DocumentPath"
    }
    $DocumentContent = Get-Content -Raw -Encoding UTF8 -LiteralPath $DocumentPath
    if ($DocumentContent -notmatch [regex]::Escape($AppVersion)) {
        throw "发布文档未包含当前版本 $AppVersion：$DocumentPath"
    }
}

Write-Host "[3/8] 运行 Python 编译检查和全部单元测试..."
Invoke-NativeCommand $PythonPath @(
    "-m", "py_compile",
    (Join-Path $ProjectRoot "client.py"),
    (Join-Path $ProjectRoot "runner.py")
) "Python 编译检查失败。"
Invoke-NativeCommand $PythonPath @(
    "-m", "unittest", "discover",
    "-s", (Join-Path $ProjectRoot "tests"),
    "-p", "test_*.py"
) "单元测试失败。"

Write-Host "[4/8] 安装并核验 Windows 打包依赖..."
Invoke-NativeCommand $PythonPath @(
    "-m", "pip", "install", "--disable-pip-version-check",
    "-r", (Join-Path $ProjectRoot "requirements-build.txt")
) "安装打包依赖失败。"
Invoke-NativeCommand $PythonPath @(
    "-c", "import maa, PyInstaller, tkinter; print('MaaFramework、PyInstaller 和 Tkinter 已就绪')"
) "Windows 打包依赖自检失败。"

Write-Host "[5/8] 使用 PyInstaller 构建 Windows x64 便携版..."
Push-Location $ProjectRoot
try {
    & $PythonPath -m PyInstaller --noconfirm --clean $SpecPath
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败。" }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    throw "打包完成后未找到客户端程序：$ExecutablePath"
}

Write-Host "[6/8] 运行 Windows 便携版自检..."
$SelfCheckMarker = Join-Path $AppDirectory ".self-check-ok"
if (Test-Path -LiteralPath $SelfCheckMarker) {
    Remove-Item -LiteralPath $SelfCheckMarker -Force
}
$SelfCheckProcess = Start-Process `
    -FilePath $ExecutablePath `
    -ArgumentList @("--self-check", "`"$SelfCheckMarker`"") `
    -PassThru `
    -WindowStyle Hidden
if (-not $SelfCheckProcess.WaitForExit(30000)) {
    $SelfCheckProcess.Kill()
    $SelfCheckProcess.WaitForExit()
    throw "便携版自检超时。"
}
if ($SelfCheckProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $SelfCheckMarker)) {
    throw "便携版自检失败。"
}
Remove-Item -LiteralPath $SelfCheckMarker -Force

Copy-Item -LiteralPath (Join-Path $ProjectRoot "便携版使用说明.txt") -Destination $AppDirectory -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $AppDirectory -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "使用说明.md") -Destination $AppDirectory -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "CHANGELOG.md") -Destination $AppDirectory -Force
Copy-Item -LiteralPath $VersionPath -Destination $AppDirectory -Force

Write-Host "[7/8] 生成 Windows ZIP 和 SHA-256..."
New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null
if (Test-Path -LiteralPath $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}
Compress-Archive -LiteralPath $AppDirectory -DestinationPath $ArchivePath -CompressionLevel Optimal
$ArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
Set-Content -Encoding ASCII -LiteralPath $ChecksumPath -Value "$ArchiveHash  $ArchiveName"

Write-Host "[8/8] 审计发布包并复核 SHA-256..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
try {
    $EntryNames = @($Archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    $RequiredEntries = @(
        "FashionMallAutomation/FashionMallClient.exe",
        "FashionMallAutomation/VERSION",
        "FashionMallAutomation/README.md",
        "FashionMallAutomation/使用说明.md",
        "FashionMallAutomation/便携版使用说明.txt",
        "FashionMallAutomation/CHANGELOG.md"
    )
    foreach ($RequiredEntry in $RequiredEntries) {
        if ($RequiredEntry -notin $EntryNames) {
            throw "发布包缺少必要文件：$RequiredEntry"
        }
    }

    $ForbiddenPatterns = @(
        '(^|/)tests(/|$)',
        '(^|/)runtime(/|$)',
        '(^|/)(client|runner)\.py$',
        'client_config\.json$',
        '(?i)(^|/)(debug|screenshots-[^/]*)(/|$)|\.log$'
    )
    foreach ($ForbiddenPattern in $ForbiddenPatterns) {
        $ForbiddenEntry = $EntryNames | Where-Object { $_ -match $ForbiddenPattern } | Select-Object -First 1
        if ($ForbiddenEntry) {
            throw "发布包包含禁止分发的内容：$ForbiddenEntry"
        }
    }

    $VersionEntry = $Archive.GetEntry("FashionMallAutomation/VERSION")
    $VersionReader = [System.IO.StreamReader]::new($VersionEntry.Open(), [System.Text.Encoding]::UTF8)
    try {
        $PackagedVersion = $VersionReader.ReadToEnd().Trim()
    } finally {
        $VersionReader.Dispose()
    }
    if ($PackagedVersion -ne $AppVersion) {
        throw "发布包版本不一致：预期 $AppVersion，实际 $PackagedVersion"
    }
} finally {
    $Archive.Dispose()
}

$RecordedHash = ((Get-Content -Raw -Encoding ASCII -LiteralPath $ChecksumPath).Trim() -split '\s+')[0]
$VerifiedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
if ($RecordedHash -ne $VerifiedHash) {
    throw "SHA-256 校验文件与发布包不一致。"
}

Write-Host "版本：$AppVersion"
Write-Host "便携版目录：$AppDirectory"
Write-Host "分发压缩包：$ArchivePath"
Write-Host "SHA-256：$ChecksumPath"
Write-Host "Windows x64 一键发布流程已全部通过。" -ForegroundColor Green
