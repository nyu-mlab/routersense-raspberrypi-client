#!/bin/bash

BASE_DIR="/dev/shm/routersense-lite"

rm -rf "$BASE_DIR"

./initialize.bash

rm -f ./shm-data
ln -s $BASE_DIR ./
mv routersense-lite shm-data

# Enter configuration mode
touch "$BASE_DIR/control/is_configuration_mode.txt"

# Add sample MAC addresses
echo "16:30:2a:a2:75:b1" > "$BASE_DIR/control/targeted_mac_address_list.txt" # Laptop
echo "1a:08:90:2f:51:e1" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Phone
echo "20:1F:3B:82:91:3D" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Chromecast
echo "EC:B5:FA:9B:F2:62" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Hue
echo "9C:76:13:13:87:7F" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Ring
echo "70:03:9F:6C:49:5E" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Smart Plug
echo "84:E3:42:61:CF:27" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Smart Plug
echo "68:C6:3A:BF:FC:77" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Smart Plug
echo "B0:FC:0D:C6:36:F3" >> "$BASE_DIR/control/targeted_mac_address_list.txt" # Amazon TV

uv run main.py
