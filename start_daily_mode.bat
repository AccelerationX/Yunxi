@echo off
setlocal

cd /d "%~dp0"

if "%YUNXI_PROVIDER%"=="" set "YUNXI_PROVIDER=moonshot"
if "%YUNXI_EMBEDDING_PROVIDER%"=="" set "YUNXI_EMBEDDING_PROVIDER=lexical"
if "%YUNXI_TICK_INTERVAL%"=="" set "YUNXI_TICK_INTERVAL=300"

set "PYTHONPATH=src;%PYTHONPATH%"

set "ARGS=--provider %YUNXI_PROVIDER% --feishu-enable --embedding-provider %YUNXI_EMBEDDING_PROVIDER% --tick-interval %YUNXI_TICK_INTERVAL%"

if not "%YUNXI_RUN_SECONDS%"=="" set "ARGS=%ARGS% --run-seconds %YUNXI_RUN_SECONDS%"
if "%YUNXI_SKIP_DESKTOP_MCP%"=="1" set "ARGS=%ARGS% --skip-desktop-mcp"
if "%YUNXI_DISABLE_TOOL_USE%"=="1" set "ARGS=%ARGS% --disable-tool-use"

echo [Yunxi] starting daily mode...
echo [Yunxi] provider=%YUNXI_PROVIDER%, embedding=%YUNXI_EMBEDDING_PROVIDER%, tick_interval=%YUNXI_TICK_INTERVAL%
python src\apps\daemon\main.py %ARGS%

endlocal
