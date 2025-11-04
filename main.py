import subprocess
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import uvicorn


# Create a tmpfs symlink for faster access. We want to keep the logs but only in the tmpfs to avoid excessive disk I/O.
subprocess.call("""
        mkdir -p /dev/shm/inspector/;
        rm -f tmpfs;
        ln -s /dev/shm/inspector tmpfs;
        ln -sf "$(realpath libinspector_config.json)" tmpfs/;
    """, shell=True)

# Change the current working directory to tmpfs
os.chdir('tmpfs')

# We only import libinspector after changing to tmpfs to ensure it uses the correct working directory
import libinspector.core

# Set up logging with rotation, overwriting any prior configuration set in libinspector
LOG_PATH = Path("inspector.rotating.log")

handler = RotatingFileHandler(
    LOG_PATH, mode="a",
    maxBytes=64 * 1024 * 1024,   # 64 MiB per file
    backupCount=16,              # 16 backups -> ~1 GiB total
    encoding="utf-8", delay=True
)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[handler],
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True  # override any prior basicConfig from libs
)


def main():

    setup_ssh_config()

    libinspector.core.start_threads()

    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=58745,
        workers=1,
        reload=False,
        log_config=None  # Disable uvicorn's default logging configuration
    )


def setup_ssh_config():
    """
    Adds the dashboard's SSH key to the authorized_keys file to allow passwordless SSH access.

    """
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    authorized_keys_file = ssh_dir / "authorized_keys"
    dashboard_ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC5D/K1J+bh982Ruc6iQlNL6O1CNK1n2AKFgiBLyW449UfOByeZjwPphTuJm8nonAd32B8hTJ0BRT70nadMomZfdgxR1IF7kVMcyfIpU57silj5M8I4TDiUjwE8MzfWrB6noPwsudTeaThmfV5RFmrNcX7YUr8fgIIGD5qzZ62wiRohPNFjrzsINPzOYmn2R3gVK2lhhHQCVIf+ZeCnx0ymMvuHqGolvmtkekNLgcHlnd4izILrEJuPP1SQxJvAX+xQ6NMbFRAeme6HJnhKA/L6vqwLrtoO4GfYKBiwoA2B0cYhU988uf34oBegKNkn4ZJTv886yI15sSQxp9aaNAHaBvjcpAihpergtKGtfQKsycfkmX0jEhesuYBxMdGkMNIHXIt+SESD0849WhmsxQUnwOikDQPmTLhNS6lJQU24s1AqCKfX/gnZFPG8nSne5gEPuwkITQcxKlWEq5/302qbLq56Y08xx+zcAgKOn6hDkrQHNJon/h5DE2YUG01YirU= ubuntu@danny-big-vm"

    # Check if the key is already present
    if authorized_keys_file.exists():
        with authorized_keys_file.open("r") as f:
            if dashboard_ssh_key in f.read():
                return  # Key already present

    # Append the key to the authorized_keys file
    with authorized_keys_file.open("a") as f:
        f.write(dashboard_ssh_key + "\n")



if __name__ == "__main__":
    main()
