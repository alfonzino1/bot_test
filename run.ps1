# Хронос: обёртка запуска для Windows.
#
#   .\run.ps1              — запустить бота (long polling)
#   .\run.ps1 doctor       — самопроверка: конфиг, БД, тексты
#   .\run.ps1 migrate      — применить миграции (alembic upgrade head)
#   .\run.ps1 test         — прогнать тесты
#   .\run.ps1 migrate-history — история миграций
#
# Python выбирается по порядку: $env:CHRONOS_PYTHON → .venv → встроенный рантайм → python.
# Каталог libs подхватывается автоматически, если он есть (локальная сборка зависимостей).

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$bundled = 'C:\Users\Mahkmud\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$candidates = @()
if ($env:CHRONOS_PYTHON) { $candidates += $env:CHRONOS_PYTHON }
$candidates += (Join-Path $root '.venv\Scripts\python.exe')
$candidates += $bundled

$python = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { $python = $candidate; break }
}
if (-not $python) { $python = 'python' }

$paths = @((Join-Path $root 'src'))
$libs = Join-Path $root 'libs'
if (Test-Path -LiteralPath $libs) { $paths += $libs }
$env:PYTHONPATH = ($paths -join ';')
$env:PYTHONIOENCODING = 'utf-8'

$command = if ($Arguments.Count -gt 0) { $Arguments[0] } else { 'run' }
$rest = if ($Arguments.Count -gt 1) { $Arguments[1..($Arguments.Count - 1)] } else { @() }

switch ($command) {
    'run'    { & $python -m chronos @rest }
    'doctor' { & $python -m chronos doctor @rest }
    'check'  { & $python -m chronos doctor @rest }
    'migrate'         { & $python -m alembic upgrade head @rest }
    'migrate-history' { & $python -m alembic history --verbose @rest }
    'migrate-new'     { & $python -m alembic revision --autogenerate -m $rest[0] }
    'test'   { & $python -m pytest -p no:cacheprovider @rest }
    default  { & $python -m chronos @Arguments }
}
exit $LASTEXITCODE
