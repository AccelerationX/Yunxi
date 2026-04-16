@echo off
setlocal

cd /d "%~dp0"

if "%YUNXI_PROVIDER%"=="" set "YUNXI_PROVIDER=ollama"
if "%YUNXI_EMBEDDING_PROVIDER%"=="" set "YUNXI_EMBEDDING_PROVIDER=lexical"
if "%YUNXI_SKIP_LLM_PING%"=="" set "YUNXI_SKIP_LLM_PING=1"

set "PYTHONPATH=src;%PYTHONPATH%"

set "ARGS=--provider %YUNXI_PROVIDER% --healthcheck-deep --feishu-enable --embedding-provider %YUNXI_EMBEDDING_PROVIDER%"

if "%YUNXI_SKIP_LLM_PING%"=="1" set "ARGS=%ARGS% --skip-llm-ping"
if "%YUNXI_SKIP_DESKTOP_MCP%"=="1" set "ARGS=%ARGS% --skip-desktop-mcp"
if "%YUNXI_DISABLE_TOOL_USE%"=="1" set "ARGS=%ARGS% --disable-tool-use"

echo [Yunxi] running daily mode healthcheck...
echo [Yunxi] provider=%YUNXI_PROVIDER%, embedding=%YUNXI_EMBEDDING_PROVIDER%, skip_llm_ping=%YUNXI_SKIP_LLM_PING%
python src\apps\daemon\main.py %ARGS%

endlocal
