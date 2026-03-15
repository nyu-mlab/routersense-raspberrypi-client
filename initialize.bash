#!/bin/bash

# Ensure this script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script as root (e.g., using sudo)."
    exit 1
fi

# Set the system timezone to New York
timedatectl set-timezone America/New_York

BASE_DIR="/dev/shm/routersense-lite"

# Initialize the directory structure
mkdir -p "$BASE_DIR/control"
mkdir -p "$BASE_DIR/nmap"
mkdir -p "$BASE_DIR/interface"
mkdir -p "$BASE_DIR/mdns"
mkdir -p "$BASE_DIR/ssdp"
mkdir -p "$BASE_DIR/tshark"

# Enable IP forwarding to allow the Raspberry Pi to forward packets between
# interfaces, which is necessary for ARP spoofing and network scanning
sysctl -w net.ipv4.ip_forward=1

# Disable ICMP redirects to prevent the system from accepting or sending them,
# which can interfere with ARP spoofing and network scanning
sysctl -w net.ipv4.conf.all.send_redirects=0
sysctl -w net.ipv4.conf.default.send_redirects=0
sysctl -w net.ipv4.conf.all.accept_redirects=0
sysctl -w net.ipv4.conf.default.accept_redirects=0

# Kill any existing arpspoof processes to avoid conflicts
pkill -9 -f arpspoof || true

# Similarly kill off any existing dumpcap and tshark processes to avoid conflicts
pkill -9 -f dumpcap || true
pkill -9 -f tshark || true

# Enter configuration mode by default so that we may rescan the network fast upon startup
touch "$BASE_DIR/control/is_configuration_mode.txt"

# Install Debian packages required for RouterSense Lite. Check if the following
# commands are available: gssdp-discover (which comes from gupnp-tools);
# avahi-browse (from avahi-utils); nmap; arpspoof (from dsniff); tshark;
# rotatelogs (from apache2-utils). If all available, exit this script. If any is
# missing, execute this script to install them.

# First, use which to determine if the commands above are available. If any one
# is not available, run the installation script.

COMMANDS_TO_CHECK=("gssdp-discover" "avahi-browse" "nmap" "arpspoof" "tshark" "rotatelogs")
PACKAGES_TO_INSTALL="gupnp-tools avahi-utils nmap dsniff tshark apache2-utils"

MISSING=0

echo "Checking for required commands..."
for cmd in "${COMMANDS_TO_CHECK[@]}"; do
    if ! which "$cmd" > /dev/null 2>&1; then
        echo " - Command '$cmd' is not found."
        MISSING=1
    else
        echo " - Command '$cmd' is available."
    fi
done

if [ "$MISSING" -eq 0 ]; then
    echo "All required commands are already installed. Exiting."
    exit 0
fi


# For tshark: Answer the wireshark-common question: "Should non-superusers be
# able to capture packets?" "No" => do NOT make dumpcap setuid-root
export DEBIAN_FRONTEND=noninteractive
echo "wireshark-common wireshark-common/install-setuid boolean false" | debconf-set-selections

echo "One or more commands are missing. Installing required packages..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends $PACKAGES_TO_INSTALL

echo "Verifying installation..."
MISSING_AFTER=0
for cmd in "${COMMANDS_TO_CHECK[@]}"; do
    if ! which "$cmd" > /dev/null 2>&1; then
        echo " - Error: Command '$cmd' is still missing after installation!"
        MISSING_AFTER=1
    else
        echo " - Command '$cmd' is successfully installed."
    fi
done

if [ "$MISSING_AFTER" -eq 1 ]; then
    echo "Some packages failed to install correctly."
    exit 1
else
    echo "All packages installed successfully!"
    exit 0
fi
