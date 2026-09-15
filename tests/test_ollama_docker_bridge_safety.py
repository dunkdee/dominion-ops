from pathlib import Path
import subprocess


SCRIPT = Path("scripts/remediation/install_ollama_docker_bridge.sh")


def test_bridge_script_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_bridge_cannot_start_governed_ollama_by_dependency():
    text = SCRIPT.read_text(encoding="utf-8")
    marker = "Description=Dominion Docker-to-loopback Ollama proxy"
    assert marker in text
    service_block = text.split(marker, 1)[1].split("\nUNIT", 1)[0]
    service_lines = {line.strip() for line in service_block.splitlines()}
    assert "Requisite=ollama.service" in service_lines
    assert "Requires=ollama.service" not in service_lines
    assert "adapter_dependency_fail_closed=PASS" in text
    assert "! grep -Fq 'Requires=ollama.service' \"$SERVICE_UNIT\"" in text


def test_bridge_binds_only_verified_docker_bridge_gateway():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DOCKER_BRIDGE_GATEWAY=" in text
    assert '[ "$HOST_GATEWAY_IP" = "$DOCKER_BRIDGE_GATEWAY" ]' in text
    assert "check_host_gateway_equals_docker_bridge=PASS" in text
    assert "ListenStream=${HOST_GATEWAY_IP}:${OLLAMA_PORT}" in text
    assert "ListenStream=0.0.0.0" not in text


def test_bridge_arms_interruption_safe_rollback_before_mutation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "trap 'on_exit $?' EXIT" in text
    assert "trap 'exit 129' HUP" in text
    assert "trap 'exit 130' INT" in text
    assert "trap 'exit 143' TERM" in text
    assert "interruption_rollback_armed=PASS" in text
    assert "prior_adapter_state_captured=PASS" in text
    assert "rollback_adapter_state=PASS" in text
    assert text.index("MUTATION_ARMED=1") < text.index("PHASE 2: WRITE FAIL-CLOSED ADAPTER UNITS")


def test_bridge_preserves_prior_units_for_rollback():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'PREV_SOCKET_B64="$($SUDO base64 -w0 "$SOCKET_UNIT"' in text
    assert 'PREV_SERVICE_B64="$($SUDO base64 -w0 "$SERVICE_UNIT"' in text
    assert "restore_prior_state()" in text
    assert "partial adapter state detected" in text
    assert "existing socket unit is not the Dominion adapter" in text
    assert "existing service unit is not the Dominion adapter" in text


def test_bridge_model_diagnostic_matches_governed_deerflow_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'REQUIRED_MODEL_PREFIX="nemotron-3-nano:4b"' in text
    assert 'REQUIRED_MODEL_PREFIX="llama3.1:8b"' not in text
    assert "required_model_contract_check=PASS" in text


def test_bridge_proves_ollama_process_lifecycle_unchanged():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "OLLAMA_PID_BEFORE=" in text
    assert "OLLAMA_PID_AFTER=" in text
    assert "OLLAMA_SINCE_BEFORE=" in text
    assert "OLLAMA_SINCE_AFTER=" in text
    assert "ollama_lifecycle_unchanged=PASS" in text
