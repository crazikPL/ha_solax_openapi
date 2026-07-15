"""Constants for the SolaX OpenAPI (Cloud) integration.

Read-only monitoring integration for SolaX inverters/batteries using the
new OAuth-based SolaX OpenAPI (openapi-eu.solaxcloud.com and friends),
as opposed to the older tokenId-based "Third-party Ecosystem" API.
"""
from datetime import timedelta

DOMAIN = "solax_openapi"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_REGION = "region"
CONF_PLANT_ID = "plant_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL_SECONDS = 60
MIN_SCAN_INTERVAL_SECONDS = 30  # SolaX OpenAPI has a call-rate limit; don't hammer it

REGIONS = {
    "eu": "openapi-eu.solaxcloud.com",
    "us": "openapi-us.solaxcloud.com",
    "cn": "openapi.solaxcloud.com",
}

BUSINESS_TYPE_RESIDENTIAL = 1

DEVICE_TYPE_INVERTER = 1
DEVICE_TYPE_BATTERY = 2
DEVICE_TYPE_METER = 3
DEVICE_TYPE_EV_CHARGER = 4

# Slow poll: plant/device metadata (rarely changes)
SLOW_UPDATE_INTERVAL = timedelta(minutes=30)
FAST_UPDATE_INTERVAL = timedelta(seconds=30) 

SOLAX_API_CODES = {
    10000: "Operation successful",
    10001: "Operation failed",
    11500: "System busy, please try again later",
    10200: "Operation abnormality, please see the specific message content for details",
    10400: "Request not authenticated",
    10401: "Username or password incorrect",
    10402: "Request access_token authentication failed",
    10403: "Interface has no access rights",
    10404: "Callback function not configured",
    10405: "The number of API calls has been used up",
    10406: "The API call rate has reached the upper limit, please try again later",
    10500: "User has no device data permission",
}

SOLAX_INVERTER_STATUS = {
    100: "Waiting", 101: "Self-check", 102: "Normal", 103: "Fault",
    104: "Permanent Fault Mode", 105: "Update Mode", 106: "EPS Check Mode",
    107: "EPS Mode", 108: "Self Test", 109: "Idle Mode", 110: "Standby Mode",
    111: "Pv Wake Up Bat Mode", 112: "Gen Check Mode", 113: "Gen run Mode",
    114: "RSD Standby", 130: "VPP mode", 131: "TOU-Self use", 132: "TOU-Charging",
    133: "TOU-Discharging", 134: "TOU-Battery off", 135: "TOU-Peak Shaving",
    150: "Self Use", 151: "Force Time Use", 152: "Back Up Mode",
    153: "Feedin Priority", 154: "Demand Mode", 155: "ConstPowr Mode",
    160: "OpenAdr Mode", 170: "STOP MODE", 171: "DEBUG MODE",
}

SOLAX_BATTERY_STATUS = {
    0: "Idle",
    1: "Work",
}

SOLAX_DEVICE_MODEL_INVERTER = {
    1: "X1-LX", 2: "X-Hybrid", 3: "X1-Hybrid-G3", 4: "X1-Boost/Air/Mini", 5: "X3-Hybrid-G1/G2",
    6: "X3-20K/30K", 7: "X3-MIC/PRO", 8: "X1-Smart", 9: "X1-AC", 10: "A1-Hybrid",
    11: "A1-FIT", 12: "A1", 13: "J1-ESS", 14: "X3-Hybrid-G4", 15: "X1-Hybrid-G4",
    16: "X3-MIC/PRO-G2", 17: "X1-SPT", 18: "X1-Boost-G4", 19: "A1-HYB-G2", 20: "A1-AC-G2",
    21: "A1-SMT-G2", 22: "X1-Mini-G4", 23: "X1-IES", 24: "X3-IES", 25: "X3-ULT",
    26: "X1-SMART-G2", 27: "A1-Micro 1 in 1", 28: "X1-Micro 2 in 1", 29: "X1-Micro 4 in 1",
    31: "X3-AELIO", 32: "X3-HYB-G4 PRO", 33: "X3-NEO-LV", 34: "X1-VAST", 35: "X3-IES-P",
    36: "J3-ULT-LV-16.5K", 37: "J3-ULT-30K", 38: "J1-ESS-HB-2", 39: "C3-IES", 40: "X3-IES-A",
    41: "X1-IES-A", 43: "X3-ULT-GLV", 44: "X1-MINI-G4 PLUS", 46: "X1-Reno-LV", 47: "A1-HYB-G3",
    100: "X3-FTH", 101: "X3-MGA-G2", 102: "X1-Hybrid-LV", 103: "X1-Lite-LV", 104: "X3-GRAND-HV",
    105: "X3-FORTH-PLUS",
}

SOLAX_DEVICE_MODEL_BATTERY = {
    1: "Triple Power", 2: "T-BAT",
}
