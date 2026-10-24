@echo off
start "" "%~dp0pig_pet.exe" --qa-window --no-codex-observer --status-file "%~dp0acceptance-state\codex-status.json"
