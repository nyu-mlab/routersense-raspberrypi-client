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
echo "16:30:2a:a2:75:b1" > "$BASE_DIR/control/targeted_mac_address_list.txt"
echo "1a:08:90:2f:51:e1" >> "$BASE_DIR/control/targeted_mac_address_list.txt"

uv run main.py
