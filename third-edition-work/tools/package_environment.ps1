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

$manualTarget = Join-Path $EnvironmentRoot "08_检查验收与运维工具\manual-install-records"
if (Test-Path -LiteralPath $manualTarget) { Remove-Item -LiteralPath $manualTarget -Recurse -Force }
Copy-Item -LiteralPath (Join-Path $WorkspaceRoot "third-edition-work\validation\manual-install") `
    -Destination $manualTarget -Recurse -Force
Get-ChildItem -LiteralPath $manualTarget -Recurse -Directory -Filter "__pycache__" |
    Sort-Object FullName -Descending |
    Remove-Item -Recurse -Force

Copy-Item -LiteralPath (Join-Path $WorkspaceRoot "third-edition-work\manuscript\12-13-agent-deployment-operations.md") `
    -Destination (Join-Path $EnvironmentRoot "06_TRAE与DeepSeek接入资料\智能体部署与运维实训.md") -Force
Copy-Item -LiteralPath (Join-Path $WorkspaceRoot "third-edition-work\research\source-register.md") `
    -Destination (Join-Path $EnvironmentRoot "09_官方来源与下载校验\官方资料登记表.md") -Force

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

$folderNotes = @{
    "01_环境与版本清单\README.md" = @"
# 环境与版本清单

`version-matrix.json` 给出教材实验版本。概览资料冻结于2026年7月31日；实验平台固定为openEuler 24.03 LTS SP3和OpenStack 2023.1 Antelope。不得把概览版本2026.1与实训版本混为一谈。
"@
    "02_openEuler安装与云镜像\README.md" = @"
# openEuler安装与云镜像

为避免重新分发许可不明确的镜像，本目录只提供官方入口：

- openEuler：<https://www.openeuler.org/en/download/>
- CirrOS：<https://download.cirros-cloud.net/>

下载后先核对官方校验值，再导入教学环境。不要把账号、Cookie或下载令牌放入本目录。
"@
    "03_OpenStack离线源\README.md" = @"
# OpenStack离线源

`openstack_repo.zip` 是本书实验使用的本地软件源归档。发布或复制后使用上级目录的`09_官方来源与下载校验/SHA256SUMS.txt`复核完整性。源内核心包对应OpenStack 2023.1 Antelope；不得把它描述为2026.1软件包。
"@
    "04_OpenStack部署脚本\README.md" = @"
# OpenStack部署脚本

`openstack-ts` 是作者提供的参考构建脚本。第二篇禁止把它作为安装入口，学生必须逐条手工输入命令、用vi编辑配置、手工同步数据库、创建服务与端点并启动服务。只有第十三章的一次性智能体部署实训可以读取并执行其受控副本。
"@
    "05_手工配置文件模板\README.md" = @"
# 手工配置文件模板

这里保存双节点实测后的脱敏配置快照，供核对参数名称和最终形态。快照不是覆盖安装包默认文件的脚本；教学时仍应按照教材逐项编辑并在每个阶段验收。
"@
    "06_TRAE与DeepSeek接入资料\README.md" = @"
# TRAE与DeepSeek接入资料

本目录提供第12—13章的文字材料和安全截图清单。TRAE安装包、DeepSeek API Key及任何账户凭据均不随书分发，应从官方渠道获取并只在遮蔽输入框中配置。
"@
    "07_实验网络与虚拟机说明\README.md" = @"
# 实验网络与虚拟机说明

| 节点 | 管理地址 | 角色 | 磁盘 |
| --- | --- | --- | --- |
| controller | 192.168.234.151 | 控制、网络、API | /dev/sda系统盘 |
| compute | 192.168.234.150 | 计算、块/对象存储 | /dev/sda系统盘；/dev/sdb与/dev/sdc各50GiB实验盘 |

ens33承载管理网络，ens34作为Provider桥接口且不配置IP。初始化数据盘前必须重新核对整盘、容量、根盘祖先、挂载、签名和PV状态，并要求明确人工确认。
"@
    "08_检查验收与运维工具\README.md" = @"
# 检查验收与运维资料

`manual-install-records`包含第二篇各组件的逐命令记录、脱敏快照及轻量验收材料。每个组件以“API可访问、服务active/enabled、一个代表性资源生命周期成功并清理”为基本验收口径。验证代码只用于检查，不是安装入口。
"@
    "09_官方来源与下载校验\README.md" = @"
# 官方来源与下载校验

`官方资料登记表.md`登记一手资料入口，`SHA256SUMS.txt`登记配套包所有文件的摘要。摘要用于完整性核验，不包含密码、密钥或令牌。
"@
}
foreach ($item in $folderNotes.GetEnumerator()) {
    Set-Content -LiteralPath (Join-Path $EnvironmentRoot $item.Key) -Value $item.Value -Encoding utf8
}

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

