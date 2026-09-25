$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pyw = Join-Path $Root "venv\Scripts\pythonw.exe"
$Icon = Join-Path $Root "assets\icon.ico"

if (-not (Test-Path -LiteralPath $Pyw)) {
    throw "먼저 setup.ps1을 실행하세요: $Pyw 없음"
}
# 코드와 함께 아이콘이 바뀔 수 있으므로 기존 파일이 있어도 매번 다시 만든다.
& (Join-Path $Root "venv\Scripts\python.exe") -m riffle.make_icon

$shell = New-Object -ComObject WScript.Shell
$definitions = @(
    @{
        Name = "Riffle.lnk"
        Arguments = "-m riffle"
        Description = "PDF 문서 합치기와 필기 옮기기 데스크톱 앱"
    }
)

# 로컬 웹 판은 2026-09-26 걷었다(데스크톱·원격 웹 두 갈래) — 예전에 만든 바로가기가 남아 있으면 지운다.
foreach ($folder in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
    $old = Join-Path $folder "Riffle 로컬 웹.lnk"
    if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old; Write-Host "옛 바로가기 삭제: $old" }
}

foreach ($definition in $definitions) {
    foreach ($folder in @(
        [Environment]::GetFolderPath("Programs"),
        [Environment]::GetFolderPath("Desktop")
    )) {
        $target = Join-Path $folder $definition.Name
        $shortcut = $shell.CreateShortcut($target)
        $shortcut.TargetPath = $Pyw
        $shortcut.Arguments = $definition.Arguments
        $shortcut.WorkingDirectory = $Root
        $shortcut.IconLocation = "$Icon,0"
        $shortcut.WindowStyle = 1
        $shortcut.Description = $definition.Description
        $shortcut.Save()
        Write-Host "바로가기 생성: $target"
    }
}

Write-Host "설치 완료. 'Riffle' 로 실행하세요." -ForegroundColor Green
