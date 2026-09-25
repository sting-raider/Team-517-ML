$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$vendor = Join-Path $root 'artifacts/rapidfuzz-cpp'
if (-not (Test-Path $vendor)) {
    git clone --depth 1 --branch v3.3.3 https://github.com/rapidfuzz/rapidfuzz-cpp.git $vendor
    if ($LASTEXITCODE -ne 0) { throw 'RapidFuzz C++ download failed' }
}
$py = Join-Path $root '.venv/Scripts/python.exe'
$include = & $py -c "import sysconfig;print(sysconfig.get_paths()['include'])"
$libs = Join-Path (Split-Path $include -Parent) 'libs'
$output = Join-Path $root 'src/ber/_fast_features.pyd'
g++ -O3 -std=c++17 -shared -static "-I$include" "-I$vendor" (Join-Path $root 'src/ber/fast_features.cpp') "-L$libs" -lpython312 -o $output
if ($LASTEXITCODE -ne 0) { throw 'Native feature build failed' }
Write-Output $output
