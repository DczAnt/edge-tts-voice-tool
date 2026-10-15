@echo off
chcp 65001 >nul
cd /d %~dp0
echo ===============================================
echo   Edge TTS 语音生成工具 - 打包便携版单文件 exe
echo ===============================================
echo.

where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 PyInstaller，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败，请手动执行: pip install pyinstaller
        pause
        exit /b 1
    )
)

pyinstaller --clean --onefile --windowed ^
    --name EdgeTTS_VoiceTool ^
    --distpath dist ^
    --workpath build ^
    --specpath build ^
    src\main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo [完成] 打包成功: dist\EdgeTTS_VoiceTool.exe
echo.
explorer /select,"dist\EdgeTTS_VoiceTool.exe"
pause