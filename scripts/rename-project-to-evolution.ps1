#Requires -Version 5.1
<#
.SYNOPSIS
关闭本项目的 Codex、MCP 终端和编辑器后，将项目目录改名为 Evolution。
.DESCRIPTION
先检查目标路径和 Git 关联，改名后保留旧路径兼容入口，并修复已有 Git worktree。
不结束任何进程，不提交或推送代码，不启动容器，不连接数据库。
使用 -WhatIf 可只读预检；GitHub 仓库和 origin 已在本次改名任务中更新。
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param()

$ErrorActionPreference = 'Stop'
$source = 'D:\WorkBench\AI Projects\OrganizationalStructure'
$target = 'D:\WorkBench\AI Projects\Evolution'
$parent = 'D:\WorkBench\AI Projects'

function Invoke-ProjectGit {
    param([string[]]$GitArguments)
    $result = @(& git @GitArguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Git 命令失败，退出码：$LASTEXITCODE。"
    }
    return $result
}

# 固定操作边界，避免在其他目录中误运行。
if ([IO.Path]::GetFullPath($source) -ne (Join-Path $parent 'OrganizationalStructure') -or
    [IO.Path]::GetFullPath($target) -ne (Join-Path $parent 'Evolution')) {
    throw '源目录或目标目录不在预期项目父目录内。'
}
$scriptProject = Split-Path -Parent $PSScriptRoot
if ($scriptProject -ne $source -and $scriptProject -ne $target) {
    throw '请从本项目 scripts 目录中的原脚本运行。'
}
Get-Command git -ErrorAction Stop | Out-Null

$alreadyRenamed = $false
if (Test-Path -LiteralPath $target) {
    $sourceItem = Get-Item -LiteralPath $source -Force -ErrorAction Stop
    $targetItem = Get-Item -LiteralPath $target -Force -ErrorAction Stop
    if ($sourceItem.LinkType -ne 'Junction' -or
        [IO.Path]::GetFullPath([string]$sourceItem.Target[0]).TrimEnd('\') -ne $target -or
        ($targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Evolution 已存在，且不是本脚本预期的已完成状态；不会覆盖或合并目录。'
    }
    $alreadyRenamed = $true
    $activeRoot = $target
} else {
    $sourceItem = Get-Item -LiteralPath $source -Force -ErrorAction Stop
    if (-not $sourceItem.PSIsContainer -or
        ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw '原项目路径必须是实际目录。'
    }
    $activeRoot = $source
}
if (-not (Test-Path -LiteralPath (Join-Path $activeRoot '.git') -PathType Container)) {
    throw '目标不是预期的主 Git 工作区。'
}
$remote = (Invoke-ProjectGit -GitArguments @('-C', $activeRoot, 'remote', 'get-url', 'origin')) -join ''
if ($remote -ne 'https://github.com/mr-vilin/Evolution.git') {
    throw 'origin 与已改名的 Evolution 仓库不一致；请先核对远端。'
}
$headBefore = (Invoke-ProjectGit -GitArguments @('-C', $activeRoot, 'rev-parse', 'HEAD')) -join ''
$worktreeLines = Invoke-ProjectGit -GitArguments @('-C', $activeRoot, 'worktree', 'list', '--porcelain')
$worktrees = @($worktreeLines | Where-Object { $_.StartsWith('worktree ') } | ForEach-Object { $_.Substring(9) })
$sourceGitPath = $source.Replace('\', '/')
$targetGitPath = $target.Replace('\', '/')
$repairedPaths = @()
foreach ($worktree in $worktrees) {
    if (-not (Test-Path -LiteralPath $worktree -PathType Container)) {
        throw "已有工作区无法访问：$worktree；请先处理后再改名。"
    }
    if ($worktree -eq $sourceGitPath -or $worktree -eq $targetGitPath) { continue }
    if ($worktree.StartsWith($sourceGitPath + '/', [StringComparison]::OrdinalIgnoreCase)) {
        $repairedPaths += $targetGitPath + $worktree.Substring($sourceGitPath.Length)
    } else {
        $repairedPaths += $worktree
    }
}
Write-Host "预检通过；需维护 $($repairedPaths.Count) 个附加工作区。"
if (-not $PSCmdlet.ShouldProcess("$source -> $target", '改名目录、保留旧路径兼容入口并修复 Git 工作区')) {
    return
}

# 离开项目目录后执行，避免本脚本的当前目录阻止 Windows 改名。
Set-Location -LiteralPath $parent
if (-not $alreadyRenamed) {
    try {
        Rename-Item -LiteralPath $source -NewName 'Evolution' -ErrorAction Stop
    } catch {
        throw "目录改名失败，原目录保留。请退出本项目的 Codex、MCP 终端和编辑器后重试。原因：$($_.Exception.Message)"
    }
    try {
        New-Item -ItemType Junction -Path $source -Target $target -ErrorAction Stop | Out-Null
    } catch {
        $junctionError = $_.Exception.Message
        try {
            Rename-Item -LiteralPath $target -NewName 'OrganizationalStructure' -ErrorAction Stop
        } catch {
            throw "兼容入口建立失败，目录回退也失败。项目当前位于 $target，请保留全部目录并人工核查。"
        }
        throw "兼容入口建立失败，已恢复原目录。原因：$junctionError"
    }
}

# 即使修复中断，旧路径兼容入口仍使原有 Git 指针可访问；重跑脚本可继续修复。
Invoke-ProjectGit -GitArguments (@('-C', $target, 'worktree', 'repair') + $repairedPaths) | Out-Host
$headAfter = (Invoke-ProjectGit -GitArguments @('-C', $target, 'rev-parse', 'HEAD')) -join ''
if ($headBefore -ne $headAfter) { throw '改名前后 HEAD 不一致，请人工核查。' }
$afterLines = Invoke-ProjectGit -GitArguments @('-C', $target, 'worktree', 'list', '--porcelain')
$afterWorktrees = @($afterLines | Where-Object { $_.StartsWith('worktree ') } | ForEach-Object { $_.Substring(9) })
if ($afterWorktrees.Count -ne $worktrees.Count) { throw '改名前后 Git 工作区数量不一致，请人工核查。' }
foreach ($worktree in $repairedPaths) {
    Invoke-ProjectGit -GitArguments @('-C', $worktree, 'rev-parse', '--git-common-dir') | Out-Null
}
Set-Location -LiteralPath $target
Write-Host "已完成：$target"
Write-Host '旧目录是指向 Evolution 的兼容入口，供现有 Codex 项目和 MCP 配置使用。'
Write-Host '后续可在 Codex 中打开 Evolution；兼容入口仍需保留。未提交或推送代码，未部署。'
