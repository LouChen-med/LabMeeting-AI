@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Persistent Skill entry point. Never generate activation or temporary scripts.
rem Override these variables in the child process environment on another machine.
if not defined LABMEETING_AI_PYTHON set "LABMEETING_AI_PYTHON=D:\software\Anaconda\envs\labmeeting-ai\python.exe"
set "LABMEETING_AI_SCRIPT=%~dp0labmeeting.py"
if not exist "%LABMEETING_AI_PYTHON%" (
  echo ERROR: Conda environment interpreter not found: "%LABMEETING_AI_PYTHON%" 1>&2
  exit /b 2
)
if not exist "%LABMEETING_AI_SCRIPT%" (
  echo ERROR: Skill tool not found: "%LABMEETING_AI_SCRIPT%" 1>&2
  exit /b 2
)
"%LABMEETING_AI_PYTHON%" -I -B -u -X utf8 "%LABMEETING_AI_SCRIPT%" %*
exit /b %errorlevel%
