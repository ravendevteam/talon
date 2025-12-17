@echo off
set FileVersion=1.0.0.19
set ProductVersion=2.1.0.0

:: Talon relies on ChrisTitusTech's WinUtil and Raphi's Win11Debloat scripts for a heavy chunk of the
:: debloating process. Before, Talon would download then execute these during the debloating process,
:: but to make Talon fully offline-capable, it now downloads them at build time then bundles them
:: inside the produced executable.
set "ROOT=%~dp0"
set "SCRIPT_BUNDLE_DIR=%ROOT%external_scripts"
if exist "%SCRIPT_BUNDLE_DIR%" rd /s /q "%SCRIPT_BUNDLE_DIR%"
mkdir "%SCRIPT_BUNDLE_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
	"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
	"$u1 = 'https://christitus.com/win'; " ^
	"$u2 = 'https://api.github.com/repos/Raphire/Win11Debloat/zipball/2025.09.27'; " ^
	"$u3 = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'; " ^
	"$o1 = Join-Path '%SCRIPT_BUNDLE_DIR%' 'winutil.ps1'; " ^
	"$zip2 = Join-Path '%SCRIPT_BUNDLE_DIR%' 'win11debloat.zip'; " ^
	"$o3 = Join-Path '%SCRIPT_BUNDLE_DIR%' 'webview2.exe'; " ^
	"Invoke-WebRequest -Uri $u1 -OutFile $o1 -UseBasicParsing; " ^
	"Invoke-WebRequest -Uri $u2 -OutFile $zip2 -UseBasicParsing; " ^
	"Invoke-WebRequest -Uri $u3 -OutFile $o3 -UseBasicParsing; " ^
	"try { Expand-Archive -LiteralPath $zip2 -DestinationPath '%SCRIPT_BUNDLE_DIR%' -Force } catch { Write-Error $_; exit 1 }; " ^
	"Remove-Item -LiteralPath $zip2 -Force; " ^
	"$c = Get-Content -LiteralPath $o1 -Raw -Encoding UTF8; " ^
	"$patched = [regex]::Replace($c,'(?ms)^\s*Write-Host ""Installing features\.\.\.""\s*.*?Write-Host ""Done\.""','Write-Host ""Features installation skipped""' + [Environment]::NewLine); " ^
	"Set-Content -LiteralPath $o1 -Value $patched -Encoding UTF8;"

python -m nuitka --onefile --standalone --enable-plugins=pyqt5 --remove-output --windows-console-mode=disable --windows-uac-admin --output-dir=dist --output-filename=Talon.exe --follow-imports --windows-icon-from-ico=media\ICON.ico --include-data-dir=configs=configs --include-data-dir=media=media --include-data-dir=debloat_raven_scripts=debloat_raven_scripts --include-data-dir=external_scripts=external_scripts --include-data-file=external_scripts\webview2.exe=external_scripts\webview2.exe --include-package=screens --product-name="Talon" --company-name="Raven Development Team" --file-description="Simple utility to debloat Windows in 2 clicks." --file-version=%FileVersion% --product-version=%ProductVersion% --copyright="Copyright (c) 2025 Raven Development Team" --onefile-tempdir-spec="{CACHE_DIR}\RavenDevelopmentTeam\Talon\{VERSION}" talon.py