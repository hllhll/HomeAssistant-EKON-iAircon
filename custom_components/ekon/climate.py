#!/usr/bin/python
# Do basic imports
import requests
import json
import time
import importlib.util
import socket
import base64
import re
import sys
import random
import string
import websocket
from urllib import parse
import asyncio
import logging
import ssl
import binascii
import os.path
import voluptuous as vol
import threading

import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate import (ClimateEntity, PLATFORM_SCHEMA)

from homeassistant.components.climate.const import (
    HVAC_MODE_OFF, HVAC_MODE_AUTO, HVAC_MODE_COOL, HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE, FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH)

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT, ATTR_TEMPERATURE, 
    CONF_NAME, CONF_HOST, CONF_PORT, CONF_MAC, CONF_TIMEOUT, CONF_CUSTOMIZE, 
    STATE_ON, STATE_OFF, STATE_UNKNOWN, 
    TEMP_CELSIUS, PRECISION_WHOLE, PRECISION_TENTHS, )

from homeassistant.helpers.event import (async_track_state_change)
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity
from configparser import ConfigParser
from Crypto.Cipher import AES
try: import simplejson
except ImportError: import json as simplejson

REQUIREMENTS = ['']

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE

DEFAULT_NAME = 'EKON Climate'
DEFAULT_BASE_URL = "https://www.activate-ac.com/"

CONF_USERNAME = 'username'
CONF_PASSWORD = 'password'
CONF_URL_BASE = 'base_url'
CONF_WS_URL = 'ws_url'
#CONF_NAME_MAPPING_METHOD = 'name_mapping_method'
CONF_NAME_MAPPING = 'name_mapping'
CONF_SSL_IGNORE = 'ssl_ignore'
CONF_LOGIN_TYPE = 'login_type'
DEFAULT_TIMEOUT = 10

# What I recall are the min and max for the HVAC
MIN_TEMP = 16
MAX_TEMP = 30

# fixed values in ekon mode lists
HVAC_MODES = [HVAC_MODE_AUTO, HVAC_MODE_COOL, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, HVAC_MODE_OFF]

FAN_MODES = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]


LOGIN_TYPE_TADIRAN = "tadiran"
LOGIN_TYPE_AIRCONETP = "airconet+"

LOGIN_TYPES = [LOGIN_TYPE_TADIRAN, LOGIN_TYPE_AIRCONETP]


# Since we're creating a platform for integration `Climate` extend the schema
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_URL_BASE, default=DEFAULT_BASE_URL): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
    #vol.Optional(CONF_NAME_MAPPING_METHOD, default=''): cv:string
    vol.Optional(CONF_NAME_MAPPING, default=[]): cv.ensure_list,

    vol.Optional(CONF_SSL_IGNORE, default=False): cv.boolean,
    vol.Optional(CONF_LOGIN_TYPE, default=LOGIN_TYPE_TADIRAN): vol.In( LOGIN_TYPES ),
    vol.Optional(CONF_WS_URL, default="wss://www.activate-ac.com/v2"): cv.string
})

EKON_PROP_ONOFF = 'onoff' 
EKON_PROP_MODE = 'mode'
EKON_PROP_FAN = 'fan'
EKON_PROP_ENVIROMENT_TEMP = 'envTemp'
EKON_PROP_TARGET_TEMP = 'tgtTemp'

"""
    public boolean mo3405e() {
        return (this.f2619c == 1 || this.f2619c == 85) ? false : true;
    }
"""
EKON_VALUE_ON = 85
EKON_VALUE_OFF = -86 # or 1 ? or any other value then 85 ?

EKON_VALUE_FAN_LOW = 1
EKON_VALUE_FAN_MEDIUM = 2
EKON_VALUE_FAN_HIGH = 3

