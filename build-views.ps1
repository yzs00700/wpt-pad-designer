$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8 = New-Object System.Text.UTF8Encoding($false)

$parts = @()
1..5 | ForEach-Object {
  $f = Join-Path $dir ("wpt-views-{0}.js" -f $_)
  $parts += [IO.File]::ReadAllText($f, [Text.Encoding]::UTF8)
}
$js = ($parts -join "`r`n")
[IO.File]::WriteAllText((Join-Path $dir 'wpt-views.js'), $js, $utf8)

$htmlPath = Join-Path $dir 'wpt-pad-designer.html'
$html = [IO.File]::ReadAllText($htmlPath, [Text.Encoding]::UTF8)
$marker = 'WPT Pad Designer v0.3'
$mi = $html.IndexOf($marker)
if ($mi -lt 0) { throw 'inline module marker not found' }
$start = $html.LastIndexOf('<script>', $mi)
if ($start -lt 0) { throw 'inline module <script> not found' }
$end = $html.IndexOf('</script>', $mi)
if ($end -lt 0) { throw 'inline module </script> not found' }
$end += '</script>'.Length

$block = "<script>`r`n" + $js + "`r`n</script>"
$html = $html.Substring(0, $start) + $block + $html.Substring($end)
[IO.File]::WriteAllText($htmlPath, $html, $utf8)

Write-Host ("rebuilt wpt-views.js ({0:N0} chars) and inlined module ({1} -> {2})" -f $js.Length, ($end - $start), $block.Length)
