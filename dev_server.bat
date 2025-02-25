@echo off
cd src/ide/www
start /wait cmd /c "npm run build-dev"
cd dist
http-server -p 80