"""
                case R.id.mode_auto /*2131230873*/:
                    i = 51;
                    break;
                case R.id.mode_cooling /*2131230875*/:
                    i = 17;
                    break;
                case R.id.mode_dry /*2131230877*/:
                    i = 85;
                    break;
                case R.id.mode_fan /*2131230879*/:
                    i = 68;
                    break;
                case R.id.mode_heating /*2131230881*/:
                    i = 34;
                    break;
"""
EKON_VALUE_MODE_COOL = 17
EKON_VALUE_MODE_AUTO = 51
EKON_VALUE_MODE_DRY = 85
EKON_VALUE_MODE_HEAT = 34
EKON_VALUE_MODE_FAN = 68

# Note that this may not be direct translation, see the sync functions
MAP_MODE_EKON_TO_HASS = {
    EKON_VALUE_MODE_COOL: HVAC_MODE_COOL,
    EKON_VALUE_MODE_AUTO: HVAC_MODE_AUTO,
    EKON_VALUE_MODE_DRY: HVAC_MODE_DRY,
    EKON_VALUE_MODE_HEAT: HVAC_MODE_HEAT,
    EKON_VALUE_MODE_FAN: HVAC_MODE_FAN_ONLY
}

MAP_MODE_HASS_TO_EKON = {
    HVAC_MODE_COOL: EKON_VALUE_MODE_COOL,
    HVAC_MODE_AUTO: EKON_VALUE_MODE_AUTO,
    HVAC_MODE_DRY: EKON_VALUE_MODE_DRY,
    HVAC_MODE_HEAT: EKON_VALUE_MODE_HEAT,
    HVAC_MODE_FAN_ONLY: EKON_VALUE_MODE_FAN
}

"""
                case R.id.fan_auto /*2131230824*/:
                    i = 0;
                    break;
                case R.id.fan_large /*2131230825*/:
                    i = 3;
                    break;
                case R.id.fan_medium /*2131230826*/:
                    i = 2;
                    break;
                case R.id.fan_small /*2131230827*/:
                    i = 1;
                    break;
"""
MAP_FAN_EKON_TO_HASS = {
    1: FAN_LOW,
    2: FAN_MEDIUM,
    3: FAN_HIGH,
    0: FAN_AUTO
}

MAP_FAN_HASS_TO_EKON = {
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3,
    FAN_AUTO: 0
}

@asyncio.coroutine
async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info('Setting up Ekon climate platform')

    _LOGGER.info('Creating Ekon climate controller')
    controller = EkonClimateController(hass, config, async_add_devices)
    
    await controller.async_load_init_data()


