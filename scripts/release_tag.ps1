<#
脚本说明：
- 用于“一键发布”当前 main 代码：仅打 tag 并推送。
- 版本来源为 app/version.yml 的 project_version。
- 脚本不会执行 git add / git commit，代码提交需人工提前完成。
- 当 tag（如 v5.2.0）推送到远端后，GitHub Actions 会自动创建 Release。
#>

# 出错立即终止，避免半成功状态（例如打了 tag 但未成功推送）
$ErrorActionPreference = "Stop"

# 计算仓库根目录（当前脚本位于 scripts/ 下）
$repoRoot = Split-Path -Parent $PSScriptRoot
$versionFile = Join-Path $repoRoot "app/version.yml"

# 基础校验：版本配置文件必须存在
if (-not (Test-Path $versionFile)) {
  throw "app/version.yml 不存在: $versionFile"
}

# 从 app/version.yml 提取 project_version（要求 X.Y.Z）
$projectVersion = ""
Get-Content $versionFile | ForEach-Object {
  if ($_ -match '^\s*project_version\s*:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$') {
    $projectVersion = $Matches[1]
  }
}

if (-not $projectVersion) {
  throw "app/version.yml 中未找到 project_version"
}

# 规范化 tag 格式：v<project_version>
$tag = "v$projectVersion"

# 切换到仓库根目录执行后续命令，确保路径与 git 上下文正确
Push-Location $repoRoot
try {
  # 要求当前分支为 main，避免误在其他分支打发布 tag
  $branch = (git branch --show-current).Trim()
  if ($branch -ne "main") {
    throw "当前分支不是 main（当前: $branch），请切换到 main 后再执行"
  }

  # 先检查 tag 是否已存在；若存在则直接终止
  $tagExists = git tag --list $tag
  if ($tagExists) {
    throw "tag 已存在: $tag，已停止执行"
  }

  Write-Host "准备发布 tag: $tag" -ForegroundColor Yellow
  $confirm = Read-Host "确认继续执行 git tag + git push ? 输入 y 继续，其它任意键取消"
  if ($confirm -ne "y" -and $confirm -ne "Y") {
    throw "已取消发布操作（未执行 tag/push）"
  }

  # 打 tag，并推送 main 与 tag
  git tag $tag
  git push origin HEAD
  git push origin $tag

  Write-Host "已发布 tag: $tag"
  Write-Host "GitHub Actions 将自动创建 Release。"
} finally {
  # 无论成功失败都恢复原始目录
  Pop-Location
}
