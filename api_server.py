from fastapi import FastAPI, Request
import libinspector.global_state
import subprocess
import json
import time
import os
import re
import base64


app = FastAPI(title="RouterSense RPi API")



@app.get("/status")
def status():
    """
    Returns a JSON object with the current status of the system, including:

     - Client ID
     - CPU usage
     - System load (3 values)
     - Memory usage
     - Temperature
     - Disk space usage
     - SHM space usage
     - Ext IP Info

    """
    # Determine Client ID based on /home/piXX directories
    client_id = None
    home_dirs = os.listdir("/home")
    for d in home_dirs:
        match = re.match(r"^pi(\d{2})$", d)
        if match:
            client_id = match.group(1)
            break

    if client_id is None:
        return {"error": "Client ID not found"}

    emergency_reboot = False

    # Get CPU usage as a percentage by reading /proc/stat
    cpu_percent = get_cpu_usage_percent()

    # Get load average
    with open("/proc/loadavg") as f:
        load_avg = f.read().split()[:3]

    # Get memory consumption
    with open("/proc/meminfo") as f:
        meminfo = f.readlines()
    mem_total = int([x for x in meminfo if x.startswith("MemTotal:")][0].split()[1])
    mem_free = int([x for x in meminfo if x.startswith("MemAvailable:")][0].split()[1])
    mem_used = mem_total - mem_free
    mem_percent = (mem_used / mem_total) * 100 if mem_total else 0

    if mem_percent > 90:
        emergency_reboot = True

    # Get temperature
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        temp_milli = int(f.read().strip())
    temp_celsius = temp_milli / 1000.0

    # Get disk space usage as a percentage
    df_output = subprocess.run(['df', '/'], capture_output=True, text=True).stdout
    disk_usage_percent = int(df_output.splitlines()[1].split()[4].rstrip('%'))

    if disk_usage_percent > 90:
        emergency_reboot = True

    # Get SHM space usage as a percentage
    df_shm_output = subprocess.run(['df', '/dev/shm'], capture_output=True, text=True).stdout
    shm_usage_percent = int(df_shm_output.splitlines()[1].split()[4].rstrip('%'))

    if shm_usage_percent > 90:
        emergency_reboot = True

    if emergency_reboot:
        subprocess.run(['/usr/sbin/reboot'])

    # Get Ext IP Info
    ip_info_str = subprocess.run(['curl', base64.b64decode('aHR0cHM6Ly9hcGkuaXBpbmZvLmlvL2xpdGUvbWU/dG9rZW49OWJiN2Q2N2IwMzJhNmE=')], capture_output=True, text=True).stdout
    try:
        ip_info_dict = json.loads(ip_info_str)
    except json.JSONDecodeError:
        ip_info_dict = {"error": "Failed to parse API response"}

    # Return the status as a JSON object
    return {
        "client_id": client_id,
        "cpu_percent": cpu_percent,
        "load_average": load_avg,
        "memory_percent": int(mem_percent),
        "temperature_celsius": temp_celsius,
        "disk_usage_percent": disk_usage_percent,
        "shm_usage_percent": shm_usage_percent,
        "ext_ip_info": ip_info_dict
    }



def read_cpu():
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("cpu "):
                _, *v = line.split()
                v = list(map(int, v[:10]))
                user,nice,system,idle,iowait,irq,softirq,steal,guest,guest_nice = v
                busy = user + nice + system + irq + softirq + steal
                idle_all = idle + iowait
                return busy, busy + idle_all



def get_cpu_usage_percent():
    b1,t1 = read_cpu()
    time.sleep(1.0)
    b2,t2 = read_cpu()
    return round(100.0*(b2-b1)/(t2-t1), 1)



@app.post("/run_sql")
async def run_sql(request: Request):
    """
    Run a SQL query and returns the result. The request body should be a JSON
    object with the following keys:

     - sql_query: The SQL query to run. Required
     - params: An optional list of parameters to bind to the query.

    """
    request_dict = await request.json()
    sql_query = request_dict['sql_query']
    sql_params = request_dict.get('params', None)

    if sql_params:
        params = (sql_query, sql_params)
    else:
        params = (sql_query,)

    db_conn, rwlock = libinspector.global_state.db_conn_and_lock
    cursor = db_conn.cursor()

    result_list = []
    result_dict = {'result': result_list, 'error': None}

    with rwlock:
        try:
            for row in cursor.execute(*params):
                row_dict = dict(row)
                for k in row_dict.keys():
                    if k.endswith('_json'):
                        try:
                            # Attempt to parse JSON fields
                            row_dict[k] = json.loads(row_dict[k])
                        except Exception:
                            pass
                result_list.append(row_dict)
        except Exception as e:
            result_dict['error'] = str(e)

    cursor.close()
    return result_dict


@app.post("/run_sql_script")
async def run_sql_script(request: Request):
    """
    Run a series of SQL queries and do not return the result. The request body should be a JSON
    object of a list, where each element is a dictionary with the following keys:

     - sql_query: The SQL query to run. Required
     - params: An optional list of parameters to bind to the query.

    """
    request_list = await request.json()

    db_conn, rwlock = libinspector.global_state.db_conn_and_lock
    cursor = db_conn.cursor()

    result_dict = {'error': None}

    with rwlock:
        for request_dict in request_list:
            sql_query = request_dict['sql_query']
            sql_params = request_dict.get('params', None)
            if sql_params:
                params = (sql_query, sql_params)
            else:
                params = (sql_query,)
            try:
                cursor.execute(*params)
            except Exception as e:
                result_dict['error'] = f'Error executing query "{sql_query}": {str(e)}'

    cursor.close()
    return result_dict



if __name__ == "__main__":
    print(json.dumps(status(), indent=2))