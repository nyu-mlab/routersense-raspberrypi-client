# RouterSense Lite

## Overview

RouterSense Lite runs on each Raspberry Pi as a system service and continuously captures lightweight network telemetry into shared memory (`/dev/shm`) for fast local writes.

### Update And Start Flow

1. Each Raspberry Pi has a cron job that runs the heartbeat updater every 5 minutes:
    - https://github.com/nyu-mlab/routersense-rpi-updater/blob/main/heartbeat.bash
2. The heartbeat script checks for updates on the `main` branch of this repository.
3. `start.bash` is called only when a new update is detected, and it restarts
   the RouterSense systemd service.
4. If there is no update, RouterSense is not restarted.

This avoids unnecessary restarts while still ensuring new code is deployed quickly.

### Main Entrypoints

- [start.bash](start.bash): operational entrypoint on Raspberry Pi.
  - Ensures `uv` is available.
  - Regenerates systemd config if needed.
  - Restarts `routersense-raspberrypi-client` service (which runs `main.py`)
- [main.py](main.py): service runtime entrypoint.
  - Calls [initialize.bash](initialize.bash) first.
  - Starts two continuous loops:
     - mDNS + SSDP discovery loop.
     - Interface + Nmap + ARP spoof + packet capture control loop.

### What `initialize.bash` Does

[initialize.bash](initialize.bash) prepares runtime dependencies and state:

- Creates SHM directories under `/dev/shm/routersense-lite`.
- Installs required Debian packages if missing.
- Kills old `arpspoof`, `dumpcap`, and `tshark` processes to avoid conflicts.

### Runtime Behavior

At runtime, RouterSense writes outputs to shared memory for speed:

- Nmap snapshots: `/dev/shm/routersense-lite/nmap`
- Interface snapshots: `/dev/shm/routersense-lite/interface`
- mDNS snapshots: `/dev/shm/routersense-lite/mdns`
- SSDP snapshots: `/dev/shm/routersense-lite/ssdp`
- Packet capture outputs: `/dev/shm/routersense-lite/tshark`

### Control Files (Server -> Pi)

The central server controls behavior by pushing two files over SSH into `/dev/shm/routersense-lite/control`:

1. `targeted_mac_address_list.txt`
    - One MAC address per line.
    - Defines which devices should be targeted for ARP spoofing.
2. `is_configuration_mode.txt`
    - Presence of this file enables fast-refresh mode.
    - File content is not required by current logic.
    - If file modification time is within 15 minutes, loops run in fast mode (about every 10-15 seconds).
    - If older than 15 minutes, the file is treated as expired and removed.

When configuration mode is not active, loops run at the normal interval (about every 60 seconds) to reduce load.

### Manual Operation

To start or restart RouterSense manually on a Raspberry Pi:

```bash
sudo ./start.bash
```

... which starts RouterSense as a systemd service.

Or run the following in the debugging mode (i.e., not a systemd service), which allows you to specify which MAC addresses to allow ahead of time:

```bash
sudo ./start_debugging.bash
```

## Analytics

Some sample `duckdb` queries to analyze the CSV files.

```
CREATE TEMPORARY VIEW v AS SELECT *
FROM read_csv(
    'shm-data/tshark/*.csv',
    auto_detect = false,
    header = false,
    columns = {
        'frame_time_epoch': 'DOUBLE',
        'eth_src': 'VARCHAR',
        'eth_dst': 'VARCHAR',
        'ip_src': 'VARCHAR',
        'ip_dst': 'VARCHAR',
        'tcp_srcport': 'INTEGER',
        'tcp_dstport': 'INTEGER',
        'udp_srcport': 'INTEGER',
        'udp_dstport': 'INTEGER',
        'tcp_flags_syn': 'INTEGER',
        'tcp_flags_ack': 'INTEGER',
        'tcp_flags_reset': 'INTEGER',
        'tcp_seq': 'BIGINT',
        'tcp_ack': 'BIGINT',
        'dns_qry_name': 'VARCHAR',
        'dns_a': 'VARCHAR',
        'tls_handshake_extensions_server_name': 'VARCHAR',
        'frame_len': 'INTEGER',
        'tcp_len': 'INTEGER',
        'udp_length': 'INTEGER'
    }
);

select eth_src, sum(frame_len) as byte_count from v group by eth_src;
select eth_dst, sum(frame_len) as byte_count from v group by eth_dst;

```