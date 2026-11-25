$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rel = 'commonfiles\CPython\3_10\winx64\Release\python\python.exe'

$cands = @()
foreach ($envName in @('ANSYSEM_ROOT252', 'AWP_ROOT252')) {
  $root = [Environment]::GetEnvironmentVariable($envName)
  if ($root) { $cands += (Join-Path $root $rel) }
}
foreach ($drive in @('C', 'D', 'E', 'F')) {
  $cands += "${drive}:\Program Files\ANSYS Inc\v252\AnsysEM\$rel"
  $cands += "${drive}:\ANSYS2025R2\ANSYS Inc\v252\AnsysEM\$rel"
}

$py = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) {
  throw "未找到 ANSYS Electronics Desktop 2025 R2 自带 Python。请先安装 AEDT 2025 R2，或手动用其 python.exe 运行 wpt_bridge.py。"
}

Write-Host "使用 AEDT Python: $py"
& $py (Join-Path $here 'wpt_bridge.py') @args
