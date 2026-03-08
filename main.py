import json
import logging
import subprocess
import threading
import time
from pathlib import Path

import shell_command_wrapper
import signal

# The intervals are not exact sleep durations, but the minimum time between the start of each loop iteration.
DEFAULT_LOOP_INTERVAL_SECONDS = 60
FAST_LOOP_INTERVAL_SECONDS = 10

CONTROL_DIR = Path(shell_command_wrapper.BASE_DIR) / "control"
NMAP_DIR = Path(shell_command_wrapper.BASE_DIR) / "nmap"
MDNS_DIR = Path(shell_command_wrapper.BASE_DIR) / "mdns"
SSDP_DIR = Path(shell_command_wrapper.BASE_DIR) / "ssdp"
INTERFACE_DIR = Path(shell_command_wrapper.BASE_DIR) / "interface"

TARGETED_MAC_FILE = CONTROL_DIR / "targeted_mac_address_list.txt"
CONFIG_MODE_FILE = CONTROL_DIR / "is_configuration_mode.txt"
DEBUG_LOG_FILE = Path(shell_command_wrapper.BASE_DIR) / "debug.log"

MEMORY_USE_THRESHOLD_PERCENT = 80


logger = logging.getLogger("routersense_client")

network_context = dict()
context_lock = threading.Lock()
stop_event = threading.Event()



def _setup_error_logging() -> None:

    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return

    file_handler = logging.FileHandler(DEBUG_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def _get_epoch_seconds() -> int:

    return int(time.time())


def _write_json_snapshot(output_dir: Path, payload) -> None:

    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert the epoch seconds to a human readable format
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(_get_epoch_seconds()))

    file_path = output_dir / f"{timestamp}.json"
    temp_path = output_dir / f".{file_path.name}.tmp"
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)
    temp_path.replace(file_path)



def _read_text_file_if_exists(path: Path) -> str | None:

    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def _parse_targeted_mac_list() -> list[str]:
    """
    Reads the targeted MAC address list from the control file, ignoring empty
    lines and comments.

    """
    raw = _read_text_file_if_exists(TARGETED_MAC_FILE)
    if not raw:
        return []

    targets: list[str] = []
    for line in raw.splitlines():
        item = line.strip().lower()
        if not item or item.startswith("#"):
            continue
        targets.append(item)
    return sorted(set(targets))



def _is_configuration_mode_active(default_expiry_minutes=15) -> bool:
    """
    Checks if the configuration mode file exists and is not expired based on its
    modification time.

    The central server can create this file to signal the client to enter a
    "configuration mode" where it will run its loops more frequently (e.g. every
    10 seconds instead of every 60 seconds) to provide more real-time data for
    debugging and configuration purposes. The file will be automatically deleted
    by the client after it expires to avoid stale configuration mode. If a
    technician is setting up a home, they will need to make sure to keep the
    dashboard open, which will keep refreshing the configuration mode file.

    """
    if not CONFIG_MODE_FILE.exists() or not CONFIG_MODE_FILE.is_file():
        return False

    try:
        modified_epoch = CONFIG_MODE_FILE.stat().st_mtime
    except Exception as e:
        logger.error("Failed reading modification time for configuration mode file %s: %s", CONFIG_MODE_FILE, e)
        return False

    if _get_epoch_seconds() - modified_epoch <= default_expiry_minutes * 60:
        return True

    try:
        CONFIG_MODE_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.error("Failed deleting expired configuration mode file %s: %s", CONFIG_MODE_FILE, e)

    return False


