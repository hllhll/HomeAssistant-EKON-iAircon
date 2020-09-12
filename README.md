SmartThing users, Another guy jused developed a plugin for SmartThings ;) https://github.com/adidamty/smartthings-ekon-plugin

# Airconet+ support is BROKEN
# This is not fully tested, no responsibility whatsoever - READ Fully before installing
Using this component may effect your hass installation stability, may report falsly the state of your HVAC, commands may seem to be working but they might not (such situation where u think you turned off the ac, but it didn't)

IT MIGHT ALSO MESS APP THE REGULAR APP USAGE. In this case, you should remove the component and restart the iAircon box either by disconnecting it from the supply of the of the AC Controller and reconnect (i.e. the phone cord that doesn't go to the screen). Or by triping the switch in the electrical panel.

**The integration was only tested against ["Tadiran connect" from Ekon](https://play.google.com/store/apps/details?id=com.tadiran.connect.app&hl=en) And yet to be tested for "Airconet+" app, But it should work.** For switching the app, follow the guidnce below.

# What types of HVACs? / ACs?
Short: Tadiran mini-central ACs, other iAircon/EKON/Airconet Based ACs
Long:
There's a compony out there Called EKON, They have a product named iAircon which is a esp8266 hardware device, or the marketing name 
"Airconet+" (available on play store, formerly "Airconet") that connects to the HVAC system

Unfortunately, No API or documentation exist for this cloud service. This is where this repo comes in

Israeli HVACs manefacturer "TADIRAN" Uses this ekon solution for their "Tadiran connect" product, designated for some of their "mini central hvacs"

<img src="https://g-rafa.co.il/wp-content/uploads/2017/06/tadiran1-e1498462193178-1024x609.jpg" width="512px" height="305px" />
<img src="https://lh3.googleusercontent.com/43-jwjJFMF1Q1ft6P7e6Su8wxygdrlRe1B5cY3o2dZAgACU-kYZ9Uql4cFVAuiGgdg=w1396-h686-rw" width="193px" height="343px" />

# HomeAssistant-HomeAssistant-EKON-iAircon
EKON iAircon / Tadiran climate component written in Python3 for Home Assistant.
Built on the bases of Gree Climate component for easier interfacing with HASS

## Custom Component Installation

1. Copy the custom_components folder to your own hassio /config folder.

2. **UPDATE: If you one to use Airconet, you would have to disable encryption and your password would not be secure. see below **
   Choose the server you want to work with (Airconet/Tadiran).
   If you are using Airconet app you are currently using the EKON Main server
   If you are using Tadiran connect app you are currently using (what I call) Tadiran server
3. If you want to work on a server OTHER then the one you are currently using, setup an account with the app, reset the wifi-controller-thing and pair it with the app and the new account.
   For example, you might currently be using Tadiran connect app, but this component was only tested on the main server. Install "Airconet", login/create an account, on the tadiran connect electronics thing, press and hold the reset button. The button is reachabe via a hole in the plastic under the sticker. You can also open the plastic box carefully. Hold the buttun untill the led blinks in 2 colors (blue/purpule) the box is in pairing mode, now using the Airconet app, add it to your account.
3.1. Verify that HomeAssistant server has permissions to read custom_components folder. Recommended is 0744 (read everyone, write owner)

4. In your configuration.yaml add the following:

   ```yaml
   climate: 
   - platform: ekon
     # This currently unused:
     name: Main account
     # Specify the name and password for your account
     username: my@account.com
     password: myPassword
     # This specifies the server that the component would work with, I have only tried it with EKON server (Airconet+ APP)
     # Optional, 
     # Use this if you are using "Airconet+" app - EKON main server
     # base_url defults to Airconet server
     base_url: https://www.activate-ac.com/ 
     # If you are using Tadiran Connect, use this instead
     # base_url: https://www.airconet.xyz/

     # WARNING, Enabling this next option would MAKE YOUR CEDENTIALS PRUNE TO MAN-IN-THE-MIDDLE Attack
     # Homeassistant ssl libraries has some issues with authenticating the www.activate-ac.com server SSL Certificate
     # One really bad option is to dosable ssl checks altogether, you can use this switch to do that:
     # ssl_ignore: True
   ```
5. OPTIONAL: Add info logging to this component (to see if/how it works)
  
   ```yaml
   logger:
     default: error
     logs:
       custom_components.ekon: debug
   ```
6. OPTIONAL: Add entity names for the HVACs under the user. In the climate block under the ekon platform add the following, entitiy names are assigned by their id, that is the XXX under the default HVAC name EkonXXX
   
   ```yaml
     username: ...
     password: ...
     ...
     name_mapping:
     - id: XXX
       name: MyHvac
   ```
## Troubleshooting (old, maybe usefull)
- No AC Shows up on the Frontend
  - Q: Did you configured custom UI?
    - Yes: If so you'll need to add it to your inteface (No clue how, concult the UI dox)
  - Q: Does the app your working with is working?
    - No, It says Air condition is not connected to the internet / offline (or similar):
      The integration might screw up information on the vendor's server. Restart the Wifi box should solve it (See below).
    - Yes: Are you working with Tadiran app? or with Airconet app?
      - Verify permissions on the custom_components and subfolders, best to set the read permissions to everyone. (Try 0744)
      - Tadiran: Did you switch the server url in the config file?
      - Tadiran: Try switching to Airconet app (See exactly how above Under installation-3); Btw you should anyway use the Airconet app (personal recomendation) 
      - Airconet: Verify username and password in the config. If still doesn't work, Turn on logs and send me :)
- How do I restart the wifi box?
  - Option 1: Switch the Circuit breaker for your entire AC off, wait a few seconds and turn it back on
  - Option 2: Disconnect the phone cable from the weifi box where it says "to controller" (note: NOT "to display") and connect it back. Wait a couple of minutes, The application should be working again. (Hopefully so will the extension)
