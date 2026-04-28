@echo off
title MSYS Importacao de Dados

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale em https://python.org e tente novamente.
    pause
    exit /b 1
)

:: Vai para a pasta do script
cd /d "%~dp0"

:: Instala / atualiza dependencias
echo Verificando dependencias...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias. Verifique sua conexao e tente novamente.
    pause
    exit /b 1
)
echo Dependencias OK.
echo.

:: Inicia o sistema
echo Iniciando MSYS Importacao de Dados...
echo Acesse: http://127.0.0.1:5000
echo.
echo Pressione Ctrl+C para encerrar.
echo ---------------------------------------------------------------------
python main.py

:: Encerramento
echo.
echo Sistema encerrado.
pause
