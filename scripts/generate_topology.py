#!/usr/bin/env python3
"""
Programmatic 10-AS BGP Topology and Configuration Generator.

Generates:
1. config/as65001/ through config/as65010/ (frr.conf, daemons, vtysh.conf)
2. topologies/docker-compose.yml (10 containers, 9 point-to-point subnets)
3. topologies/bgp_multi_as.clab.yml (ContainerLab configuration)

Topology Architecture:
- Tier-1 Transit Core: AS65001 <-> AS65002 (Peering)
- Regional ISPs: AS65003, AS65004, AS65005, AS65006
- Stubs & Enterprise: AS65007 (192.0.2.0/24), AS65008 (198.51.100.0/24), AS65009 (203.0.113.0/24)
- Rogue / Attacker: AS65010 (multi-hop via AS65006)
- AI Controllers deployed on: AS65001 (Core Defender) and AS65003 (Edge Defender)
"""

import os
import shutil
from typing import Dict, List, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
TOPOLOGIES_DIR = os.path.join(PROJECT_ROOT, "topologies")

# Links definition: (left_as, right_as, subnet_prefix, left_ip, right_ip, network_name)
LINKS = [
    (65001, 65002, "10.0.12.0/29", "10.0.12.2", "10.0.12.3", "net_12"),
    (65001, 65003, "10.0.13.0/29", "10.0.13.2", "10.0.13.3", "net_13"),
    (65001, 65004, "10.0.14.0/29", "10.0.14.2", "10.0.14.3", "net_14"),
    (65002, 65005, "10.0.25.0/29", "10.0.25.2", "10.0.25.3", "net_25"),
    (65002, 65006, "10.0.26.0/29", "10.0.26.2", "10.0.26.3", "net_26"),
    (65003, 65007, "10.0.37.0/29", "10.0.37.2", "10.0.37.3", "net_37"),
    (65003, 65008, "10.0.38.0/29", "10.0.38.2", "10.0.38.3", "net_38"),
    (65004, 65009, "10.0.49.0/29", "10.0.49.2", "10.0.49.3", "net_49"),
    (65006, 65010, "10.0.60.0/29", "10.0.60.2", "10.0.60.3", "net_610"),
]

# AS Node definitions
NODES = {
    65001: {
        "name": "as65001",
        "role": "Tier-1 Transit Core (AI Controller #1)",
        "originated_prefixes": [],
        "has_ai_controller": True,
    },
    65002: {
        "name": "as65002",
        "role": "Tier-1 Transit Core",
        "originated_prefixes": [],
        "has_ai_controller": False,
    },
    65003: {
        "name": "as65003",
        "role": "Regional ISP West (AI Controller #2)",
        "originated_prefixes": [],
        "has_ai_controller": True,
    },
    65004: {
        "name": "as65004",
        "role": "Regional ISP East",
        "originated_prefixes": [],
        "has_ai_controller": False,
    },
    65005: {
        "name": "as65005",
        "role": "Regional ISP North",
        "originated_prefixes": [],
        "has_ai_controller": False,
    },
    65006: {
        "name": "as65006",
        "role": "Regional ISP South",
        "originated_prefixes": [],
        "has_ai_controller": False,
    },
    65007: {
        "name": "as65007",
        "role": "Stub Customer A",
        "originated_prefixes": ["192.0.2.0/24"],
        "has_ai_controller": False,
    },
    65008: {
        "name": "as65008",
        "role": "Stub Customer B",
        "originated_prefixes": ["198.51.100.0/24"],
        "has_ai_controller": False,
    },
    65009: {
        "name": "as65009",
        "role": "Enterprise Network",
        "originated_prefixes": ["203.0.113.0/24"],
        "has_ai_controller": False,
    },
    65010: {
        "name": "as65010",
        "role": "Rogue / Attacker",
        "originated_prefixes": [],
        "has_ai_controller": False,
    },
}

