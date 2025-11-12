---

# VPC Controller – Full Virtual Private Cloud Demo

This project lets you **build and visualize a complete Virtual Private Cloud (VPC) system** entirely on a single Linux host.
You’ll see how cloud networking concepts — like subnets, NAT, peering, and firewall policies — actually look when implemented under the hood with **Linux namespaces, veth pairs, bridges, and iptables**.

You don’t need AWS or GCP for this one.
Just your terminal, `root` privileges, and curiosity.

---

##  **Project Structure**

Here’s how the project is laid out:

```
/vpcctl-stage-4
│
├── demo.sh          # End-to-end demo that builds, tests, and tears down two VPCs
├── policy.json      # Sample firewall/security policy file
├── vpcctl.py        # The main VPC controller script (core logic)
└── README.md        # You're reading it right now
```

---

## 1. Getting Started

First, clone this repository to your local machine:

```bash
git clone https://github.com/<your-username>/bimbo-vpc.git
cd bimbo-vpc
```

Every command from here will run inside this directory.
You’ll notice two main files:

* **vpcctl.py** — the controller that manages your virtual network.
* **demo.sh** — a full step-by-step demonstration script.

---

## 2. Requirements

Before running the demo, make sure your system has:

* Python 3.8 or higher
* `iproute2` and `iptables` installed
* `curl` and `netcat` (for testing connectivity)

You can install missing dependencies using:

```bash
sudo apt update
sudo apt install -y python3 iproute2 iptables curl netcat
```

---

## 3. Running the Demo

Run the entire demo with root privileges:

```bash
sudo bash demo.sh
```

By the end, you’ll have simulated:

* Two VPCs (vpc1 and vpc2)
* Each with public and private subnets
* HTTP applications deployed inside
* NAT-enabled public subnets
* A peering connection between both VPCs
* Firewall policies enforcing ingress and egress rules

Everything gets logged in the `bimbo_logs` folder and persisted in `bimbo_data`.

---

## 4. What Happens Step by Step (and What It Means)

Let’s walk through it like we’re building the cloud from scratch.

---

### Step 1: Create Two VPCs

```bash
python3 vpcctl.py make-vpc --vname vpc1 --cidr 10.10.0.0/16
python3 vpcctl.py make-vpc --vname vpc2 --cidr 10.20.0.0/16
```

Here, you’re **creating two isolated Layer 2 domains**, each with its own bridge (like AWS’ internal VPC switch).
In Linux, a *bridge* acts as a virtual switch that can connect multiple interfaces.

So, `bimbo-vpc1-br` and `bimbo-vpc2-br` are your cloud backbones — your "virtual LANs."

---

### Step 2: Add Public and Private Subnets

Each subnet is a **network namespace** with its own routing table, interfaces, and isolated processes.

```bash
python3 vpcctl.py add-net --vpc vpc1 --netname public --cidr 10.10.1.0/24
python3 vpcctl.py add-net --vpc vpc1 --netname private --cidr 10.10.2.0/24
```

What’s happening under the hood:

* A **namespace** (like a mini virtual machine) is created.
* A **veth pair** connects that namespace to the bridge.
* The bridge gets an IP (gateway), and the namespace gets another (host).
* Routes are added so they can talk.

You’ve just created two internal networks — just like AWS subnets.

---

### Step 3: Launch HTTP Applications

```bash
python3 vpcctl.py launch-http --vpc vpc1 --netname public --port 8080
```

Now you start **lightweight web servers** inside each namespace.
Each runs `python3 -m http.server` as if it were an app inside an EC2 instance.
You’ll find logs for each one in `bimbo_logs/http_<subnet>.log`.

Think of it like deploying small test web services in your VPC.

---

### Step 4: Enable NAT for Outbound Internet Access

```bash
python3 vpcctl.py enable-nat --vpc vpc1 --iface ens5
```

Here, you turn on IP forwarding and configure `iptables` MASQUERADE rules.
This means any traffic from the VPC’s CIDR that goes out through `ens5` will appear to come from your real machine’s IP — exactly how AWS NAT gateways work.

Public subnets now have internet access.
Private subnets don’t.
By design.

---

### Step 5: Test Connectivity

The script uses `ping` and `curl` commands like this:

```bash
sudo ip netns exec bimbo-vpc1-public ping -c 2 10.10.2.2
sudo ip netns exec bimbo-vpc1-public curl -s 10.10.2.2:8081
```

This tests **inter-subnet communication within the same VPC**.
They succeed because both subnets share the same bridge — meaning Layer 2 visibility is intact.

Then you test:

* **Outbound access** (public subnets can reach the internet)
* **Private subnet isolation** (private subnets can’t)
* **Cross-VPC isolation** (vpc1 and vpc2 can’t talk yet)

---

### Step 6: Peer the Two VPCs

```bash
python3 vpcctl.py peer --vpc1 vpc1 --cidr1 10.10.1.0/24 --vpc2 vpc2 --cidr2 10.20.1.0/24
```

This connects both VPC bridges using a new veth pair.
`iptables` rules are added to allow traffic between the two CIDRs.

You’ve effectively created a **VPC Peering Connection**, meaning both networks can now exchange packets as if connected by a private route.

---

### Step 7: Apply Firewall Policy

```bash
python3 vpcctl.py apply-policy --vpc vpc1 --netname public --policy policy.json
```

Each namespace gets its own **internal firewall** via `iptables` inside the namespace context.
Rules are applied per direction — ingress and egress — based on the JSON file.

You’re now enforcing **micro-segmentation** at the subnet level.

---

### Step 8: Inspect and Clean Up

```bash
python3 vpcctl.py show --vpc vpc1
python3 vpcctl.py remove-vpc --vpc vpc1
```

You can view all metadata — bridges, subnets, veth pairs, PIDs, and IPs — from `show`.
And when done, delete the entire VPC with one command.
This removes bridges, namespaces, and all associated interfaces cleanly.

---

## 5. Logs and State

Every operation logs to `bimbo_logs` with timestamps, and each VPC’s configuration is stored in `bimbo_data` as a JSON file.

You can open these to inspect what the controller keeps track of — CIDRs, bridge names, namespaces, veth interfaces, and running apps.

---

## 6. Key Concepts You’ll Understand by the End

By the time you complete the demo, you’ll have learned:

* How **bridges and veth pairs** simulate cloud networks locally
* What **network namespaces** really do under the hood
* How **NAT masquerading** gives internet access to private subnets
* How **peering** creates private inter-VPC routing
* How **firewall policies** isolate and protect workloads
* And how all of this ties together like AWS VPC architecture — just smaller, local, and transparent.

---

## 7. Clean Slate

If you ever want to start fresh:

```bash
sudo ip netns delete $(ip netns list | awk '{print $1}') 2>/dev/null
sudo ip link delete $(ip link show | grep bimbo | awk -F: '{print $2}') 2>/dev/null
rm -rf bimbo_data bimbo_logs
```

This wipes everything and returns your system to its pre-demo state.

---

## 8. Final Thought

This makes sense to me. I just hope it makes sense to you too because I rushed to submit </3

---


## Author
--

Adenuga Israel Abimbola


# :)
