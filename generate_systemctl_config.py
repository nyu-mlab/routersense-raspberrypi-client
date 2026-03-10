"""
Generates a systemd service configuration file for a Python application, and deploys and installs it at the systemd directory.

Must be run with root privileges, e.g.,

```
sudo $(which uv) run generate_systemctl_config.py
```

Usage: Edit the template below and run it with `uv` in the same directory as this script.

"""
import sys
import os


service_file_content = f"""
[Unit]
Description=RouterSense RaspberryPi Client
After=network.target

[Service]
ExecStart=/root/.local/bin/uv run main.py
WorkingDirectory={os.path.dirname(os.path.abspath(__file__))}
User=root
Group=root
Environment=PYTHONUNBUFFERED=1

# Restart service automatically if it crashes
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

"""

def main():

    # Check if the script is run with root privileges
    if os.geteuid() != 0:
        print("This script must be run with root privileges.")
        sys.exit(1)

    # Write the service file to the systemd directory
    systemd_dir = "/etc/systemd/system"
    service_name = "routersense-raspberrypi-client.service"
    service_file_path = os.path.join(systemd_dir, service_name)
    with open(service_file_path, "w") as f:
        f.write(service_file_content)

    # Reload systemd to recognize the new service
    os.system("systemctl daemon-reload")

    # Enable and start the service
    os.system(f"systemctl enable {service_name}")
    os.system(f"systemctl start {service_name}")


if __name__ == "__main__":
    main()