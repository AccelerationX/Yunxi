@echo off
setlocal
set "YUNXI_HOME=%~dp0"
set "PYTHONPATH=%YUNXI_HOME%src;%PYTHONPATH%"
python "%YUNXI_HOME%src\apps\factory_cli\main.py" %*
