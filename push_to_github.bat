@echo off
echo === R5-Ultra-Controller GitHub Push ===
echo.

:: Remove any broken .git directory
if exist ".git" (
    echo Cleaning up existing git folder...
    rmdir /s /q .git
)

echo Initializing git repository...
git init
git branch -M main

echo.
echo Configuring identity...
git config user.email "mariaribaudo71@gmail.com"
git config user.name "Zelozzzz"

echo.
echo Configuring remote...
git remote add origin https://github.com/Zelozzzz/R5-Ultra-Controller.git

echo.
echo Adding all files...
git add .

echo.
echo Committing...
git commit -m "Initial commit"

echo.
echo Pushing to GitHub...
git push -u origin main

echo.
echo === Done! Check https://github.com/Zelozzzz/R5-Ultra-Controller ===
pause
