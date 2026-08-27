# 10 · Architecture

Architecture describes how Dominion's services, control plane, agents, connector fabric, and evidence paths fit together.

## Navigate

- [[Dominion-Brain/03-Control-Plane/CONTROL_PLANE|Control Plane]]
- [[Dominion-Brain/03-Control-Plane/DOMINION_OPERATING_MAP|Operating Map]]
- [[Dominion-Brain/03-Control-Plane/RUNTIME_ALIGNMENT|Runtime Alignment]]
- [[Dominion-Command-Center/17-MCP-CLI-Connector|MCP CLI Connector Fabric]]

## Production Topology

Founder authority → governance/control plane → agents and schedulers → MCP CLI connector fabric → registered local/API/CLI targets → receipts → canonical runtime state → Obsidian + web Command Center.

The MCP layer is adapter infrastructure, not a bypass around governance. Registry edits define which targets exist; arbitrary URLs and arbitrary shell commands are denied at runtime.

Architecture documentation is design truth; live runtime status still requires current evidence.

[[Dominion-Command-Center/00-HOME|← Command Center]]