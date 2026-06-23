$ErrorActionPreference = "Stop"

python -m pytest -q

Push-Location desktop
try {
  npm test -- --run
  npm run build
}
finally {
  Pop-Location
}
