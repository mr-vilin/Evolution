# Trusted SSH MCP entry. Service tokens remain inside the remote container.
param(
    [string]$Server = 'tencent_test_col'
)

$ErrorActionPreference = 'Stop'
& ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes $Server 'cd /srv/organization-directory && sudo -n docker compose -f compose.json --profile agent exec -T mcp python -m app.mcp --transport stdio'
exit $LASTEXITCODE
