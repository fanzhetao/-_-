[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $ProjectRoot "FashionMallClient.spec"
$BuildDependencies = Join-Path $ProjectRoot ".build-deps"
$DistDirectory = Join-Path $ProjectRoot "dist"
$AppDirectory = Join-Path $DistDirectory "FashionMallAutomation"
$ExecutablePath = Join-Path $AppDirectory "FashionMallClient.exe"
$ReleaseDirectory = Join-Path $ProjectRoot "release"
$ArchivePath = Join-Path $ReleaseDirectory "FashionMallAutomation-Windows-x64.zip"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "未找到 .venv。请先在项目根目录创建 Python 3.13 虚拟环境。"
}

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

New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null
if (Test-Path -LiteralPath $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}
Compress-Archive -LiteralPath $AppDirectory -DestinationPath $ArchivePath -CompressionLevel Optimal

Write-Host "便携版目录：$AppDirectory"
Write-Host "分发压缩包：$ArchivePath"
