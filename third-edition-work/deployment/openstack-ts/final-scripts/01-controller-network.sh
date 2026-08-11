#!/usr/bin/env bash
set -euo pipefail

# Configure the controller management NIC and basic hostname/hosts mapping.
# Run this script on the controller node only.

MGMT_NIC="ens33"
CONTROLLER_IP="192.168.234.151/24"
GATEWAY_IP="192.168.234.2"
DNS_IP="192.168.234.2"

nmcli connection modify "${MGMT_NIC}" \
  ipv4.addresses "${CONTROLLER_IP}" \
  ipv4.gateway "${GATEWAY_IP}" \
  ipv4.dns "${DNS_IP}" \
  ipv4.method manual \
  connection.autoconnect yes

hostnamectl set-hostname controller

cat > /etc/hosts <<'EOF'
127.0.0.1 localhost
192.168.234.151 controller
192.168.234.150 compute
EOF

# Apply the NetworkManager profile immediately.
nmcli connection up "${MGMT_NIC}" || nmcli device reapply "${MGMT_NIC}"

hostnamectl
echo "---"
ip -4 addr show "${MGMT_NIC}"
echo "---"
ip route
