@echo off
setlocal
set FileVersion=1.0.0.15
set "ROOT=%~dp0"
set "SCRIPT_BUNDLE_DIR=%ROOT%external_scripts"
pushd "%ROOT%" || exit /b 1

python -c "from importlib.metadata import version; from pathlib import Path; import sys; required=next(line.split('==', 1)[1].strip() for line in Path('requirements.txt').read_text().splitlines() if line.startswith('Nuitka==')); installed=version('Nuitka'); sys.exit(0 if installed == required else 'Build requires Nuitka '+required+'; found '+installed+'. Run: python -m pip install Nuitka=='+required)"
if errorlevel 1 exit /b 1

for /f "usebackq delims=" %%V in (`python -c "import ast,pathlib,re,sys; s=pathlib.Path(sys.argv[1]).read_text(encoding='utf-8-sig'); m=re.search(r'^TALON_VERSION\s*=\s*(.+)$', s, re.M); sys.exit(1) if not m else print(ast.literal_eval(m.group(1)))" "%ROOT%talon.py"`) do set "ProductVersion=%%V"
if not defined ProductVersion (
	echo Failed to read TALON_VERSION from talon.py.
	exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
	"$ErrorActionPreference = 'Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
	"$bundle = [IO.Path]::GetFullPath($env:SCRIPT_BUNDLE_DIR); " ^
	"$expected = [IO.Path]::GetFullPath((Join-Path $env:ROOT 'external_scripts')); " ^
	"if ($bundle -ne $expected) { throw 'Invalid external script bundle directory' }; " ^
	"if (Test-Path -LiteralPath $bundle) { Remove-Item -LiteralPath $bundle -Recurse -Force }; " ^
	"New-Item -ItemType Directory -Path $bundle | Out-Null; " ^
	"$u1 = 'https://github.com/ChrisTitusTech/winutil/releases/download/26.08.19/winutil.ps1'; " ^
	"$u2 = 'https://api.github.com/repos/Raphire/Win11Debloat/zipball/2026.08.24'; " ^
	"$o1 = Join-Path $bundle 'winutil.ps1'; " ^
	"$zip2 = Join-Path $bundle 'win11debloat.zip'; " ^
	"Invoke-WebRequest -Uri $u1 -OutFile $o1 -UseBasicParsing; " ^
	"Invoke-WebRequest -Uri $u2 -OutFile $zip2 -UseBasicParsing; " ^
	"Expand-Archive -LiteralPath $zip2 -DestinationPath $bundle -Force; " ^
	"Remove-Item -LiteralPath $zip2 -Force;"
if errorlevel 1 exit /b 1

python -m nuitka --standalone --enable-plugins=pyqt5 --include-qt-plugins=qml --remove-output --windows-console-mode=attach --windows-uac-admin --output-dir=dist --output-filename=Talon.exe --follow-imports --windows-icon-from-ico=media\ICON.ico --include-data-dir=media=media --include-data-dir=ui=ui --include-data-dir=locales=locales --include-data-dir=presets=presets --include-data-dir=external_scripts=external_scripts --include-package=screens --include-package=configuration_components --product-name="Talon" --company-name="Raven Technologies Group LLC" --file-description="Simple utility to debloat Windows in 2 clicks." --file-version=%FileVersion% --product-version=%ProductVersion% --copyright="Copyright (c) 2026 Raven Technologies Group LLC" talon.py
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
	"$ErrorActionPreference = 'Stop'; " ^
	"$dist = [IO.Path]::GetFullPath((Join-Path $env:ROOT 'dist\talon.dist')); " ^
	"if (-not (Test-Path -LiteralPath (Join-Path $dist 'Talon.exe') -PathType Leaf)) { throw 'Talon build output was not found' }; " ^
	"$entries = @(Get-Item -LiteralPath $dist, (Split-Path -Parent $dist) -Force) + @(Get-ChildItem -LiteralPath $dist -Recurse -Force); " ^
	"if ($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Refusing to trim build output containing links or junctions' }; " ^
	"$qmlFiles = @(Get-ChildItem -LiteralPath (Join-Path $dist 'ui') -Filter '*.qml' -File -Recurse); " ^
	"if ($qmlFiles.Count -eq 0) { throw 'Packaged QML files were not found' }; " ^
	"$imports = $qmlFiles | ForEach-Object { [regex]::Matches([IO.File]::ReadAllText($_.FullName), '\bimport\s+([A-Za-z][A-Za-z0-9_.]*)') }; " ^
	"$unsupported = @($imports | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -notin @('QtQuick', 'QtQuick.Window', 'QtQml', 'QtQml.Models', 'QtQml.WorkerScript') } | Sort-Object -Unique); " ^
	"if ($unsupported.Count) { throw ('Review the package cleanup for new QML imports: ' + ($unsupported -join ', ')) }; " ^
	"$qtModules = Get-ChildItem -LiteralPath (Join-Path $dist 'PyQt5') -Filter 'Qt*.pyd' -File; " ^
	"$unsupported = @($qtModules.BaseName | Where-Object { $_ -notin @('QtCore', 'QtGui', 'QtNetwork', 'QtOpenGL', 'QtQml', 'QtQuick', 'QtWidgets') }); " ^
	"if ($unsupported.Count) { throw ('Review the package cleanup for new PyQt modules: ' + ($unsupported -join ', ')) }; " ^
	"$unused = @('PyQt5\qt-plugins\mediaservice', 'PyQt5\qt-plugins\platformthemes', 'PyQt5\qt-plugins\printsupport', 'PyQt5\qt-plugins\platforms\qwebgl.dll', 'pythoncom312.dll', 'libeay32.dll', 'ssleay32.dll', 'media\ICON.ico'); " ^
	"$unused += 'Qt QtBluetooth QtGraphicalEffects QtLocation QtMultimedia QtNfc QtPositioning QtQuick3D QtRemoteObjects QtSensors QtTest QtWebChannel QtWebEngine QtWebSockets QtWebView' -split ' ' | ForEach-Object { 'PyQt5\qml\' + $_ }; " ^
	"$unused += 'Controls Controls.2 Dialogs Extras Layouts LocalStorage Particles.2 PrivateWidgets Scene2D Scene3D Shapes Templates.2 Timeline XmlListModel' -split ' ' | ForEach-Object { 'PyQt5\qml\QtQuick\' + $_ }; " ^
	"$unused += @('PyQt5\qml\QtQml\RemoteObjects', 'PyQt5\qml\QtQml\StateMachine'); " ^
	"$unused += 'bluetooth dbus location multimedia nfc positioning positioningquick printsupport quick3d quick3dassetimport quick3drender quick3druntimerender quick3dutils quickcontrols2 quickparticles quickshapes quicktemplates2 quicktest remoteobjects sensors sql test webchannel webengine webenginecore websockets webview xmlpatterns' -split ' ' | ForEach-Object { 'qt5' + $_ + '.dll' }; " ^
	"$targets = @(foreach ($relative in $unused) { " ^
	"    $target = [IO.Path]::GetFullPath((Join-Path $dist $relative)); " ^
	"    if (-not $target.StartsWith($dist + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw ('Invalid cleanup path: ' + $target) }; " ^
	"    if (Test-Path -LiteralPath $target) { $target }; " ^
	"}); " ^
	"$before = ($entries | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum).Sum; " ^
	"foreach ($target in $targets) { Remove-Item -LiteralPath $target -Recurse -Force }; " ^
	"$after = (Get-ChildItem -LiteralPath $dist -File -Recurse -Force | Measure-Object -Property Length -Sum).Sum; " ^
	"Write-Host ('Removed {0:N2} MiB of unused bundled files; Talon package is {1:N2} MiB.' -f (($before - $after) / 1MB), ($after / 1MB));"
exit /b %errorlevel%