class EkonClimateController():
    """Ekon user account, inside this account there are all the ACs""" 
    def __init__(self, hass, config, async_add_devices):
        # , async_add_devices, name, base_url, username, password, name_mapping

        self._http_session = requests.Session()
        self.hass = hass
        self._async_add_devices = async_add_devices
        self._name = config.get(CONF_NAME)
        self._base_url = config.get(CONF_URL_BASE)
        self._username = config.get(CONF_USERNAME)
        self._ws_sucsess = False
        self._password = config.get(CONF_PASSWORD)
        self._devices = {}
        self._name_mapping = config.get(CONF_NAME_MAPPING)

        self._ssl_ignore = config.get(CONF_SSL_IGNORE)
        self._login_type = config.get(CONF_LOGIN_TYPE)
        self._ws_url = config.get(CONF_WS_URL)

    async def async_load_init_data(self):
         # Now since I don't have a clue in how to develop inside HASS, I took some ideas and implementation from HASS-sonoff-ewelink
        if not await self.async_do_login():
            return

        devices = await self.async_query_devices()
        for dev_raw in devices:
            dev_name = "Ekon" + str(dev_raw['id'])
            # Note: I Suck @ python :P

            matching_items = list(filter(lambda x: int(x['id'])==int(dev_raw['id']), self._name_mapping))
            if len(matching_items)>0:
                dev_name = matching_items[0]['name']

            _LOGGER.info('Adding Ekon climate device to hass')
            newdev = EkonClimate(self, dev_raw['mac'], dev_raw['id'],
                dev_raw[EKON_PROP_ONOFF], dev_raw[EKON_PROP_MODE], dev_raw[EKON_PROP_FAN], dev_raw[EKON_PROP_TARGET_TEMP], dev_raw[EKON_PROP_ENVIROMENT_TEMP], dev_raw['envTempShow'], dev_raw['light'], dev_name
            )
            self._devices[dev_raw['mac']] = newdev
            self._async_add_devices([newdev])

        # Not yet implemented
        await self.async_setup_ws()

    def ws_start_ping_thread(self):
        #asyncio.get_event_loop().run_until_complete(async_ws_ping_thread)
        #self.hass.async_create_task(self.async_ws_ping_thread())
        #task = asyncio.create_task(self.async_ws_ping_thread())
        # Again, Could someone please explain how can I schedule something to run on hass in a specific time??
        #self._ws_ping_thread = threading.Thread(target=self.async_ws_ping_thread)
        self._ws_ping_thread = threading.Thread(target=lambda : self.async_ws_ping_thread())
        self._ws_ping_thread.daemon = True
        self._ws_ping_thread.start()

    def ws_start_reciver_thread(self):
        # Could someone please explain why python-websocket doesn't offer a non-blocking event-driven WS interface?
        run_forever_lambda = lambda : self._ws.run_forever()
        if(self._ssl_ignore):
            # https://github.com/websocket-client/websocket-client
            run_forever_lambda = lambda : self._ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
        self._ws_reciver_thread = threading.Thread(target=run_forever_lambda)
        self._ws_reciver_thread.daemon = True
        self._ws_reciver_thread.start()

    def ws_stop_ping_thread(self):
        self._ws_ping_thread.stop()

    def ws_stop_reciver_thread(self):
        self._ws_reciver_thread.stop()

    # @asyncio.coroutine
    def async_ws_ping_thread(self):
        time.sleep(20)
        while self._ws_sucsess:
            #await asyncio.sleep(20)
            _LOGGER.debug("Sending WS Heartbeat ping")
            self._ws.send("Hello!")
            time.sleep(20)
            
    async def async_setup_ws(self):
        headers = {}
        # SO 58866803
        headers['Sec-WebSocket-Key'] = str(base64.b64encode(bytes([random.randint(0, 255) for _ in range(16)])), 'ascii')
        headers['Sec-WebSocket-Version'] = '13'
        headers['Upgrade'] = 'websocket'
        cookies = self._http_session.cookies.get_dict()
        # Tadiran: wss://www.airconet.xyz/ws
        # Airconet+: wss://www.activate-ac.com/v2
        _LOGGER.debug("async_setup_ws() - Connecting to WebSocket ws")
        self._ws = websocket.WebSocketApp(self._ws_url, header=headers, cookie="; ".join(["%s=%s" %(i, j) for i, j in cookies.items()]),
            on_open=lambda ws: self.ws_on_open(ws), # <--- This line is changed
            on_message=lambda ws, msg: self.ws_on_message (ws, msg),
            on_error=lambda ws, error: self.ws_on_error(ws, error), # Omittable (msg -> error)
            on_close=lambda ws: self.ws_on_close(ws)  ) 
        self.ws_start_reciver_thread()
        _LOGGER.debug ("async_setup_ws - created handler and ping thread")
        return True

    def ws_on_open(self, ws):
        _LOGGER.info("ws_on_open() - WebSocket opened")
        # OK So we don't need to use polling anymore; when HVAC change we will be notified
        self._ws_sucsess = True
        # Since we're now connected, start the ping thread (Not a regular WS ping, requires data in message)
        self.ws_start_ping_thread()

    def ws_on_error(self, ws, error):
        _LOGGER.error("ws_on_error() - WS Error:")
        _LOGGER.error(error)
        self._ws_sucsess = False

    def ws_on_close(self, ws):
        # Reconnect? woot?
        _LOGGER.info("ws_on_close() - ws closed")
        self._ws_sucsess = False

        #Retry?
        _LOGGER.info("ws_on_close() - Retry WS setup?")
        self.hass.async_create_task(self.async_setup_ws())


    
    def ws_on_message(self, ws, msg):
        _LOGGER.debug('ws_on_message() - WS Got message:')
        _LOGGER.debug(msg)
        obj = json.loads(msg)
        if "deviceStatus" in obj:
            obj = obj["deviceStatus"]
        if "allOn" in obj:
            _LOGGER.debug("allOn message!")
            return
        if type(obj) == type({}):
            # Wrap json in array since refreshACsJson accepts HVAC list
            obj = list([obj])
        self.refreshACsJson(obj)

        
    
    async def async_query_devices(self):
        return await self.hass.async_add_executor_job(self.query_devices)

    # Returns JSON object
    def query_devices(self):
        """json response .... 'attachment': [< array of hvacs >]"""
        """ Each hvac is like """
        # [{'id': xxx, 'mac': 'xxxxxxxxxxxxx', 'onoff': 85, 'light': 0, 'mode': 17, 'fan': 1, 'envTemp': 23, 'envTempShow': 23, 'tgtTemp': 24}]
        url = self._base_url + '/dev/allStatus'
        result = self._http_session.get(url)
        if(result.status_code!=200):
            _LOGGER.error ("Error query_devices")
            return False
        _LOGGER.debug(result.content)
        attch = json.loads(result.content)['attachment']
        _LOGGER.info ("query_devices")
        _LOGGER.info (attch)
        return attch  

    async def async_do_login(self):
        return await self.hass.async_add_executor_job(self.do_login)

    def do_login(self):
        # Tested theory: both tadiran-login and Airconet+ login would work out of the box with @Ronen's changes
        # TODO: This would eventually break when Ekon realizes this is NOT HOW YOU DO CAPTCHA.
        captcha = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(7))
        url = self._base_url + 'j_spring_security_check'
        url_params = {
            'trialCnt': '0',
            'username': self._username,
            'password': self._password,
            'remember': 'true',
            'isServer': 'false',
            # 'device-id': '02:00:00:00:00:00',
            'logCaptchaInput': captcha,
            'mainCaptcha_val': captcha,
            'isDebug': 'tRue'
        }
        verify = True
        if self._ssl_ignore:
            verify = False
        result = self._http_session.post(url, verify=verify, params=url_params, data="")
        if(result.status_code!=200):
            _LOGGER.error('EKON Login failed! Please check credentials!')
            _LOGGER.error(result.content)
            return False
        _LOGGER.debug('EKON Login Sucsess')
        _LOGGER.debug(self._http_session.cookies)
        return True

    # json, format:  {'id': 2728, 'mac': '60019443DD92', 'onoff': 85, 'light': 0, 'mode': 17, 'fan': 1, 'envTemp': 23, 'envTempShow': 23, 'tgtTemp': 21, 'deviceType': '0', 'type': 'AC'}
    def refreshACsJson(self,json):
        for dev_raw in json:
            """Refresh the only refreshed stuff 
            'mac': _mac_addr, # We won't sync it; 1-time read.
            'onoff': onoff, 
            'mode': mode, 
            'fan': fan, 
            'envTemp': env_temp, 
            'tgtTemp': target_temp
            """
            _LOGGER.info('(controller) Refreshing HVAC Data')
            _LOGGER.debug(json)
            dev = self._devices[dev_raw['mac']]
            ekon_state = self._devices[dev_raw['mac']]._ekon_state_obj
            ekon_state[EKON_PROP_FAN] = dev_raw[EKON_PROP_FAN]
            ekon_state[EKON_PROP_ONOFF] = dev_raw[EKON_PROP_ONOFF]
            ekon_state[EKON_PROP_MODE] = dev_raw[EKON_PROP_MODE]
            ekon_state[EKON_PROP_ENVIROMENT_TEMP] = dev_raw[EKON_PROP_ENVIROMENT_TEMP]
            ekon_state[EKON_PROP_TARGET_TEMP] = dev_raw[EKON_PROP_TARGET_TEMP]
            self._devices[dev_raw['mac']].SyncEkonObjToSelf()
            # Overwrite the request-to-set values with updated one
            self._devices[dev_raw['mac']].cpy_current_to_set_to()
            self._devices[dev_raw['mac']].schedule_update_ha_state()

    def refreshACs(self):
        self.refreshACsJson( self.query_devices() )

