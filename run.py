"""
Collect PV data from the SolarmanPV API and send Power+Energy data (W+kWh) to MQTT
"""

import argparse
import http.client
import json
import logging
import sys
import time
import mqtt

logging.basicConfig(level=logging.INFO)


def load_config(file):
    """
    Load configuration
    :return:
    """
    with open(file, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
        return config


def today():
    """
    Return date in YYYY-MM-DD
    :return:
    """
    date = time.strftime("%Y-%m-%d")
    return date


def get_token(url, appid, secret, username, passhash):
    """
    Get a token from the API
    :return: access_token
    """
    try:
        conn = http.client.HTTPSConnection(url)
        payload = json.dumps({
            "appSecret": secret,
            "email": username,
            "password": passhash
        })
        headers = {
            'Content-Type': 'application/json'
        }
        url = f"//account/v1.0/token?appId={appid}&language=en"
        conn.request("POST", url, payload, headers)
        res = conn.getresponse()
        data = json.loads(res.read())
        logging.debug("Received token")
        return data["access_token"]
    except Exception as error:  # pylint: disable=broad-except
        logging.error("Unable to fetch token: %s", str(error))
        sys.exit(1)

def get_station_realtime(url, stationid, token):
    """
    Return station realtime data
    :return: realtime data
    """
    conn = http.client.HTTPSConnection(url)
    payload = json.dumps({
        "stationId": stationid
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': "bearer " + token
    }
    conn.request("POST", "//station/v1.0/realTime?language=en", payload, headers)
    res = conn.getresponse()
    data = json.loads(res.read())
    return data

def get_device_current_data(url, device_sn, token):
    """
    Return device current data
    :return: current data
    """
    conn = http.client.HTTPSConnection(url)
    payload = json.dumps({
        "deviceSn": device_sn
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': "bearer " + token
    }
    conn.request("POST", "//device/v1.0/currentData?language=en", payload, headers)
    res = conn.getresponse()
    data = json.loads(res.read())
    return data

def restruct_and_separate_current_data(data):
    """
    Return restructured and separated device current data
    Original data is removed
    :return: new current data
    """
    new_data_list = {}
    if data["dataList"]
        data_list = data["dataList"]
        for i in data_list:
            del i["key"]
            name = i["name"]
            name = name.replace(" ", "_")
            del i["name"]
            new_data_list[name] = i["value"]
        del data["dataList"]
    return new_data_list

def single_run(file):
    """
    Output current watts and kilowatts
    :return:
    """
    config = load_config(file)
    token = get_token(
        config["url"],
        config["appid"],
        config["secret"],
        config["username"],
        config["passhash"]
    )

    station_data = get_station_realtime(config["url"], config["stationId"], token)
    inverter_data = get_device_current_data(config["url"], config["inverterId"], token)
    logger_data = get_device_current_data(config["url"], config["loggerId"], token)

    inverter_data_list = restruct_and_separate_current_data(inverter_data)
    logger_data_list = restruct_and_separate_current_data(logger_data)

    if config["debug"]:
        logging.info(json.dumps(station_data, indent=4, sort_keys=True))
        logging.info(json.dumps(inverter_data, indent=4, sort_keys=True))
        logging.info(json.dumps(inverter_data_list, indent=4, sort_keys=True))
        logging.info(json.dumps(logger_data, indent=4, sort_keys=True))
        logging.info(json.dumps(logger_data_list, indent=4, sort_keys=True))

    discard = ["code", "msg", "requestId", "success"]
    topic = config["mqtt"]["topic"]

    _t = time.strftime("%Y-%m-%d %H:%M:%S")
    inverter_device_state = inverter_data["deviceState"]

    if inverter_device_state == 1:
        logging.info("%s - Inverter DeviceState: %s -> Publishing MQTT...",
                     _t, inverter_device_state)
        for i in station_data:
            if i not in discard:
                mqtt.message(config["mqtt"], topic+"/station/" + i, station_data[i])

        for i in inverter_data:
            if i not in discard:
                mqtt.message(config["mqtt"], topic+"/inverter/" + i, inverter_data[i])
        mqtt.message(config["mqtt"], topic+"/inverter/attributes", json.dumps(inverter_data_list))

        for i in logger_data:
            if i not in discard:
                mqtt.message(config["mqtt"], topic+"/logger/" + i, logger_data[i])
        mqtt.message(config["mqtt"], topic+"/logger/attributes", json.dumps(logger_data_list))
    else:
        mqtt.message(config["mqtt"], topic+"/inverter/deviceState", inverter_data["deviceState"])
        mqtt.message(config["mqtt"], topic+"/logger/deviceState", logger_data["deviceState"])
        logging.info("%s - Inverter DeviceState: %s"
                     "-> Only status MQTT publish (probably offline due to nighttime shutdown)",
                     _t, inverter_device_state)

def daemon(file, interval):
    """
    Run as a daemon process
    :param file: Config file
    :param interval: Run interval in seconds
    :return:
    """
    interval = int(interval)
    logging.info("Starting daemonized with a %s seconds run interval", str(interval))
    while True:
        try:
            single_run(file)
            time.sleep(interval)
        except Exception as error:  # pylint: disable=broad-except
            logging.error("Error on start: %s", str(error))
            sys.exit(1)


def main():
    """
    Main
    :return:
    """
    parser = argparse.ArgumentParser(description="Collect data from Trannergy / Solarman API")
    parser.add_argument("-d", "--daemon",
                        action="store_true",
                        help="run as a service")
    parser.add_argument("-s", "--single",
                        action="store_true",
                        help="single run and exit")
    parser.add_argument("-i", "--interval",
                        default="300",
                        help="run interval in seconds (default 300 sec.)")
    parser.add_argument("-f", "--file",
                        default="config.json",
                        help="config file (default ./config.json)")
    parser.add_argument("-v", "--version",
                        action='version',
                        version='%(prog)s 0.0.1')
    args = parser.parse_args()
    if args.single:
        single_run(args.file)
    elif args.daemon:
        daemon(args.file, args.interval)
    else:
        parser.print_help(sys.stderr)


if __name__ == '__main__':
    main()