def _run_initialize_script() -> None:

    script_path = Path(__file__).with_name("initialize.bash")
    try:
        result = subprocess.run(
            ["bash", str(script_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            logger.info("initialize.bash stdout: %s", result.stdout.strip())
        if result.stderr:
            logger.info("initialize.bash stderr: %s", result.stderr.strip())
    except Exception as e:
        logger.error("Failed to run initialize script %s: %s", script_path, e)
        raise


def _dynamic_wait():
    """
    Waits for a duration based on whether configuration mode is active, or until
    the stop_event is set.

    """
    stop_event.wait(
        FAST_LOOP_INTERVAL_SECONDS
        if _is_configuration_mode_active()
        else DEFAULT_LOOP_INTERVAL_SECONDS
    )

    # Check free space on the SHM mount
    try:
        result = subprocess.run(
            ["df", "--output=pcent", "/dev/shm"],
            check=True,
            capture_output=True,
            text=True,
        )

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) >= 2:
            # Expected output:
            # Use%
            #  42%
            use_percent_str = lines[1].replace("%", "").strip()
            use_percent = int(use_percent_str)
            logger.debug("/dev/shm usage: %d%%", use_percent)
        else:
            logger.warning("Unexpected df output while checking /dev/shm usage: %r", result.stdout)

    except Exception as e:
        logger.error("Failed to check usage percent on /dev/shm: %s", e)

    if use_percent >= MEMORY_USE_THRESHOLD_PERCENT:
        stop_event.set()
        logger.error("/dev/shm usage is at %d%% and over the threshold. Emergency stop.", use_percent)
        clean_up(None, None)
        return



def _loop_mdns_ssdp() -> None:

    logger.info("Starting mDNS/SSDP loop.")

    try:
        while not stop_event.is_set():
            _loop_mdns_ssdp_helper()
            _dynamic_wait()

    except Exception as e:
        logger.error("Fatal error in mDNS/SSDP loop: %s", e)
        stop_event.set()


def _loop_mdns_ssdp_helper() -> None:

    # Make sure we have the default interface
    try:
        with context_lock:
            default_interface = network_context["default_interface"]
    except KeyError:
        return

    # Run mDNS discovery
    try:
        mdns_result = shell_command_wrapper.mdns_discover()
        _write_json_snapshot(MDNS_DIR, {'timestamp': _get_epoch_seconds(), 'data': mdns_result})
    except Exception as e:
        logger.error("mDNS discovery failed: %s", e)

    if stop_event.is_set():
        return

    # Run SSDP discovery on the default interface
    try:
        ssdp_result = shell_command_wrapper.ssdp_discover(default_interface)
        _write_json_snapshot(SSDP_DIR, {'timestamp': _get_epoch_seconds(), 'data': ssdp_result})
    except Exception as e:
        logger.error("SSDP discovery failed for interface %s: %s", default_interface, e)


def _loop_network_context() -> None:

    logger.info("Starting network context loop.")

    try:
        while not stop_event.is_set():
            _loop_network_context_helper()
            _dynamic_wait()

    except Exception as e:
        logger.error("Fatal error in network context loop: %s", e)
        stop_event.set()


def _loop_network_context_helper() -> None:

    # Get the targeted MAC address list from the control file
    targeted_mac_address_list = _parse_targeted_mac_list()
    if len(targeted_mac_address_list) == 0:
        return

    # Get interface info, including default interface, router IP, RPi IP, and
    # CIDR subnet.
    try:
        interface_info = shell_command_wrapper.get_interface_info()
    except shell_command_wrapper.NetworkError as e:
        logger.error("Failed to collect interface information: %s", e)
        stop_event.set()
        return

    _write_json_snapshot(INTERFACE_DIR, {'timestamp': _get_epoch_seconds(), 'data': interface_info})

    # Save the default interface into the network context because the SSDP thread needs it
    with context_lock:
        network_context["default_interface"] = interface_info["default_interface"]

    # Now run nmap to get the IP-MAC mapping for devices in the subnet. This is
    # needed for ARP spoofing.
    try:
        nmap_result = shell_command_wrapper.nmap(interface_info["cidr_subnet"])
    except shell_command_wrapper.NetworkError as e:
        logger.error("nmap scan failed for subnet %s: %s", interface_info.get("cidr_subnet"), e)
        stop_event.set()
        return

    if len(nmap_result) == 0:
        logger.warning("nmap scan returned no results for subnet %s", interface_info.get("cidr_subnet"))
        return

    # Save the nmap result to disk for debugging and historical reference
    _write_json_snapshot(NMAP_DIR, {'timestamp': _get_epoch_seconds(), 'data': nmap_result})

    # Translate these MAC addresses into IP addresses using the nmap result
    targeted_ip_set = set()
    for mac_address, host_dict in nmap_result.items():
        if mac_address.lower() in targeted_mac_address_list:
            ip_address = host_dict.get("ip_address")
            if ip_address:
                targeted_ip_set.add(ip_address)

    # Make sure that the router's IP is excluded from the targeted IP list, even if its MAC address is in the targeted MAC list, to avoid accidentally ARP spoofing the router against itself
    router_ip = interface_info["router_ip"]
    targeted_ip_set.discard(router_ip)

    # Convert the set to a sorted list so that the order is deterministic for a
    # given set of IPs, which helps avoid unnecessary restarts of arpspoof due
    # to list order changes
    targeted_ip_list = sorted(targeted_ip_set)

    if len(targeted_ip_list) == 0:
        return

    # Now construct the arguments for arpspoof
    arpspoof_args = {
        "default_interface": interface_info["default_interface"],
        "router_ip": interface_info["router_ip"],
        "targeted_ip_list": targeted_ip_list
    }

    # Check the previous arpspoof arguments and only restart arpspoof if something has changed (e.g. new devices discovered, or router IP changed)
    with context_lock:
        try:
            if network_context['arpspoof_args'] == arpspoof_args:
                return
        except KeyError:
            pass  # No previous args, so we will start arpspoof
        prev_arpspoof_args = network_context.setdefault("arpspoof_args", {})

    # If the arguments are the same as last time, then we can skip restarting arpspoof
    if prev_arpspoof_args == arpspoof_args:
        return

    logger.info('Starting a new instance of arpspoof with arguments: %s', arpspoof_args)
    try:
        shell_command_wrapper.arpspoof(
            arpspoof_args["default_interface"],
            arpspoof_args["router_ip"],
            arpspoof_args["targeted_ip_list"],
        )
    except Exception as e:
        logger.error(
            "Failed to start arpspoof with these arguments=%s with exception %s",
            arpspoof_args,
            e,
        )
        stop_event.set()
        return

    with context_lock:
        network_context["arpspoof_args"] = arpspoof_args

    logger.info('Starting a new instance of packet capture.')

    try:
        shell_command_wrapper.tshark(
            interface_info["default_interface"],
            targeted_mac_address_list,
        )
    except Exception as e:
        logger.error('Failed to start tshark: %s', e)
        stop_event.set()
        return



def main() -> None:

    logger.info("Starting RouterSense Raspberry Pi Client.")

    _setup_error_logging()
    _run_initialize_script()

    discover_thread = threading.Thread(
        target=_loop_mdns_ssdp,
        name="mdns-ssdp-loop",
        daemon=True,
    )
    discover_thread.start()

    network_thread = threading.Thread(
        target=_loop_network_context,
        name="network-context-loop",
        daemon=True,
    )
    network_thread.start()

    signal.signal(signal.SIGTERM, clean_up)
    signal.signal(signal.SIGINT, clean_up)

    discover_thread.join()
    network_thread.join()



def clean_up(signum, frame):

    logger.info("Received signal %s, cleaning up and exiting.", signum)

    subprocess.call(["pkill", "-9", "-f", "arpspoof"])
    subprocess.call(["pkill", "-9", "-f", "dumpcap"])
    subprocess.call(["pkill", "-9", "-f", "tshark"])

    stop_event.set()


if __name__ == "__main__":

    try:
        main()
    except Exception as e:
        logger.error("Fatal unhandled exception in main: %s", e)

