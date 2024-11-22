@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo Creating required directories...
mkdir static\uploads 2>nul
mkdir logs 2>nul

echo Starting the server...
python app.py
