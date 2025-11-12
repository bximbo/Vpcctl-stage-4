#!/usr/bin/env python3
"""
Bimbo VPC Controller - VPC management.
"""
import argparse
import json
import subprocess
import time
import ipaddress
import hashlib
from pathlib import Path

# --- Setup ---
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "bimbo_data"
LOG_DIR = BASE_DIR / "bimbo_logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# --- Logging ---
def bimbo_log(event, details):
    log_file = LOG_DIR / f"{event}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {details}\n")

# --- Helpers ---
def shell(cmd, silent=False):
    if not silent:
        print(f"$ {' '.join(str(x) for x in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result

def short_id(*args):
    return hashlib.md5(":".join(args).encode()).hexdigest()[:7]

def state_path(name):
    return DATA_DIR / f"{name}.json"

def save_state(name, data):
    with open(state_path(name), "w") as f:
        json.dump(data, f, indent=2)

def load_state(name):
    p = state_path(name)
    if not p.exists():
        print(f"[ERR] VPC '{name}' not found.")
        exit(1)
    with open(p) as f:
        return json.load(f)

def remove_state(name):
    p = state_path(name)
    if p.exists():
        p.unlink()

# --- VPC Operations ---
def make_vpc(args):
    vpc = args.vname
    cidr = args.cidr
    br = f"bimbo-{vpc}-br"
    shell(["ip", "link", "add", br, "type", "bridge"], silent=True)
    shell(["ip", "link", "set", br, "up"])
    shell(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    vpc_data = {"vpc": vpc, "cidr": cidr, "bridge": br, "subnets": {}}
    save_state(vpc, vpc_data)
    print(f"[OK] VPC '{vpc}' created.")
    bimbo_log("make_vpc", f"Created VPC {vpc} with {cidr} and bridge {br}")

def add_net(args):
    vpc = args.vpc
    netname = args.netname
    cidr = args.cidr
    vpc_data = load_state(vpc)
    br = vpc_data["bridge"]
    ns = f"bimbo-{vpc}-{netname}"
    veth1 = f"bimbo-{short_id(vpc, netname)}-a"
    veth2 = f"bimbo-{short_id(vpc, netname)}-b"
    net = ipaddress.ip_network(cidr)
    hosts = list(net.hosts())
    if len(hosts) < 2:
        print(f"[ERR] CIDR too small.")
        return
    gw, hostip = str(hosts[0]), str(hosts[1])
    mask = net.prefixlen
    shell(["ip", "netns", "add", ns], silent=True)
    shell(["ip", "link", "add", veth1, "type", "veth", "peer", "name", veth2])
    shell(["ip", "link", "set", veth1, "netns", ns])
    shell(["ip", "netns", "exec", ns, "ip", "addr", "add", f"{hostip}/{mask}", "dev", veth1])
    shell(["ip", "netns", "exec", ns, "ip", "link", "set", veth1, "up"])
    shell(["ip", "link", "set", veth2, "up"])
    shell(["ip", "link", "set", veth2, "master", br])
    # Ensure bridge IP is set and up
    shell(["ip", "addr", "add", f"{gw}/{mask}", "dev", br], silent=True)
    shell(["ip", "link", "set", br, "up"], silent=True)
    shell(["ip", "netns", "exec", ns, "ip", "route", "add", "default", "via", gw])
    vpc_data["subnets"][netname] = {"ns": ns, "veth1": veth1, "veth2": veth2, "cidr": cidr, "gw": gw, "hostip": hostip}
    save_state(vpc, vpc_data)
    print(f"[OK] Subnet '{netname}' added to VPC '{vpc}'.")
    bimbo_log("add_net", f"Added subnet {netname} ({cidr}) to VPC {vpc}")

def launch_http(args):
    vpc = args.vpc
    netname = args.netname
    port = args.port
    vpc_data = load_state(vpc)
    ns = vpc_data["subnets"][netname]["ns"]
    logfile = LOG_DIR / f"http_{netname}_{port}.log"
    cmd = ["ip", "netns", "exec", ns, "python3", "-m", "http.server", str(port)]
    try:
        with open(logfile, "w") as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        vpc_data["subnets"][netname]["http"] = {"port": port, "pid": proc.pid, "log": str(logfile)}
        save_state(vpc, vpc_data)
        print(f"[OK] HTTP server running in {netname} on port {port} (PID {proc.pid})")
        bimbo_log("launch_http", f"HTTP server started in {netname} ({vpc}) port {port} PID {proc.pid}")
    except Exception as e:
        print(f"[ERR] Failed to launch HTTP server: {e}")
        bimbo_log("launch_http", f"Failed to launch HTTP server in {netname} ({vpc}): {e}")

def stop_http(args):
    vpc = args.vpc
    netname = args.netname
    vpc_data = load_state(vpc)
    http = vpc_data["subnets"][netname].get("http")
    if not http:
        print(f"[INFO] No HTTP server found.")
        return
    pid = http["pid"]
    shell(["kill", str(pid)], silent=True)
    del vpc_data["subnets"][netname]["http"]
    save_state(vpc, vpc_data)
    print(f"[OK] HTTP server stopped in {netname}.")
    bimbo_log("stop_http", f"Stopped HTTP server in {netname} ({vpc}) PID {pid}")

def enable_nat(args):
    vpc = args.vpc
    iface = args.iface
    vpc_data = load_state(vpc)
    br = vpc_data["bridge"]
    cidr = vpc_data["cidr"]
    shell(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    shell(["iptables", "-t", "nat", "-A", "POSTROUTING", "-s", cidr, "-o", iface, "-j", "MASQUERADE"], silent=True)
    shell(["iptables", "-A", "FORWARD", "-i", br, "-o", iface, "-j", "ACCEPT"], silent=True)
    shell(["iptables", "-A", "FORWARD", "-i", iface, "-o", br, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"], silent=True)
    print(f"[OK] NAT enabled for VPC '{vpc}' via '{iface}'.")
    bimbo_log("enable_nat", f"Enabled NAT for VPC {vpc} via {iface}")

def peer(args):
    vpc1 = args.vpc1
    vpc2 = args.vpc2
    cidr1 = args.cidr1
    cidr2 = args.cidr2
    vpc1_data = load_state(vpc1)
    vpc2_data = load_state(vpc2)
    br1 = vpc1_data["bridge"]
    br2 = vpc2_data["bridge"]
    vethA = f"peer-{short_id(vpc1, vpc2)}-A"
    vethB = f"peer-{short_id(vpc1, vpc2)}-B"
    shell(["ip", "link", "add", vethA, "type", "veth", "peer", "name", vethB], silent=True)
    shell(["ip", "link", "set", vethA, "master", br1])
    shell(["ip", "link", "set", vethB, "master", br2])
    shell(["ip", "link", "set", vethA, "up"])
    shell(["ip", "link", "set", vethB, "up"])
    shell(["iptables", "-A", f"FORWARD", "-s", cidr1, "-d", cidr2, "-j", "ACCEPT"], silent=True)
    shell(["iptables", "-A", f"FORWARD", "-s", cidr2, "-d", cidr1, "-j", "ACCEPT"], silent=True)
    print(f"[OK] Peered VPCs '{vpc1}' <-> '{vpc2}'")
    bimbo_log("peer", f"Peered {vpc1} ({cidr1}) <-> {vpc2} ({cidr2})")

def apply_policy(args):
    vpc = args.vpc
    netname = args.netname
    policyfile = Path(args.policy)
    if not policyfile.exists():
        print(f"[ERR] Policy file not found.")
        return
    vpc_data = load_state(vpc)
    ns = vpc_data["subnets"][netname]["ns"]
    with open(policyfile) as f:
        policy = json.load(f)
    def validate_action(action):
        act = action.strip().lower()
        if act in ("allow", "accept"):
            return "ACCEPT"
        elif act in ("deny", "drop"):
            return "DROP"
        else:
            print(f"[ERR] Invalid action '{action}' in policy. Use 'allow'/'accept' or 'deny'/'drop'.")
            return None

    for rule in policy.get("ingress", []):
        action = validate_action(rule.get("action", ""))
        if not action:
            continue
        shell(["ip", "netns", "exec", ns, "iptables", "-A", "INPUT", "-p", rule.get("protocol", "tcp"), "--dport", str(rule["port"]), "-j", action])
    for rule in policy.get("egress", []):
        action = validate_action(rule.get("action", ""))
        if not action:
            continue
        shell(["ip", "netns", "exec", ns, "iptables", "-A", "OUTPUT", "-p", rule.get("protocol", "tcp"), "--dport", str(rule["port"]), "-j", action])
    print(f"[OK] Policy applied to {netname} in VPC {vpc}.")
    bimbo_log("apply_policy", f"Applied policy {policyfile} to {netname} in {vpc}")

def show_vpc(args):
    vpc = args.vpc
    vpc_data = load_state(vpc)
    print(json.dumps(vpc_data, indent=2))
    bimbo_log("show_vpc", f"Inspected VPC {vpc}")

def remove_vpc(args):
    vpc = args.vpc
    vpc_data = load_state(vpc)
    br = vpc_data["bridge"]
    shell(["ip", "link", "set", br, "down"], silent=True)
    shell(["ip", "link", "del", br], silent=True)
    for netname in list(vpc_data["subnets"].keys()):
        ns = vpc_data["subnets"][netname]["ns"]
        shell(["ip", "netns", "del", ns], silent=True)
    remove_state(vpc)
    print(f"[OK] VPC '{vpc}' deleted.")
    bimbo_log("remove_vpc", f"Deleted VPC {vpc}")

def list_vpcs(args):
    vpcs = [p.stem for p in DATA_DIR.glob("*.json")]
    print("Bimbo VPCs:")
    for v in vpcs:
        print(f"- {v}")
    bimbo_log("list_vpcs", f"Listed VPCs: {vpcs}")

# --- CLI ---
def main():
    parser = argparse.ArgumentParser(description="Bimbo VPC Controller")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(func=list_vpcs)
    mk = sub.add_parser("make-vpc"); mk.add_argument("--vname"); mk.add_argument("--cidr"); mk.set_defaults(func=make_vpc)
    an = sub.add_parser("add-net"); an.add_argument("--vpc"); an.add_argument("--netname"); an.add_argument("--cidr"); an.set_defaults(func=add_net)
    lh = sub.add_parser("launch-http"); lh.add_argument("--vpc"); lh.add_argument("--netname"); lh.add_argument("--port", type=int); lh.set_defaults(func=launch_http)
    sh = sub.add_parser("stop-http"); sh.add_argument("--vpc"); sh.add_argument("--netname"); sh.set_defaults(func=stop_http)
    nat = sub.add_parser("enable-nat"); nat.add_argument("--vpc"); nat.add_argument("--iface"); nat.set_defaults(func=enable_nat)
    pr = sub.add_parser("peer"); pr.add_argument("--vpc1"); pr.add_argument("--cidr1"); pr.add_argument("--vpc2"); pr.add_argument("--cidr2"); pr.set_defaults(func=peer)
    ap = sub.add_parser("apply-policy"); ap.add_argument("--vpc"); ap.add_argument("--netname"); ap.add_argument("--policy"); ap.set_defaults(func=apply_policy)
    sv = sub.add_parser("show"); sv.add_argument("--vpc"); sv.set_defaults(func=show_vpc)
    rm = sub.add_parser("remove-vpc"); rm.add_argument("--vpc"); rm.set_defaults(func=remove_vpc)
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