class EkonClimateValues():
    def __init__(self):
        self._target_temperature = 0
        self._current_temperature = 0
        self._fan_mode = 0
        self._hvac_mode = 0

class EkonClimate(ClimateEntity):
    #'onoff': 85, 'light': 0, 'mode': 17, 'fan': 1, 'envTemp': 23, 'envTempShow': 23, 'tgtTemp': 24
    def __init__(self, controller, _mac_addr, id, onoff, mode, fan, target_temp, env_temp, env_temp_show, light, name):
        _LOGGER.info('Initialize the Ekon climate device')
        self._controller = controller
        self._id = id
        self._name = name
        self._mac_addr = _mac_addr

        self._target_temperature_step = 1
        # Ekon works with celsius only
        self._unit_of_measurement = TEMP_CELSIUS
        
        # The part that is synced; missing/unused/no idea: uid, env_temp_show, light
        self._ekon_state_obj = {
            'mac': _mac_addr, # We won't sync it; 1-time read.
            'onoff': onoff, 
            'mode': mode, 
            'fan': fan, 
            'envTemp': env_temp, # RO
            'tgtTemp': target_temp, # RO
        }

        # Hack? see later
        self._last_on_state=False
        if onoff != EKON_VALUE_ON:
            self._last_on_state=False
        self.SyncEkonObjToSelf()

        # For set_xxxx functions; create a shadow instance of the Ekon and local values
        self._set_values = EkonClimateValues()
        self.cpy_current_to_set_to()

    def cpy_current_to_set_to(self):
        self._set_values._target_temperature = self._target_temperature
        self._set_values._current_temperature = self._current_temperature
        self._set_values._hvac_mode = self._hvac_mode
        self._set_values._fan_mode = self._fan_mode
        self._set_obj = self._ekon_state_obj.copy()

    def SyncEkonObjToSelf(self):
        self._current_temperature = self._ekon_state_obj[EKON_PROP_ENVIROMENT_TEMP]
        self._target_temperature = self._ekon_state_obj[EKON_PROP_TARGET_TEMP]
        
        # AFAIK
        self._min_temp = 16
        self._max_temp = 32

        # Figure out HASS HVAC Mode from EKON
        ekon_onoff = self._ekon_state_obj[EKON_PROP_ONOFF]
        if ekon_onoff == EKON_VALUE_ON:
            ekon_mode = self._ekon_state_obj[EKON_PROP_MODE]
            self._hvac_mode = MAP_MODE_EKON_TO_HASS[ekon_mode]
        else:
            self._hvac_mode = HVAC_MODE_OFF
        
        self._fan_mode = MAP_FAN_EKON_TO_HASS[self._ekon_state_obj[EKON_PROP_FAN]]


    def SyncSelfToEkonObj(self):
        _LOGGER.info("SyncSelfToEkonObj")
        self._set_obj[EKON_PROP_TARGET_TEMP] = self._set_values._target_temperature

        if self._hvac_mode == HVAC_MODE_OFF:
            self._set_obj[EKON_PROP_ONOFF] = EKON_VALUE_OFF
        else:
            self._set_obj[EKON_PROP_ONOFF] = EKON_VALUE_ON
            self._set_obj[EKON_PROP_MODE] = MAP_MODE_HASS_TO_EKON[self._set_values._hvac_mode]       
        self._set_obj[EKON_PROP_FAN] = MAP_FAN_HASS_TO_EKON[self._set_values._fan_mode]

    def TurnOnOff(self, state):
        url = self._controller._base_url + 'dev/switchHvac/' + self._ekon_state_obj["mac"] + '?on='

        _LOGGER.info("onoff changed is_on: %r" % state)
        if state:
            self._last_on_state = True
            url = url + 'True'
        else:
            self._last_on_state = False
            url = url + 'False'

        result = self._controller._http_session.get(url)
        if(result.status_code!=200):
            _LOGGER.error(result.content)
            _LOGGER.error("TurnOnOff (onoff)error")
            return False
        return True
        
    def SyncAndSet(self):
        # We get here after calling code changed fan / temp / mode of self;
        self.SyncSelfToEkonObj()
        url = self._controller._base_url + 'dev/setHvac'
        # mac, onoff, mode, fan, envtemp, tgttemp, 
        _LOGGER.info('Syncing to remote, state')
        _LOGGER.info(str(json.dumps(self._ekon_state_obj)))
        result = self._controller._http_session.post(url, json=self._set_obj)
        if(result.status_code!=200):
            _LOGGER.error(result.content)
            _LOGGER.error("SyncAndSet (properties)error")
            return False
        # Damn server has delay/race condition syncing the value we just set, so that it will be the one read next time
        # In other words, if we setHvac and getDevice immidiatly, values might be the old one, so HA would look like it hadn't changed
        time.sleep(1)
        # TODO: Check response json returnCode {"returnCode":0,"values":null} ; 0 OK, -72 Device offiline; -73 see belo. other fail 
        """                 case -73:
                                StringBuilder sb = new StringBuilder();
                                sb.append("temp outrage for device ");
                                sb.append(cVar);
                                StringBuilder.m3719b(sb.toString());
                                JSONArray jSONArray = jSONObject.getJSONArray("values");
                                if (jSONArray.length() > 0) {
                                    Album a = Album.m3577a(jSONArray.getJSONObject(0));
                                    HomePageActivity.this.mo3201b().f2190a.put(a.mo3382h(), a);
                                    if (a.mo3382h().equals(HomePageActivity.this.f2352x.mo3328c())) {
                                        HomePageActivity.this.mo3084b(a);
                                        return;
                                    }
                                    return;
                                }
                                return;
                            case -72:
                                Context.m3722a(HomePageActivity.this.getString(R.string.device_offline), 0);
                                imageButton = HomePageActivity.this.f2349u;
                                break;
                            default:
                                Context.m3722a(HomePageActivity.this.getString(R.string.operation_failure), 0);
                                imageButton = HomePageActivity.this.f2349u;
                                break;
        """
        _LOGGER.info(result.content)
        return True
    
    def GetAndSync(self):
        self._controller.refreshACs()
        # Sync in
        self.SyncEkonObjToSelf()
        # Overwrite the request-to-set values with updated one
        self.cpy_current_to_set_to()

    def SendStateToAc(self, timeout):
        _LOGGER.info('Start sending state to HVAC')
        obj = {
            'mac': self._ekon_state_obj['mac'], 
            'onoff': self._ekon_state_obj['onoff'], 
            'mode': self._ekon_state_obj['mode'], 
            'fan': self._ekon_state_obj['fan'], 
            'envTemp': self._ekon_state_obj['envTemp'], 
            'tgtTemp': self._ekon_state_obj['tgtTemp']
        }
        url = self._controller._base_url + 'dev/setHvac'
        result = self._controller._http_session.post(json=obj)
        if(result.status_code!=200):
            _LOGGER.error("SendStateToAc faild")
            _LOGGER.errpr(result.content)
            return False
        return True

    @property
    def should_poll(self):
        val = not self._controller._ws_sucsess
        _LOGGER.info('should_poll():' + str(val))
        # Return the polling state.
        return val

    def update(self):
        _LOGGER.info('update()')
        # Update HA State from Device
        self.GetAndSync()

    @property
    def name(self):
        _LOGGER.info('name(): ' + str(self._name))
        # Return the name of the climate device.
        return self._name

    @property
    def temperature_unit(self):
        _LOGGER.info('temperature_unit(): ' + str(self._unit_of_measurement))
        # Return the unit of measurement.
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        _LOGGER.info('current_temperature(): ' + str(self._current_temperature))
        # Return the current temperature.
        return self._current_temperature

    @property
    def min_temp(self):
        _LOGGER.info('min_temp(): ' + str(MIN_TEMP))
        # Return the minimum temperature.
        return MIN_TEMP
        
    @property
    def max_temp(self):
        _LOGGER.info('max_temp(): ' + str(MAX_TEMP))
        # Return the maximum temperature.
        return MAX_TEMP
        
    @property
    def target_temperature(self):
        _LOGGER.info('target_temperature(): ' + str(self._target_temperature))
        # Return the temperature we try to reach.
        return self._target_temperature
        
    @property
    def target_temperature_step(self):
        _LOGGER.info('target_temperature_step(): ' + str(self._target_temperature_step))
        # Return the supported step of target temperature.
        return self._target_temperature_step

    @property
    def hvac_mode(self):
        _LOGGER.info('hvac_mode(): ' + str(self._hvac_mode))
        # Return current operation mode ie. heat, cool, idle.
        return self._hvac_mode

    @property
    def hvac_modes(self):
        _LOGGER.info('hvac_modes(): ' + str(HVAC_MODES))
        # Return the list of available operation modes.
        return HVAC_MODES

    @property
    def fan_mode(self):
        _LOGGER.info('fan_mode(): ' + str(self._fan_mode))
        # Return the fan mode.
        return self._fan_mode

    @property
    def fan_modes(self):
        _LOGGER.info('fan_list(): ' + str(FAN_MODES))
        # Return the list of available fan modes.
        return FAN_MODES
        
    @property
    def supported_features(self):
        _LOGGER.info('supported_features(): ' + str(SUPPORT_FLAGS))
        # Return the list of supported features.
        return SUPPORT_FLAGS        
 
    def set_temperature(self, **kwargs):
        _LOGGER.info('set_temperature(): ' + str(kwargs.get(ATTR_TEMPERATURE)))
        # Set new target temperatures.
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            # do nothing if temperature is none
            self._set_values._target_temperature = int(kwargs.get(ATTR_TEMPERATURE))
            self.SyncAndSet()
            # I'm not sure what this does in POLLING mode (Should poll True), But I guess it would make HASS
            # Perform a poll update() and refresh new data from the server
            self.schedule_update_ha_state()

    def set_fan_mode(self, fan):
        _LOGGER.info('set_fan_mode(): ' + str(fan))
        # Set the fan mode.
        self._set_values._fan_mode = fan
        self.SyncAndSet()
        self.schedule_update_ha_state()

    def set_hvac_mode(self, hvac_mode):
        _LOGGER.info('set_hvac_mode(): ' + str(hvac_mode))
        if hvac_mode == HVAC_MODE_OFF:
            self.TurnOnOff(False)
            return
        
        # Set new operation mode.
        prev_mode = self._hvac_mode
        self._set_values._hvac_mode = hvac_mode
        self.SyncAndSet()
        # And only after turn on? if needed
        if prev_mode==HVAC_MODE_OFF:
            # if was off, turn on after configuring mode
            self.TurnOnOff(True)

        self.schedule_update_ha_state()

    @asyncio.coroutine
    def async_added_to_hass(self):
        _LOGGER.info('Ekon climate device added to hass()')
        self.GetAndSync()
