[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
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
$BuildDependencies = Join-Path $ProjectRoot ".build-deps"
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

Write-Host "[1/7] 检查版本与文档..."
foreach ($DocumentPath in $VersionedDocumentation) {
    if (-not (Test-Path -LiteralPath $DocumentPath)) {
        throw "缺少发布文档：$DocumentPath"
    }
    $DocumentContent = Get-Content -Raw -Encoding UTF8 -LiteralPath $DocumentPath
    if ($DocumentContent -notmatch [regex]::Escape($AppVersion)) {
        throw "发布文档未包含当前版本 $AppVersion：$DocumentPath"
    }
}

Write-Host "[2/7] 运行 Python 编译检查和单元测试..."
& $PythonPath -m py_compile `
    (Join-Path $ProjectRoot "client.py") `
    (Join-Path $ProjectRoot "runner.py")
if ($LASTEXITCODE -ne 0) { throw "Python 编译检查失败。" }
& $PythonPath -m unittest discover -s (Join-Path $ProjectRoot "tests") -p "test_*.py"
if ($LASTEXITCODE -ne 0) { throw "单元测试失败。" }

Write-Host "[3/7] 准备构建环境与依赖..."
$PythonBase = (& $PythonPath -c "import sys; print(sys.base_prefix)").Trim()
if ($LASTEXITCODE -ne 0) { throw "无法确定 Python 安装目录。" }
$SourceTclRoot = Join-Path $PythonBase "tcl"
$StagedTclRoot = Join-Path $BuildDependencies "tcl"
$StagedTclLibrary = Join-Path $StagedTclRoot "tcl8.6"
$StagedTkLibrary = Join-Path $StagedTclRoot "tk8.6"

if (-not (Test-Path -LiteralPath (Join-Path $SourceTclRoot "tcl8.6\init.tcl"))) {
    throw "Python 缺少 Tcl 运行库，无法打包 Tkinter 客户端。"
}

New-Item -ItemType Directory -Force -Path $StagedTclLibrary, $StagedTkLibrary | Out-Null
Copy-Item -Path (Join-Path $SourceTclRoot "tcl8.6\*") -Destination $StagedTclLibrary -Recurse -Force
Copy-Item -Path (Join-Path $SourceTclRoot "tk8.6\*") -Destination $StagedTkLibrary -Recurse -Force
$env:TCL_LIBRARY = $StagedTclLibrary
$env:TK_LIBRARY = $StagedTkLibrary

& $PythonPath -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "安装打包依赖失败。" }

Write-Host "[4/7] 使用 PyInstaller 构建便携版..."
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

Write-Host "[5/7] 运行便携版自检..."
$SelfCheckMarker = Join-Path $AppDirectory ".self-check-ok"
if (Test-Path -LiteralPath $SelfCheckMarker) {
    Remove-Item -LiteralPath $SelfCheckMarker -Force
}
$SelfCheckProcess = Start-Process `
    -FilePath $ExecutablePath `
    -ArgumentList "--self-check `"$SelfCheckMarker`"" `
    -PassThru `
    -WindowStyle Hidden
if (-not $SelfCheckProcess.WaitForExit(20000)) {
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

Write-Host "[6/7] 生成发布压缩包和 SHA-256..."
New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null
if (Test-Path -LiteralPath $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}
Compress-Archive -LiteralPath $AppDirectory -DestinationPath $ArchivePath -CompressionLevel Optimal
$ArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
Set-Content -Encoding ASCII -LiteralPath $ChecksumPath -Value "$ArchiveHash  $ArchiveName"

Write-Host "[7/7] 审计发布包内容..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
try {
    $EntryNames = @($Archive.Entries | ForEach-Object { $_.FullName })
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
Write-Host "一键发布流程已全部通过。"
