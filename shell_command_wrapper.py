"""
Wrapper for shell commands to be executed in a subprocess. Checks the output
formats (in case of updated versions of the shell commands). Formats the output
into a JSON object. Uses commands defined in the `install_debian_packages.bash`
script.

"""
import subprocess
import re
import requests
import xml.etree.ElementTree as ET


# Define a regex for an IPv4 address
IPV4_REGEX = re.compile(r'(\d{1,3}\.){3}\d{1,3}')

# Where to save the output files (e.g., nmap scan results, tshark pcap files,
# etc.); same as defined in initialize.bash
BASE_DIR = "/dev/shm/routersense-lite"



class NetworkError(Exception):
    """Custom exception for network-related errors."""
    pass



def get_interface_info():
    """
    Runs `ip route get 8.8.8.8` and extracts the router's IP address, the
    default interface, and the Pi's IP address.

    Example output: `8.8.8.8 via 192.168.86.1 dev eth0 src 192.168.86.37 uid 0`

    Also runs `ip addr show <default_interface>` to get the default CIDR subnet
    of the default interface. Example output:

    `inet 192.168.86.37/24 brd 192.168.86.255 scope global dynamic noprefixroute eth0`

    ... where the CIDR subnet is `192.168.86.37/24`.

    Raises the NetworkError exception if the command fails or the output format
    is not as expected.

    Overall, returns a dictionary with the following keys:
    - router_ip: The IP address of the router (e.g., 192.168.86.1)
    - default_interface: The name of the default network interface (e.g., eth0)
    - rpi_ip: The IP address of the Raspberry Pi (e.g., 192.168.86.37)
    - cidr_subnet: The CIDR subnet of the default interface (e.g., 192.168.86.37/24)

    """
    try:
        proc_result = subprocess.run(
            ["ip", "route", "get", "8.8.8.8"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise NetworkError(f"ip route get failed: {e}")
    except FileNotFoundError:
        raise NetworkError("ip command not found")
    except Exception as e:
        raise NetworkError(f"Unexpected error: {e}")

    # Parse the output
    output = proc_result.stdout.strip().split()
    try:
        router_ip = output[2]  # The IP address after 'via'
        default_interface = output[4]  # The interface after 'dev'
        rpi_ip = output[6]  # The IP address after 'src'
    except IndexError:
        raise NetworkError(f"Unexpected output format: {proc_result.stdout}")

    # Make sure that router_ip and rpi_ip are valid IPv4 addresses
    if not IPV4_REGEX.fullmatch(router_ip):
        raise NetworkError(f"Invalid router IP address: {router_ip}")
    if not IPV4_REGEX.fullmatch(rpi_ip):
        raise NetworkError(f"Invalid Pi IP address: {rpi_ip}")

    try:
        proc_result = subprocess.run(
            ["ip", "addr", "show", default_interface],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise NetworkError(f"ip addr show failed: {e}")
    except FileNotFoundError:
        raise NetworkError("ip command not found")
    except Exception as e:
        raise NetworkError(f"Unexpected error in ip addr show: {e}")

    # Parse the output to find the CIDR subnet
    cidr_subnet = None
    for line in proc_result.stdout.strip().splitlines():
        line = line.strip()
        if line.startswith("inet "):
            # Extract the CIDR subnet which is the second word after 'inet'
            parts = line.split()
            if len(parts) >= 2:
                cidr_subnet = parts[1]  # This should be in the format '<IP address>/<prefix length>'
                # Verify that the CIDR subnet is in the form '<IP address>/<prefix length>'
                if not re.match(r'^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$', cidr_subnet):
                    raise NetworkError(f"Invalid CIDR subnet format: {cidr_subnet}")
                break
    return {
        "router_ip": router_ip,
        "default_interface": default_interface,
        "rpi_ip": rpi_ip,
        "cidr_subnet": cidr_subnet
    }



def nmap(cidr_subnet):
    """
    Runs `nmap -sn <CIDR subnet> -oX -` and discovers all the active hosts in
    the subnet.

    Returns a dictionary where the keys are the MAC addresses, and the values
    are dictionaries with IP address, OUI vendor, and PTR hostname (if
    available). For example:

    {
        "00:11:22:33:44:55": {
            "ip_address": "192.168.86.42", "vendor": "Example Vendor",
            "ptr_hostname": "example-host.local"
        }
    }

    """
    try:
        proc_result = subprocess.run(
            ["nmap", "-sn", cidr_subnet, "-oX", "-"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise NetworkError(f"nmap failed: {e}")
    except FileNotFoundError:
        raise NetworkError("nmap command not found")
    except Exception as e:
        raise NetworkError(f"Unexpected error: {e}")

    # Parse the XML output
    nmap_result_dict = dict()
    try:
        root = ET.fromstring(proc_result.stdout.strip())
        for host in root.findall('host'):
            mac_address = None
            ip_address = None
            vendor = None
            ptr_hostname = None

            for address in host.findall('address'):
                if address.get('addrtype') == 'mac':
                    mac_address = address.get('addr')
                    vendor = address.get('vendor')
                elif address.get('addrtype') == 'ipv4':
                    ip_address = address.get('addr')

            ptr_hostname_elem = host.find('hostnames/hostname')
            if ptr_hostname_elem is not None:
                # Make sure this is a PTR hostname
                if ptr_hostname_elem.get('type') == 'PTR':
                    ptr_hostname = ptr_hostname_elem.get('name')

            if mac_address:
                nmap_result_dict[mac_address] = {
                    "ip_address": ip_address,
                    "vendor": vendor,
                    "ptr_hostname": ptr_hostname
                }
    except ET.ParseError as e:
        raise NetworkError(f"Failed to parse nmap XML output: {e}")

    return nmap_result_dict



def tshark(default_interface, targeted_mac_address_list):
    """
    Starts a shell script that chains dumpcap | tshark | rotatelogs to capture
    packets from the targeted MAC addresses and save them in rotating log files.
    The log files are saved in the tshark directory defined by BASE_DIR, with
    filenames in the format "packets-%Y%m%d-%H%M%S.csv" and rotated every 15
    seconds.

    Returns the PID of the process group. To terminate, use `os.killpg(pid,
    signal.SIGKILL)` to terminate the entire process group.

    """
    if len(targeted_mac_address_list) == 0:
        raise NetworkError("Targeted MAC address list is empty")

    # Kill existing dumpcap and tshark processes to avoid conflicts
    subprocess.call(["pkill", "-9", "-f", "dumpcap"])
    subprocess.call(["pkill", "-9", "-f", "tshark"])

    capture_filter = " or ".join([f"ether host {mac}" for mac in targeted_mac_address_list])

    tshark_dir = f"{BASE_DIR}/tshark"

    tshark_script = f"""
        dumpcap -q -i {default_interface} -f "{capture_filter}" -w - \
            | tshark -l -n -r - \
                -T fields -E header=y -E separator=, -E quote=d -E occurrence=a \
                -e frame.time_epoch \
                -e eth.src -e eth.dst \
                -e ip.src -e ip.dst \
                -e tcp.srcport -e tcp.dstport \
                -e udp.srcport -e udp.dstport \
                -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset \
                -e tcp.seq -e tcp.ack \
                -e dns.qry.name -e dns.a \
                -e tls.handshake.extensions_server_name \
                -e frame.len -e tcp.len -e udp.length \
            | rotatelogs -l {tshark_dir}/packets-%Y%m%d-%H%M%S.csv 15
    """
    try:
        proc = subprocess.Popen(
            tshark_script,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        raise NetworkError(f"Failed to start tshark: {e}")

    return proc.pid



def arpspoof(default_interface, router_ip, targeted_ip_address_list, bidirectional=True):
    """
    Runs arp-spoofing on all the devices in the targeted_ip_address_list against
    the router. If bidirectional is True, spoof both the router and the device.
    If bidirectional is False, only spoof the target devices.

    """
    if len(targeted_ip_address_list) == 0:
        raise NetworkError("Targeted IP address list is empty")

    # Build the arpspoof command with multiple -t options
    command = ["arpspoof", "-i", default_interface]
    for ip in targeted_ip_address_list:
        command.extend(["-t", ip])  # Add a -t option for each target IP address

    if bidirectional:
        command.append("-r")  # Poison both hosts (host and target) to capture traffic in both directions.

    command.append(router_ip)  # The last argument is the router IP to spoof

    # Kill existing arpspoof
    subprocess.call(["pkill", "-9", "-f", "arpspoof"])

    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        raise NetworkError("arpspoof command not found")
    except Exception as e:
        raise NetworkError(f"Unexpected error: {e}")



def mdns_discover():
    """
    Runs `avahi-browse -a -t -r` and discovers all the mDNS services.

    Simply returns the raw output as a string for now, since parsing it can be
    complex and may require additional libraries.

    Raises the NetworkError exception if the command fails.

    """
    try:
        proc_result = subprocess.run(
            ["avahi-browse", "-a", "-t", "-r"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise NetworkError(f"avahi-browse failed: {e}")
    except Exception as e:
        raise NetworkError(f"Unexpected error: {e}")

    return proc_result.stdout.strip()



def ssdp_discover(default_interface):
    """
    Runs `ssdp-discover` and discovers all the resource URLs. For each URL,
    visit the URL and save the contents. Returns a dictionary of results.

    Raises the NetworkError exception if the command fails or the output format
    is not as expected.

    """
    try:
        proc_result = subprocess.run(
            ["gssdp-discover", "-i", default_interface, "--timeout", "10"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise NetworkError(f"gssdp-discover failed: {e}")
    except Exception as e:
        raise NetworkError(f"Unexpected error: {e}")

    # Parse the output
    ssdp_result_dict = dict()
    for line in proc_result.stdout.strip().splitlines():
        # Use regex to extract the URL which starts with "http://"
        url_match = re.search(r'http://\S+', line)
        if url_match:
            url = url_match.group(0)
            ssdp_result_dict[url] = None  # Initialize the value to None

    for url in ssdp_result_dict:
        try:
            response = requests.get(url, timeout=10)  # Set a timeout for the request
            response.raise_for_status()  # Raise an error for bad status codes
            ssdp_result_dict[url] = response.text  # Save the contents of the URL
        except requests.RequestException as e:
            ssdp_result_dict[url] = f"Error fetching URL: {e}"

    return ssdp_result_dict



if __name__ == "__main__":
    try:
        info = get_interface_info()
        print(info)
    except NetworkError as e:
        print(f"Error: {e}")

    import json

    print(json.dumps(nmap(info["cidr_subnet"]), indent=2))

    # print(json.dumps(ssdp_discover(info["default_interface"]), indent=2))
    print(json.dumps(mdns_discover(), indent=2))