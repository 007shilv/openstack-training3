param(
    [Parameter(Mandatory = $true)] [string] $WorkspaceRoot,
    [Parameter(Mandatory = $true)] [string] $EnvironmentRoot,
    [string] $RepoZip = ""
)

$ErrorActionPreference = "Stop"

$folders = @(
    "01_环境与版本清单",
    "02_openEuler安装与云镜像",
    "03_OpenStack离线源",
    "04_OpenStack部署脚本",
    "05_手工配置文件模板",
    "06_TRAE与DeepSeek接入资料",
    "07_实验网络与虚拟机说明",
    "08_检查验收与运维工具",
    "09_官方来源与下载校验"
)
foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path (Join-Path $EnvironmentRoot $folder) -Force | Out-Null
}

Copy-Item -LiteralPath (Join-Path $WorkspaceRoot "third-edition-work\config\version-matrix.json") `
    -Destination (Join-Path $EnvironmentRoot "01_环境与版本清单\version-matrix.json") -Force

$scriptTarget = Join-Path $EnvironmentRoot "04_OpenStack部署脚本\openstack-ts"
if (Test-Path -LiteralPath $scriptTarget) { Remove-Item -LiteralPath $scriptTarget -Recurse -Force }
Copy-Item -LiteralPath (Join-Path $WorkspaceRoot "third-edition-work\deployment\openstack-ts") `
    -Destination $scriptTarget -Recurse -Force
Get-ChildItem -LiteralPath $scriptTarget -Recurse -Directory -Filter "__pycache__" |
    Sort-Object FullName -Descending |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $scriptTarget -Recurse -File -Include "*.pyc", ".pytest_cache" |
    Remove-Item -Force

$templateTarget = Join-Path $EnvironmentRoot "05_手工配置文件模板\config-snapshots"
if (Test-Path -LiteralPath $templateTarget) { Remove-Item -LiteralPath $templateTarget -Recurse -Force }
Copy-Item -LiteralPath (Join-Path $WorkspaceRoot "third-edition-work\validation\manual-install\config-snapshots") `
    -Destination $templateTarget -Recurse -Force

if ($RepoZip -and (Test-Path -LiteralPath $RepoZip)) {
    Copy-Item -LiteralPath $RepoZip -Destination (Join-Path $EnvironmentRoot "03_OpenStack离线源\openstack_repo.zip") -Force
}

$readme = @"
# 第三版教材配套环境

本目录与《云计算基础架构平台构建与应用（第三版初稿）》配套。实验操作系统为openEuler 24.03 LTS SP3，OpenStack实训版本为2023.1 Antelope。

使用顺序：环境与版本清单 → openEuler安装 → 离线源 → 第二篇手工配置 → 第三篇智能体脚本部署 → 验收与运维。

安全说明：目录中不保存OpenStack真实口令、DeepSeek API Key、SSH私钥、Cookie或令牌。`04_OpenStack部署脚本`仅供第十三章明确的智能体自动化实训；第二篇必须按教材逐条手工输入命令、编辑配置、同步数据库并启动服务。
"@
Set-Content -LiteralPath (Join-Path $EnvironmentRoot "README.md") -Value $readme -Encoding utf8

$checksumRoot = Join-Path $EnvironmentRoot "09_官方来源与下载校验"
$checksumPath = Join-Path $checksumRoot "SHA256SUMS.txt"
$environmentPrefix = $EnvironmentRoot.TrimEnd("\") + "\"
$lines = Get-ChildItem -LiteralPath $EnvironmentRoot -Recurse -File |
    Where-Object { $_.FullName -ne $checksumPath } |
    Sort-Object FullName |
    ForEach-Object {
        if (-not $_.FullName.StartsWith($environmentPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "File escaped environment root: $($_.FullName)"
        }
        $relative = $_.FullName.Substring($environmentPrefix.Length).Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
Set-Content -LiteralPath $checksumPath -Value $lines -Encoding utf8
Write-Output "PACKAGED_FILES=$($lines.Count)"

