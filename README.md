# RouterSense RPi Client

Run all of the following as the `root` user.

## Setup and run

Simply run the following (which can start/restart RouterSense):

```
./start.bash

```

## Develop

Make sure that the system service is stopped:

```
systemctl stop routersense-rpi-client
```

Edit the python files and test with

```
uv run main.py
```

You can query the system with the following commands. To get the general status, run

```
curl http://localhost:58745/status
```

To list all devices, run

```
curl -X POST http://localhost:58745/run_sql -H "Content-Type: text/plain" -d 'select * from devices;' | jq
```

If your system does not have `jq` available, you can install it with `apt install jq`.


## Contact

Questions? Ask Danny Y. Huang - [https://hdanny.org](https://hdanny.org).
