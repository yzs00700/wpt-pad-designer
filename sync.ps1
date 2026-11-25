param(
  [string]$Message = "",
  [switch]$NoPull,
  [switch]$NoPush,
  [switch]$NoGitee
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

if (-not (Test-Path '.git')) {
  throw "当前目录不是 Git 仓库：$repo"
}

# 首次使用时补齐提交身份
$name = (& git config user.name 2>$null)
if (-not $name) { & git config user.name 'yzs00700' }
$email = (& git config user.email 2>$null)
if (-not $email) { & git config user.email 'yzs00700@users.noreply.github.com' }

$origin = (& git remote get-url origin 2>$null)
if (-not $origin) {
  throw "未配置 origin。请先执行：git remote add origin https://github.com/yzs00700/wpt-pad-designer.git"
}

if (-not $NoPull) {
  Write-Host '[1/3] 拉取 origin/main ...' -ForegroundColor Cyan
  & git fetch origin --prune
  if ($LASTEXITCODE -ne 0) { throw '拉取失败：请检查网络或远程地址。' }
  & git rev-parse --verify --quiet origin/main | Out-Null
  if ($LASTEXITCODE -eq 0) {
    & git pull --rebase --autostash origin main
    if ($LASTEXITCODE -ne 0) {
      throw '拉取时发生冲突。请按 Git 提示解决冲突，然后重新运行 sync。'
    }
  } else {
    Write-Host '      远程 main 还不存在，跳过拉取（首次推送）。'
  }
}

$changes = (& git status --porcelain)
if ($changes) {
  if (-not $Message) {
    $Message = 'sync: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' @ ' + $env:COMPUTERNAME
  }
  Write-Host '[2/3] 提交本地改动 ...' -ForegroundColor Cyan
  & git add -A
  & git commit -m $Message
  if ($LASTEXITCODE -ne 0) { throw '提交失败。' }
} else {
  Write-Host '[2/3] 没有本地改动。' -ForegroundColor DarkGray
}

if (-not $NoPush) {
  Write-Host '[3/3] 推送到 origin ...' -ForegroundColor Cyan
  & git push origin main
  if ($LASTEXITCODE -ne 0) {
    throw '推送失败：请确认已登录 GitHub（浏览器授权窗口或 Token），并且有仓库写权限。'
  }

  $gitee = (& git remote get-url gitee 2>$null)
  if ($gitee -and -not $NoGitee) {
    Write-Host '      推送到 gitee ...' -ForegroundColor Cyan
    & git push gitee main
    if ($LASTEXITCODE -ne 0) {
      Write-Host '      Gitee 推送失败（GitHub 已成功）。可稍后重试，或改用 Gitee 镜像自动同步。' -ForegroundColor Yellow
    }
  }
}

Write-Host '完成。' -ForegroundColor Green
