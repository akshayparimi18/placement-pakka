# PowerShell Setup & Verification Script for D:\placement-pakka
$ErrorActionPreference = "Stop"

Write-Host "=== Placement Pakka (Anna App Schema v2) Windows Setup ===" -ForegroundColor Cyan

# 1. Initialize Git & Connect Remote
if (-not (Test-Path ".git")) {
    git init
}
git branch -M main
$remotes = git remote
if ($remotes -contains "origin") {
    git remote set-url origin https://github.com/akshayparimi18/placement-pakka.git
} else {
    git remote add origin https://github.com/akshayparimi18/placement-pakka.git
}

# 2. Clone Official Anna Reference Repo into .ref/ (Read-Only, ignored by Git)
if (-not (Test-Path ".ref/anna-executa-examples")) {
    Write-Host "Cloning whtcjdtc2007/anna-executa-examples into .ref/anna-executa-examples..." -ForegroundColor Yellow
    git clone --depth 1 https://github.com/whtcjdtc2007/anna-executa-examples.git .ref/anna-executa-examples
}

# 3. Create Local Python Virtual Environment (.venv)
if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "Installing dependencies into .venv..." -ForegroundColor Yellow
.\.venv\Scripts\pip install --upgrade pip
if (Test-Path ".ref/anna-executa-examples/sdk/python") {
    .\.venv\Scripts\pip install -e .ref/anna-executa-examples/sdk/python
}
.\.venv\Scripts\pip install -e ./executas/placement-panel langgraph langchain-core pydantic pytest

# 4. Run Automated Smoke Test Suite
Write-Host "Running test_plugin.py verification..." -ForegroundColor Green
.\.venv\Scripts\python test_plugin.py

# 5. Stage & Commit
git status
git add .
git commit -m "feat: initial Placement Pakka Anna App (schema v2)" --allow-empty
Write-Host "Ready to push! Run: git push -u origin main" -ForegroundColor Green