DAEMONS_CONTENT = """# Tell zebra to enable routing
zebra=yes
bgpd=yes
ospfd=no
ospf6d=no
ripd=no
ripngd=no
isisd=no
fabricd=no
pimd=no
pbrd=no
bfdd=no
fabricd=no
vrrpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
pathd=no
pcepd=no
"""

VTYSH_CONF_CONTENT = """service integrated-vtysh-config
"""


def get_node_peers(as_num: int) -> List[Dict[str, Any]]:
    """Returns list of peer connections for an AS node."""
    peers = []
    for left_as, right_as, subnet, left_ip, right_ip, net_name in LINKS:
        if as_num == left_as:
            peers.append({
                "remote_as": right_as,
                "local_ip": left_ip,
                "peer_ip": right_ip,
                "network": net_name,
                "subnet": subnet,
            })
        elif as_num == right_as:
            peers.append({
                "remote_as": left_as,
                "local_ip": right_ip,
                "peer_ip": left_ip,
                "network": net_name,
                "subnet": subnet,
            })
    return peers


def generate_frr_conf(as_num: int) -> str:
    node = NODES[as_num]
    name = node["name"]
    peers = get_node_peers(as_num)
    primary_ip = peers[0]["local_ip"] if peers else f"10.0.{as_num % 100}.2"

    lines = [
        "frr version 10.2.1",
        "frr defaults traditional",
        f"hostname {name}",
        "log syslog informational",
        "no ipv6 forwarding",
        "service integrated-vtysh-config",
        "!",
    ]

    # Loopback interface for originated prefixes
    if node["originated_prefixes"]:
        lines.append("interface lo")
        for pfx in node["originated_prefixes"]:
            base_ip = pfx.split("/")[0].rsplit(".", 1)[0] + ".1"
            lines.append(f" ip address {base_ip}/{pfx.split('/')[1]}")
        lines.append("exit")
        lines.append("!")

    # BGP router configuration
    lines.extend([
        f"router bgp {as_num}",
        f" bgp router-id {primary_ip}",
        " no bgp ebgp-requires-policy",
        " bgp log-neighbor-changes",
        " timers bgp 3 9",
        " !",
    ])

    # Neighbors
    for p in peers:
        lines.append(f" neighbor {p['peer_ip']} remote-as {p['remote_as']}")
        lines.append(f" neighbor {p['peer_ip']} description Peering-to-AS{p['remote_as']}")
    lines.append(" !")

    # Address family ipv4 unicast
    lines.append(" address-family ipv4 unicast")
    for pfx in node["originated_prefixes"]:
        lines.append(f"  network {pfx}")

    for p in peers:
        lines.append(f"  neighbor {p['peer_ip']} activate")
        lines.append(f"  neighbor {p['peer_ip']} send-community both")
        route_map_name = f"RM_IN_AS{p['remote_as']}"
        lines.append(f"  neighbor {p['peer_ip']} route-map {route_map_name} in")

    lines.append(" exit-address-family")
    lines.append("exit")
    lines.append("!")

    # Route maps
    for p in peers:
        route_map_name = f"RM_IN_AS{p['remote_as']}"
        lines.extend([
            f"route-map {route_map_name} permit 10",
            " set local-preference 100",
            "exit",
            "!",
        ])

    lines.extend([
        "line vty",
        "exit",
        "",
    ])

    return "\n".join(lines)


