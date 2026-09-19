# Benchmark C4: execute all 6 frozen official runs in the frozen counterbalanced
# order, one fresh worktree per run, non-interactively, with no permission
# bypass of any kind. Aborts the entire batch on any procedural invalidity.
#
# Usage: pwsh -File run_all_c4.ps1
#
# Preconditions (checked below, script aborts if unmet):
#   - The frozen artifacts under docs/validation/company_os_ai_resource_benchmark_c4/
#     are already committed and pushed on company-os-resource-lab-benchmark-c4.
#   - claude --version reports exactly 2.1.70.
#   - C:\Users\mgial\.benchmark-c2\mcp\treesitter_cache.json exists (reused index).
#   - C:\Users\mgial\.benchmark-c4\mcp\provider_server.py and
#     treesitter_mcp_config.json exist.

$ErrorActionPreference = "Stop"

$RepoDir      = "C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-benchmark-c4"
$Branch       = "company-os-resource-lab-benchmark-c4"
$RunsRoot     = "C:\Users\mgial\.benchmark-c4\runs"
$PromptsDir   = Join-Path $RepoDir "docs\validation\company_os_ai_resource_benchmark_c4\prompts"
$McpConfig    = "C:\Users\mgial\.benchmark-c4\mcp\treesitter_mcp_config.json"
$ExtraTool    = "mcp__treesitter_query__treesitter_query"
$ResultsFile  = "C:\Users\mgial\.benchmark-c4\runs\manifest.json"

function Assert-Precondition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        Write-Error "PRECONDITION FAILED: $Message"
        exit 1
    }
}

$claudeVersion = (& claude --version) 2>&1
Assert-Precondition ($claudeVersion -match "^2\.1\.70") "claude --version must report 2.1.70 exactly, got: $claudeVersion"

Assert-Precondition (Test-Path "C:\Users\mgial\.benchmark-c2\mcp\treesitter_cache.json") "treesitter_cache.json missing"
Assert-Precondition (Test-Path "C:\Users\mgial\.benchmark-c4\mcp\provider_server.py") "C4 provider_server.py missing"
Assert-Precondition (Test-Path $McpConfig) "C4 treesitter_mcp_config.json missing"

Push-Location $RepoDir
$BranchTip = (git rev-parse $Branch).Trim()
$RemoteTip = (git rev-parse "origin/$Branch") 2>$null
Pop-Location
Assert-Precondition ($BranchTip -eq $RemoteTip) "local $Branch ($BranchTip) must match origin/$Branch ($RemoteTip) -- freeze must be pushed before execution"

Write-Host "Frozen branch tip: $BranchTip"

# Frozen counterbalanced run order (run_order.json) -- do not reorder.
$Runs = @(
    @{ id = "T1_C0"; task = "1"; condition = "C0" },
    @{ id = "T1_C2"; task = "1"; condition = "C2" },
    @{ id = "T2_C2"; task = "2"; condition = "C2" },
    @{ id = "T2_C0"; task = "2"; condition = "C0" },
    @{ id = "T3_C0"; task = "3"; condition = "C0" },
    @{ id = "T3_C2"; task = "3"; condition = "C2" }
)

New-Item -ItemType Directory -Force -Path $RunsRoot | Out-Null
$manifest = @()

foreach ($run in $Runs) {
    $runId     = $run.id
    $task      = $run.task
    $condition = $run.condition
    $runDir    = Join-Path $RunsRoot $runId
    $promptFile = Join-Path $PromptsDir "Task${task}_${condition}_prompt.txt"
    $outputJsonl = Join-Path $RunsRoot "$runId.jsonl"

    Assert-Precondition (Test-Path $promptFile) "prompt file missing: $promptFile"

    Write-Host "=== Preparing run $runId (task $task, condition $condition) ==="
    if (Test-Path $runDir) {
        Write-Error "ABORT: run directory already exists ($runDir) -- refusing to reuse a run path. Remove it manually if this is an intentional single-run rerun per the frozen rerun policy."
        exit 1
    }

    Push-Location $RepoDir
    git worktree add $runDir $BranchTip --detach 2>&1 | Write-Host
    $addExit = $LASTEXITCODE
    Pop-Location
    Assert-Precondition ($addExit -eq 0) "git worktree add failed for $runId"

    # Re-verify source fingerprints before the run (stop condition: source drift).
    Push-Location $runDir
    $headSha = (git rev-parse HEAD).Trim()
    Pop-Location
    Assert-Precondition ($headSha -eq $BranchTip) "run worktree $runId HEAD ($headSha) does not match frozen tip ($BranchTip)"

    $mcpArgArgs = @()
    if ($condition -eq "C2") {
        $mcpArgArgs = @("--mcp-config", $McpConfig, "--extra-tool", $ExtraTool)
    }

    Write-Host "=== Executing run $runId ==="
    $pyArgs = @($runDir, $promptFile, $outputJsonl) + $mcpArgArgs
    & python (Join-Path $RepoDir "tools\benchmark_c4\run_condition.py") @pyArgs
    $runExit = $LASTEXITCODE

    if ($runExit -ne 0) {
        Write-Error "ABORT: run $runId exited $runExit -- batch stopped, no further official runs executed. Preserve $runDir and $outputJsonl for the operator; do not retry automatically."
        exit 1
    }

    # Structural leak/contamination check: the transcript must never mention
    # the ground-truth path or the benchmark's own doc directory.
    $leak = Select-String -Path $outputJsonl -Pattern "ground_truth\.json|company_os_ai_resource_benchmark_c4" -SimpleMatch:$false -Quiet
    if ($leak) {
        Write-Error "ABORT: run $runId transcript references the ground-truth path or benchmark doc directory -- INVALID, contamination stop condition triggered."
        exit 1
    }

    $sessionIdLine = Select-String -Path $outputJsonl -Pattern '"session_id":"([a-f0-9-]+)"' | Select-Object -First 1
    $sessionId = if ($sessionIdLine) { $sessionIdLine.Matches[0].Groups[1].Value } else { "UNAVAILABLE" }

    $manifest += [ordered]@{
        run_id = $runId; task = $task; condition = $condition
        run_dir = $runDir; prompt_file = $promptFile; output_jsonl = $outputJsonl
        session_id = $sessionId; head_sha = $headSha; exit_code = $runExit
    }

    Write-Host "=== Run $runId complete (exit=$runExit, session=$sessionId) ==="
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $ResultsFile -Encoding utf8
Write-Host "All 6 official runs complete. Manifest: $ResultsFile"
Write-Host "Next: external scoring (Phase 8) against ground_truth.json -- never inside a measured session."
