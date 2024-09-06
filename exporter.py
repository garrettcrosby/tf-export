import requests
import warnings
import string
import yaml
import json
import logging
import sys
import os
import multiprocessing as mp
from itertools import islice
from datetime import datetime

warnings.filterwarnings("ignore", message="Unverified HTTPS request")


class threadfix(object):
    def __init__(self, url, api, exclude, sslVerify=False, cert=None):
        self.url = url
        self.api = api
        self.exclude = exclude
        self.sslVerify = sslVerify
        self.cert = cert
        self.appList = []
        self.allScans = {}
        self.scanDir = None

    def make_header(self):
        logging.info("Creating authentication header for API requests.\n")
        self.authHeader = {
            "Accept": "application/json",
            "Authorization": "APIKEY {0}".format(self.api),
        }

    def connect_handler(self, method, path, data=None, params=None):
        fullPath = self.url + path
        response = requests.request(
            method,
            fullPath,
            headers=self.authHeader,
            data=data,
            params=params,
            verify=self.sslVerify,
        )
        if response.ok == False:
            err_msg = (
                "There was an error! Dumping data...\n"
                "The request path was {0}\nStatus code is: {1}\n"
                "Response data: \n{2}\nContinuing program...\n".format(
                    fullPath, response.status_code, response.json()
                )
            )
            logging.error(err_msg)
        return response.json()

    def get_applications(self):
        endpoint = "/rest/latest/applications"
        r = self.connect_handler("GET", endpoint)
        logging.info("Got applications")
        apps = r["object"]
        self.appList = [x for x in apps if x["name"] not in self.exclude]

    def export(self):
        workingDir = os.getcwd()
        self.scanDir = os.path.join(workingDir, "scans")
        if not os.path.exists(self.scanDir):
            os.mkdir(self.scanDir)
        for app in self.appList:
            appName = slugify(app["name"])
            appId = app["id"]
            self.allScans[appName] = []
            logging.info("Making app dirs")
            appDir = os.path.join(self.scanDir, appName)
            if not os.path.exists(appDir):
                os.mkdir(appDir)
            logging.info(f"Getting scans for app: {appName}")
            self.get_scans(appId, appName)

    def get_scans(self, appId, appName):
        endpoint = f"/rest/latest/applications/{appId}/scans"
        r = self.connect_handler("GET", endpoint)
        scanList = r["object"]
        try:
            for scan in scanList:
                self.allScans[appName].append(scan["id"])
        except TypeError:
            logging.warning(f"No scans found for app: {appName}")

    def download_scan(self, scan, app):
        endpoint = f"/rest/latest/scans/{scan}/download/threadfix"
        r = self.connect_handler("GET", endpoint)
        scanName = f"{r['source']}_{r['updated']}_{r['collectionType']}_{scan}.json"
        scanName = scanName.replace(
            " ", "_"
        )  # get rid of spaces, particularly in scanner source
        scanName = scanName.replace(":", "-")  # format the date string
        filePath = os.path.join(self.scanDir, app, scanName)
        with open(filePath, "w") as f:
            json.dump(r, f, indent=2)

    def multi_threader(self):
        if (
            len(self.allScans) > 4
        ):  # if more than 4 apps we will multithread using 4 threads
            appList = list(self.allScans.keys())
            appChunks = app_splitter(appList)
            if (
                len(appChunks) > 4
            ):  # we had a len not divisible by 4, handle the remainder
                remainder = appChunks.pop(4)
                appChunks[3] = appChunks[3] + remainder

            p0 = mp.Process(target=self.download_scans, args=(appChunks[0],))
            p1 = mp.Process(target=self.download_scans, args=(appChunks[1],))
            p2 = mp.Process(target=self.download_scans, args=(appChunks[2],))
            p3 = mp.Process(target=self.download_scans, args=(appChunks[3],))

            p0.start()
            p1.start()
            p2.start()
            p3.start()

            p0.join()
            p1.join()
            p2.join()
            p3.join()
        else:
            self.download_scans(self.allScans)

    def download_scans(self, apps):
        for app in apps:
            logging.info(f"Getting scans for app: {app}")
            for scan in self.allScans[app]:
                self.download_scan(scan, app)


def slugify(text):
    validChars = f"-_.() {string.ascii_letters}{string.digits}"
    safeString = "".join(c for c in text if c in validChars)
    return safeString


def app_splitter(apps):
    segmentedList = []
    increment = len(apps) // 4

    def list_splitter(inputList):
        it = iter(inputList)
        for i in range(0, len(inputList), increment):
            yield [x for x in islice(it, increment)]

    for i in list_splitter(apps):
        segmentedList.append(i)

    return segmentedList


def load_config():
    with open("config.yaml", "r") as stream:
        try:
            config = yaml.safe_load(stream)
            logging.info("Config loaded. \n")
            return config["config"], config["exclude"]
        except yaml.YAMLError as exc:
            logging.critical("Could not load config, exiting!")
            print(exc)


def config_logger():
    now = datetime.now()
    now_format = now.strftime("%d-%m-%Y_%H:%M:%S")
    logging.basicConfig(
        filename="app_script_log_{0}.log".format(now_format),
        level=logging.INFO,
        filemode="w",
        force=True,
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def main():
    config_logger()
    logging.info("Logging configured.\n")
    config, exclude = load_config()
    logging.info("Config loaded!\n")
    tfix_instance = threadfix(
        config["threadfix_url"],
        config["threadfix_api_key"],
        exclude,
        sslVerify=False,
    )
    tfix_instance.make_header()
    tfix_instance.get_applications()
    tfix_instance.export()
    tfix_instance.multi_threader()


main()
