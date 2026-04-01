@echo off
echo Installing client requirements...
pip3 install -r client_requirements.txt

if not exist "grid.png" (
    echo Generating grid texture...
    python generate_grid.py
)

echo Starting Tank Battle Arena client...
python3 client_complete.py
pause
