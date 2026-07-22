#!/usr/bin/env python3
"""Safety entrypoint for the Stage-2F guarded cutover engine.

It adds four controls without duplicating the underlying cutover logic:
1. a failed old-container rename immediately restarts the original container;
2. stopped rollback containers are disconnected from the production network so
   their old service aliases cannot compete with the new containers;
3. rollback reconnects the exact service aliases before originals are started;
4. target port bindings are treated as a hard container-health contract.
"""

from __future__ import annotations

import stage2f_guarded_cutover as engine

_ORIGINAL_COMMAND = engine.command
_ORIGINAL_SANITIZED = engine.sanitized_container

PORT_CONTRACTS = {
    "baby-api": {("public", "8080", "8080/tcp")},
    "dominion-web": {("public", "8090", "80/tcp")},
    "wix-agent": {("loopback", "8082", "8000/tcp")},
    "baby-logger": set(),
}


def binding_scope(host_ip):
    """Normalize equivalent Docker host-bind representations."""
    if host_ip in {"127.0.0.1", "::1"}:
        return "loopback"
    return "public"


def guarded_command(args, *, cwd=None, timeout=300, env=None):
    """Add rename recovery and rollback-network isolation."""
    result = _ORIGINAL_COMMAND(args, cwd=cwd, timeout=timeout, env=env)

    if (
        result.get("returncode") != 0
        and len(args) == 4
        and args[:2] == ["docker", "rename"]
        and args[2] in engine.TARGETS
        and "-rollback-stage2f-" in args[3]
    ):
        _ORIGINAL_COMMAND(["docker", "start", args[2]], timeout=90)

    if (
        result.get("returncode") == 0
        and len(args) == 4
        and args[:3] == ["docker", "update", "--restart=no"]
    ):
        rollback_name = args[3]
        if "-rollback-stage2f-" in rollback_name:
            disconnect = _ORIGINAL_COMMAND(
                ["docker", "network", "disconnect", "--force", engine.NETWORK_NAME, rollback_name],
                timeout=30,
            )
            if disconnect.get("returncode") != 0:
                return {
                    "available": True,
                    "returncode": 1,
                    "stdout": "",
                    "stderr_type": "rollback_network_disconnect_failed",
                }
    return result


def guarded_sanitized(name):
    """Mark a target unhealthy when its host-port contract is not exact."""
    item = _ORIGINAL_SANITIZED(name)
    if name in PORT_CONTRACTS and item.get("exists"):
        actual = {
            (
                binding_scope(port.get("host_ip")),
                port.get("host_port") or "",
                port.get("container_port") or "",
            )
            for port in item.get("ports", [])
        }
        valid = actual == PORT_CONTRACTS[name]
        item["port_contract_valid"] = valid
        if not valid:
            item["running"] = False
    return item


def guarded_rollback(migrated, rollback_names):
    """Restore names, exact aliases, restart policies, and health."""
    actions = []
    errors = []
    for service in reversed(migrated):
        remove = _ORIGINAL_COMMAND(["docker", "rm", "--force", service], timeout=90)
        actions.append({"service": service, "new_removed": remove.get("returncode") == 0})

    for service in reversed(migrated):
        rollback_name = rollback_names[service]
        rename = _ORIGINAL_COMMAND(["docker", "rename", rollback_name, service], timeout=30)
        if rename.get("returncode") != 0:
            errors.append(f"rollback_rename_failed:{service}")
            continue

        connect_args = ["docker", "network", "connect"]
        if service in {"baby-api", "baby-logger", "dominion-web"}:
            connect_args.extend(["--alias", service])
        connect_args.extend([engine.NETWORK_NAME, service])
        connect = _ORIGINAL_COMMAND(connect_args, timeout=30)
        if connect.get("returncode") != 0:
            restored = _ORIGINAL_SANITIZED(service)
            if not any(network.get("network_id") == engine.NETWORK_ID for network in restored.get("networks", [])):
                errors.append(f"rollback_network_connect_failed:{service}")
                continue

        policy = _ORIGINAL_COMMAND(
            ["docker", "update", f"--restart={engine.TARGETS[service]['restart']}", service],
            timeout=30,
        )
        start = _ORIGINAL_COMMAND(["docker", "start", service], timeout=90)
        if policy.get("returncode") != 0 or start.get("returncode") != 0:
            errors.append(f"rollback_start_failed:{service}")
            continue

        health = engine.TARGETS[service]["health"]
        if health and not engine.wait_http(health[0], health[1], timeout=90):
            errors.append(f"rollback_health_failed:{service}")

    final_health = [engine.http_probe(*item) for item in engine.PROTECTED_HTTP]
    if any(item.get("status") != 200 for item in final_health):
        errors.append("rollback_protected_http_failed")
    return {
        "success": not errors,
        "errors": errors,
        "actions": actions,
        "health": final_health,
    }


engine.command = guarded_command
engine.sanitized_container = guarded_sanitized
engine.rollback = guarded_rollback

if __name__ == "__main__":
    raise SystemExit(engine.main())
