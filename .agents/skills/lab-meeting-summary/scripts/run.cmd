@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Persistent Skill entry point. Never generate activation or temporary scripts.
rem Override these variables in the child process environment on another machine.
if not defined LABMEETING_AI_PYTHON set "LABMEETING_AI_PYTHON=D:\software\Anaconda\envs\labmeeting-ai\python.exe"
if defined LABMEETING_AI_PROJECT goto project_ready
for %%I in ("%~dp0..\..\..\..") do set "LABMEETING_AI_PROJECT=%%~fI"
if exist "%LABMEETING_AI_PROJECT%\labmeeting.py" goto project_ready
set "LABMEETING_AI_PROJECT=E:\BRC\Meet\LabMeeting-AI"
:project_ready
if not exist "%LABMEETING_AI_PYTHON%" (
  echo ERROR: Conda environment interpreter not found: "%LABMEETING_AI_PYTHON%" 1>&2
  exit /b 2
)
if not exist "%LABMEETING_AI_PROJECT%\labmeeting.py" (
  echo ERROR: Full project not found: "%LABMEETING_AI_PROJECT%" 1>&2
  exit /b 2
)
"%LABMEETING_AI_PYTHON%" -I -B -u -X utf8 "%LABMEETING_AI_PROJECT%\labmeeting.py" %*
exit /b %errorlevel%
