#!/bin/bash
# DevOps Intern Stage 4 VPC Full Demo Script
# Run this as root (sudo bash demo.sh)
set -e

# Replace eth0 with your actual internet interface
INTERNET_IFACE="ens5"

# 1. Create Two VPCs
python3 vpcctl.py make-vpc --vname vpc1 --cidr 10.10.0.0/16
python3 vpcctl.py make-vpc --vname vpc2 --cidr 10.20.0.0/16

# 2. Add Public and Private Subnets to Each VPC
python3 vpcctl.py add-net --vpc vpc1 --netname public --cidr 10.10.1.0/24
python3 vpcctl.py add-net --vpc vpc1 --netname private --cidr 10.10.2.0/24
python3 vpcctl.py add-net --vpc vpc2 --netname public --cidr 10.20.1.0/24
python3 vpcctl.py add-net --vpc vpc2 --netname private --cidr 10.20.2.0/24

# 3. Deploy HTTP App in Public and Private Subnets
python3 vpcctl.py launch-http --vpc vpc1 --netname public --port 8080
python3 vpcctl.py launch-http --vpc vpc1 --netname private --port 8081
python3 vpcctl.py launch-http --vpc vpc2 --netname public --port 8080
python3 vpcctl.py launch-http --vpc vpc2 --netname private --port 8081
sleep 2

# 4. Enable NAT for Public Subnets
python3 vpcctl.py enable-nat --vpc vpc1 --iface "$INTERNET_IFACE"
python3 vpcctl.py enable-nat --vpc vpc2 --iface "$INTERNET_IFACE"

# 5. Test Communication Between Subnets in Same VPC
sudo ip netns exec bimbo-vpc1-public ping -c 2 10.10.2.2 || true
sudo ip netns exec bimbo-vpc1-public curl -s 10.10.2.2:8081 || true
sudo ip netns exec bimbo-vpc1-private ping -c 2 10.10.1.2 || true
sudo ip netns exec bimbo-vpc1-private curl -s 10.10.1.2:8080 || true

# 6. Test Outbound Internet Access from Public Subnet
sudo ip netns exec bimbo-vpc1-public curl -s http://1.1.1.1  || true
sudo ip netns exec bimbo-vpc2-public curl -s http://1.1.1.1  || true

# 7. Test Outbound Internet Access from Private Subnet (Should Fail)
sudo ip netns exec bimbo-vpc1-private curl -s http://1.1.1.1  || true
sudo ip netns exec bimbo-vpc2-private curl -s http://1.1.1.1  || true

# 8. Test Isolation Between VPCs (Should Fail)
sudo ip netns exec bimbo-vpc1-public ping -c 2 10.20.1.2 || true
sudo ip netns exec bimbo-vpc2-public ping -c 2 10.10.1.2 || true

# 9. Peer VPCs
python3 vpcctl.py peer --vpc1 vpc1 --cidr1 10.10.1.0/24 --vpc2 vpc2 --cidr2 10.20.1.0/24
sleep 2

# 10. Test Communication After Peering
sudo ip netns exec bimbo-vpc1-public ping -c 2 10.20.1.2 || true
sudo ip netns exec bimbo-vpc2-public ping -c 2 10.10.1.2 || true

# 11. Apply Firewall/Security Group Policy
cat > policy.json <<EOF
{
  "ingress": [
    {"port": 8080, "protocol": "tcp", "action": "allow"},
    {"port": 22, "protocol": "tcp", "action": "deny"}
  ],
  "egress": [
    {"port": 80, "protocol": "tcp", "action": "allow"},
    {"port": 22, "protocol": "tcp", "action": "deny"}
  ]
}
EOF
python3 vpcctl.py apply-policy --vpc vpc1 --netname public --policy policy.json
python3 vpcctl.py apply-policy --vpc vpc2 --netname public --policy policy.json

# 12. Test Firewall Enforcement
sudo ip netns exec bimbo-vpc1-public nc -zv 10.10.1.2 22 || true
sudo ip netns exec bimbo-vpc2-public nc -zv 10.20.1.2 22 || true
sudo ip netns exec bimbo-vpc1-public nc -zv 10.10.1.2 8080 || true
sudo ip netns exec bimbo-vpc2-public nc -zv 10.20.1.2 8080 || true

# 13. Inspect VPCs
python3 vpcctl.py show --vpc vpc1
python3 vpcctl.py show --vpc vpc2

# 14. Stop HTTP Apps
python3 vpcctl.py stop-http --vpc vpc1 --netname public
python3 vpcctl.py stop-http --vpc vpc1 --netname private
python3 vpcctl.py stop-http --vpc vpc2 --netname public
python3 vpcctl.py stop-http --vpc vpc2 --netname private

# 15. List All VPCs
python3 vpcctl.py list

# 16. Clean Up (Delete VPCs)
python3 vpcctl.py remove-vpc --vpc vpc1
python3 vpcctl.py remove-vpc --vpc vpc2

# 17. Verify Cleanup
python3 vpcctl.py list