def generate_docker_compose() -> str:
    lines = [
        "# Auto-generated 10-AS BGP Testbed Compose File",
        "services:",
    ]

    for as_num in sorted(NODES.keys()):
        name = NODES[as_num]["name"]
        peers = get_node_peers(as_num)

        lines.extend([
            f"  {name}:",
            "    image: quay.io/frrouting/frr:10.2.1",
            f"    container_name: {name}",
            f"    hostname: {name}",
            "    cap_add:",
            "      - NET_ADMIN",
            "      - SYS_ADMIN",
            "      - NET_RAW",
            "    volumes:",
            f"      - ../config/{name}/daemons:/etc/frr/daemons:ro",
            f"      - ../config/{name}/frr.conf:/etc/frr/frr.conf:ro",
            f"      - ../config/{name}/vtysh.conf:/etc/frr/vtysh.conf:ro",
            "    networks:",
        ])
        for p in peers:
            lines.extend([
                f"      {p['network']}:",
                f"        ipv4_address: {p['local_ip']}",
            ])
        lines.append("    restart: unless-stopped")
        lines.append("")

    lines.append("networks:")
    for left_as, right_as, subnet, left_ip, right_ip, net_name in LINKS:
        gw_ip = subnet.rsplit(".", 1)[0] + ".1"
        lines.extend([
            f"  {net_name}:",
            "    driver: bridge",
            "    ipam:",
            "      driver: default",
            "      config:",
            f"        - subnet: {subnet}",
            f"          gateway: {gw_ip}",
        ])

    lines.append("")
    return "\n".join(lines)


def generate_clab_yaml() -> str:
    lines = [
        "name: bgp-ai-mesh-10as",
        "",
        "topology:",
        "  nodes:",
    ]

    for as_num in sorted(NODES.keys()):
        name = NODES[as_num]["name"]
        lines.extend([
            f"    {name}:",
            "      kind: linux",
            "      image: quay.io/frrouting/frr:10.2.1",
            "      binds:",
            f"        - ../config/{name}/daemons:/etc/frr/daemons",
            f"        - ../config/{name}/frr.conf:/etc/frr/frr.conf",
            f"        - ../config/{name}/vtysh.conf:/etc/frr/vtysh.conf",
            "",
        ])

    lines.append("  links:")
    link_idx: Dict[str, int] = {}
    for left_as, right_as, subnet, left_ip, right_ip, net_name in LINKS:
        left_name = f"as{left_as}"
        right_name = f"as{right_as}"
        link_idx[left_name] = link_idx.get(left_name, 0) + 1
        link_idx[right_name] = link_idx.get(right_name, 0) + 1
        lines.append(
            f'    - endpoints: ["{left_name}:eth{link_idx[left_name]}", "{right_name}:eth{link_idx[right_name]}"]'
        )

    lines.append("")
    return "\n".join(lines)


def build_all():
    print(f"[*] Generating configurations for {len(NODES)} AS nodes in {CONFIG_DIR}...")
    for as_num in sorted(NODES.keys()):
        name = NODES[as_num]["name"]
        as_dir = os.path.join(CONFIG_DIR, name)
        os.makedirs(as_dir, exist_ok=True)

        with open(os.path.join(as_dir, "daemons"), "w", encoding="utf-8", newline="\n") as f:
            f.write(DAEMONS_CONTENT)

        with open(os.path.join(as_dir, "vtysh.conf"), "w", encoding="utf-8", newline="\n") as f:
            f.write(VTYSH_CONF_CONTENT)

        frr_conf = generate_frr_conf(as_num)
        with open(os.path.join(as_dir, "frr.conf"), "w", encoding="utf-8", newline="\n") as f:
            f.write(frr_conf)

        print(f"  [+] Configured {name} ({NODES[as_num]['role']})")

    # Generate docker-compose.yml
    compose_path = os.path.join(TOPOLOGIES_DIR, "docker-compose.yml")
    compose_content = generate_docker_compose()
    with open(compose_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(compose_content)
    print(f"[+] Written {compose_path}")

    # Generate ContainerLab yaml
    clab_path = os.path.join(TOPOLOGIES_DIR, "bgp_multi_as.clab.yml")
    clab_content = generate_clab_yaml()
    with open(clab_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(clab_content)
    print(f"[+] Written {clab_path}")
    print("[*] All 10-AS topology configurations generated successfully.")


if __name__ == "__main__":
    build_all()
