# RouterSense Lite

## 1. Design Philosophy

The Raspberry Pi operates as a **stateless capture and telemetry spool node** whose responsibilities are limited to:

* capture network metadata
* segment data into short-lived SHM files
* mark completed files with a `.done` suffix
* expose files for SSH pull by the central server

There is:

* no SQLite on the Pi
* no HTTP/FastAPI service
* no persistent storage
* no push from the Pi except SSH responses

All durable storage, indexing, analytics, and aggregation occur centrally.

---

## 2. High-Level Data Flow

dumpcap → tshark → rotatelogs → SHM files (.done)
↓
central server SSH pull

Discovery scans (nmap, mDNS, SSDP) follow the same pattern.

---

## 3. Raspberry Pi Design

### 3.1 SHM Directory Layout

All transient state resides in tmpfs:

/dev/shm/routersense/
packets/

nmap/
    raw/
    parsed/

mdns/
ssdp/

control/
    isConfigurationMode.txt
    mac_whitelist.txt

There are **no active vs done directories**.
Files become immutable when renamed with `.done`.

---

### 3.2 Packet Capture Pipeline

#### Extracted metadata

* epoch timestamp
* frame length
* src/dst MAC
* src/dst IP
* TCP/UDP ports
* TCP flags
* TCP reset indicator
* TCP sequence and acknowledgement numbers
* DNS request/response names
* TLS ClientHello SNI

#### Capture pipeline

Files rotate every **15 seconds** and are named using epoch time.

```bash
dumpcap -i eth0 -q -B 16 -p -w - \
| tshark -l -n -r - \
    -T fields \
    -E separator=, -E occurrence=f \
    -e frame.time_epoch \
    -e frame.len \
    -e eth.src -e eth.dst \
    -e ip.src -e ip.dst \
    -e tcp.srcport -e tcp.dstport \
    -e udp.srcport -e udp.dstport \
    -e tcp.flags -e tcp.analysis.reset \
    -e tcp.seq -e tcp.ack \
    -e dns.qry.name -e dns.resp.name \
    -e tls.handshake.extensions_server_name \
| rotatelogs -l -D -p /usr/local/bin/mark_done_packets.sh \
    /dev/shm/routersense/packets/packets.%s.csv 15

Rotation uses epoch timestamp (%s).

⸻

3.3 Packet Rotation Completion Hook

#!/usr/bin/env bash
NEW="$1"
OLD="$2"

if [[ -n "${OLD:-}" && -f "$OLD" ]]; then
  mv -f "$OLD" "${OLD}.done"
fi

Only .done files are considered immutable and safe for transfer.

⸻

3.4 Nmap Scanning

Nmap produces two outputs:
	•	raw scan
	•	parsed IP→MAC mapping

Files are named with epoch timestamps and renamed with .done.

Frequencies:

Mode	Frequency
Configuration mode	15 seconds
Normal mode	60 seconds


⸻

3.5 SSDP and mDNS Scans
	•	executed every 60 seconds
	•	output snapshot files named with epoch timestamp
	•	renamed with .done upon completion

⸻

3.6 Configuration Mode

Configuration mode is determined by:

/dev/shm/routersense/control/isConfigurationMode.txt

The file contains an expiration timestamp.

Behavior:
	•	file absent → normal mode
	•	file present and unexpired → configuration mode
	•	expired → automatically deleted

Configuration mode only affects Nmap frequency.

The central server dashboard creates and updates this file.

⸻

3.7 MAC Address Whitelist

Stored at:

/dev/shm/routersense/control/mac_whitelist.txt

This is the only file pushed from the central server.

⸻

4. Central Server Design

4.1 SSH Pull Scheduler

The central server maintains persistent SSH connectivity and performs synchronization:

Mode	Poll Interval
Configuration mode	every 15 seconds
Normal mode	every 60 seconds

The central server determines the mode by reading the Pi’s configuration file.

⸻

4.2 Actions Per Poll

Each poll performs two operations:

1️⃣ Push MAC whitelist

rsync mac_whitelist.txt pi:/dev/shm/routersense/control/

This ensures updated device metadata propagates quickly.

2️⃣ Pull completed telemetry files
The central server pulls only .done files:

rsync --remove-source-files \
    pi:/dev/shm/routersense/**/*.done \
    /central/spool/<pi-id>/

This guarantees:
	•	immutable transfer
	•	bounded SHM usage
	•	natural backpressure

⸻

4.3 Cold Storage Aggregation

Every hour, small files are aggregated into Parquet:
	•	efficient DuckDB queries
	•	compressed archival storage

⸻

4.4 Hot Storage (Recent Activity Window)

A lightweight SQLite database stores only the last 10 minutes of traffic.

Schema:

timestamp
src_mac
dst_mac
bytes

Purpose:
	•	identify active devices
	•	compute send/receive volume
	•	power dashboard queries

All other metadata remains in cold storage.

⸻

5. Failure and Recovery Characteristics

Pi reboot

Only in-flight SHM files are lost.

Network outage

.done files accumulate until next pull.

Central server outage

Backlog grows but remains bounded by SHM capacity.

Capture restart

Only current segment is affected; completed segments remain intact.

⸻

6. Benefits of This Architecture
	•	extremely simple Pi runtime
	•	no flash wear
	•	immutable ingestion units
	•	deterministic recovery
	•	trivial debugging
	•	scalable across deployments
	•	no streaming queue complexity

⸻

7. Recommended Future Enhancements (optional)
	•	adaptive rotation interval under SHM pressure
	•	supervisor restart for capture failures
	•	optional compression of rotated segments
	•	dynamic scan throttling during network congestion

