# Hardware Wiring Guide

Complete wiring instructions for Family Dashboard hardware components.

## 🔌 Component Overview

### What You're Connecting

1. **Push Button** - Advances screens
2. **PIR Motion Sensor** - Auto wake/sleep
3. **Raspberry Pi 4** - The brain
4. **Monitor** - Display (via HDMI)

## 📍 GPIO Pin Reference

### Raspberry Pi 4 GPIO Layout

```
    Raspberry Pi 4 Model B
    
    USB-C Power      HDMI0  HDMI1  Audio
         ↓            ↓      ↓      ↓
    ┌────────────────────────────────────┐
    │                                    │
    │  3V3  1 ● ● 2  5V   ← PIR Sensor  │
    │ GPIO2 3 ● ● 4  5V                  │
    │ GPIO3 5 ● ● 6  GND  ← PIR Sensor  │
    │ GPIO4 7 ● ● 8  TX                  │
    │   GND 9 ● ●10  RX   ← Button      │
    │GPIO17 11● ●12  GPIO18              │
    │GPIO27 13● ●14  GND  ← PIR Sensor  │
    │GPIO22 15● ●16  GPIO23              │
    │  3V3 17● ●18  GPIO24              │
    │GPIO10 19● ●20  GND                 │
    │ GPIO9 21● ●22  GPIO25              │
    │GPIO11 23● ●24  GPIO8               │
    │   GND 25● ●26  GPIO7               │
    │                                    │
    │  [USB] [USB] [USB] [USB]          │
    │  [Ethernet]                        │
    │                                    │
    └────────────────────────────────────┘
```

### Pin Assignments

| Component | Connection | Physical Pin | GPIO Number |
|-----------|-----------|--------------|-------------|
| Button Signal | Signal | 11 | GPIO 17 |
| Button Ground | Ground | 9 | GND |
| PIR Sensor VCC | Power | 2 | 5V |
| PIR Sensor GND | Ground | 6 | GND |
| PIR Sensor OUT | Signal | 13 | GPIO 27 |

These are the pins this guide wires up, and the defaults in `config.env`.
They are not necessarily the pins on a Pi that ran something else first:
a board inherited from another dashboard may well have its button
somewhere else entirely.

If the button does nothing, do not guess which pin it is on - a floating
input rests HIGH exactly like a wired button does, so there is nothing to
read. Ask it instead:

```bash
sudo systemctl stop dashboard-hardware
.venv/bin/python hardware/identify-button.py
```

Press the button once. It reports the pin, writes `BUTTON_PIN` into
`config.env` and restarts the service. Pass pin numbers as arguments to
widen the search.

## 🔘 Push Button Wiring

### Parts Needed
- 1x Tactile push button
- 2x Jumper wires (Female-to-Female)

### Wiring Steps

1. **Identify Button Pins**
   - Most tactile buttons have 4 pins in 2 pairs
   - Each pair is internally connected
   - Use multimeter to identify pairs (continuity test)

2. **Connect Signal Wire**
   ```
   Button Pin → GPIO 17 (Physical Pin 11)
   Use any pin from one pair
   ```

3. **Connect Ground Wire**
   ```
   Button Pin → GND (Physical Pin 9)
   Use any pin from the OTHER pair
   ```

4. **Verify**
   - When button is pressed, GPIO 17 connects to Ground
   - Built-in pull-up resistor keeps GPIO 17 HIGH when not pressed
   - Button press pulls GPIO 17 LOW

### Capacitive touch module instead of a button

A TTP223-style touch pad is a drop-in replacement for the push button and is
easier to mount behind a panel, since nothing has to move. It takes three
wires rather than two, because it needs power:

| Module pin | Pi pin |
|---|---|
| VCC | 1 (3.3V) |
| GND | 9 (GND) |
| OUT (sometimes I/O or SIG) | 11 (GPIO 17) |

Then in `config.env`:

```
BUTTON_PIN=17
BUTTON_ACTIVE=high
```

`BUTTON_ACTIVE=high` is the part that matters and the part that is easy to
miss. A switch idles **high** and is pressed **low**; a touch pad is the
other way round, idling **low** and going **high** under a finger. The
service derives the pull resistor, the interrupt edge and the level that
counts as a press from this one setting, so with it left at `low` the pad
either does nothing or registers a press the moment the service starts.

Expected on startup:

```
Button: GPIO 17 (touch pad, active high)
```

If instead it says the pin *is not resting low*, the module is either held
down, wired to 3.3V rather than to the GPIO, or is one of the variants with
the polarity jumper set the other way.

Power it from 3.3V (pin 1), not 5V. These modules will run from either, but
at 5V the OUT pin swings to 5V too, and a Pi GPIO is not 5V tolerant.

### Button Diagram

```
         ┌─────────────┐
         │ Raspberry Pi│
         │             │
    ┌────┤ GPIO17 (11) │
    │    │             │
    │    │  GND (9)    ├────┐
    │    └─────────────┘    │
    │                       │
    │    ┌──┐ ┌──┐         │
    └────┤  └─┘  ├─────────┘
         │ Button│
         └───────┘
   
   Button Internals:
   Pin 1 ──┐    ┌── Pin 3
          Button
   Pin 2 ──┘    └── Pin 4
```

## 📡 PIR Motion Sensor Wiring

### Parts Needed
- 1x PIR Motion Sensor (HC-SR501)
- 3x Jumper wires (Female-to-Female or Male-to-Female)

### Sensor Overview

```
    HC-SR501 PIR Sensor (Back View)
    
    ┌─────────────────────────┐
    │  ○ Sensitivity Adjust   │
    │                         │
    │  ○ Time Delay Adjust    │
    │                         │
    │  ●─● Trigger Mode       │
    │  [L] [H]                │
    │  Repeatable / Single    │
    └─────────────────────────┘
    
    (Front View)
    
    ┌─────────────────────────┐
    │                         │
    │    [Fresnel Lens]       │
    │         Dome            │
    │                         │
    │  VCC  OUT  GND          │
    │   ●    ●   ●            │
    └─────────────────────────┘
```

### Wiring Steps

1. **Power (VCC)**
   ```
   Sensor VCC → 5V (Physical Pin 2)
   Usually the leftmost pin
   Red wire recommended
   ```

2. **Ground (GND)**
   ```
   Sensor GND → GND (Physical Pin 6)
   Usually the rightmost pin
   Black wire recommended
   ```

3. **Signal (OUT)**
   ```
   Sensor OUT → GPIO 27 (Physical Pin 13)
   Middle pin
   Yellow/Green wire recommended
   ```

### Sensor Configuration

**Jumper Settings:**
- Position: **H** - repeat trigger. On an HC-SR501 it is H that retriggers,
  not L; L fires once and then ignores whatever happens until its delay runs
  out.
- The service polls the pin's level once a second and reads high as "someone is
  here", so H is what keeps the output up while a person is still in the room.
  In L the dashboard would drop back to the screensaver with someone standing
  in front of it.

**Sensitivity Dial:**
- Turn clockwise for more range (3-7 meters)
- Turn counter-clockwise for less range
- Start at mid-position, adjust as needed

**Time Delay Dial:**
- Controls how long OUT stays HIGH after detection
- Turn fully counter-clockwise (minimum ~3 seconds)
- Software handles timing, not the sensor

### PIR Diagram

```
         ┌─────────────┐
         │ Raspberry Pi│
         │             │
    ┌────┤  5V (2)     │
    │    │             │
    │ ┌──┤ GPIO27 (13) │
    │ │  │             │
    │ │┌─┤  GND (6)    │
    │ ││ └─────────────┘
    │ ││
    │ ││  ┌──────────┐
    │ ││  │PIR Sensor│
    └─┼┼──┤VCC   OUT ├──┐
      ││  │       GND├──┼──┐
      │└──┤          │  │  │
      └───┤          │  │  │
          └──────────┘  │  │
                        │  │
    Detection Range ────┘  │
    (Dome direction)        │
                            │
    Ground ─────────────────┘
```

## 🔌 Complete System Wiring

### All Connections

```
    ┌──────────────────────────────────────┐
    │         Raspberry Pi 4               │
    │                                      │
    │  Pin 2  (5V)    ──────────────> PIR VCC
    │  Pin 6  (GND)   ──────────────> PIR GND
    │  Pin 9  (GND)   ──────────────> Button
    │  Pin 11 (GPIO17)──────────────> Button
    │  Pin 13 (GPIO27)──────────────> PIR OUT
    │                                      │
    │  [HDMI0] ────────────> Monitor       │
    │  [USB-C] ────────────> Power Supply  │
    │                                      │
    └──────────────────────────────────────┘
```

### Wire Color Convention (Recommended)

| Connection | Recommended Color |
|-----------|------------------|
| 5V Power | Red |
| Ground | Black |
| GPIO Signal | Yellow, Green, or Blue |

## 🧪 Testing Hardware

### Test 1: Button

```bash
# Run this test script
python3 << 'EOF'
import RPi.GPIO as GPIO
import time

BUTTON_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Testing button on GPIO 17...")
print("Press button to test (Ctrl+C to exit)")

try:
    while True:
        state = GPIO.input(BUTTON_PIN)
        if state == GPIO.LOW:
            print("✓ BUTTON PRESSED!")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nTest complete")
finally:
    GPIO.cleanup()
EOF
```

**Expected Result:**
- When button NOT pressed: No output
- When button pressed: "✓ BUTTON PRESSED!" appears

**Troubleshooting:**
- No response when pressed: Check wiring, try swapping button pins
- Always shows pressed: Button may be shorted, check connections

### Test 2: PIR Sensor

```bash
# Run this test script
python3 << 'EOF'
import RPi.GPIO as GPIO
import time

MOTION_PIN = 27

GPIO.setmode(GPIO.BCM)
# Pull-down, so a pin with no sensor on it reads LOW instead of floating HIGH.
# Without this the test prints "MOTION DETECTED!" forever whether or not
# anything is wired up, which proves nothing. The service does the same.
GPIO.setup(MOTION_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print("Testing PIR sensor on GPIO 27...")
print("Wave hand in front of sensor (Ctrl+C to exit)")

try:
    while True:
        state = GPIO.input(MOTION_PIN)
        if state == GPIO.HIGH:
            print("✓ MOTION DETECTED!")
        else:
            print("  No motion")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nTest complete")
finally:
    GPIO.cleanup()
EOF
```

**Expected Result:**
- No motion: "No motion" appears
- Motion detected: "✓ MOTION DETECTED!" appears
- LED on sensor lights up when motion detected

**Expected with no sensor connected:** "No motion", continuously. If an
unconnected GPIO 27 reports motion, the pull-down above is missing.

**Troubleshooting:**
- Always detects motion: Turn sensitivity down, check for heat sources
- Never detects motion: Check wiring, ensure jumper in H position
- Sensor not powered: Check 5V connection, ensure VCC connected
- Motion for the first minute after power-on: normal. The module settles for
  about a minute, which is why `MOTION_WARMUP` ignores the pin until then.

### What the dashboard does with it

The sensor is optional, and the only thing it changes is who can wake the wall:

| | Screensaver starts | Dashboard comes back |
|---|---|---|
| No sensor | on the idle timer | phone's Photos tab, or a working button |
| Sensor fitted | on the idle timer | automatically, when someone walks up |

Set `MOTION_PIN=off` in `config.env` to stop looking for one. The service also
gives up on a pin that reads high for six hours without a break, since that is
wiring, not a room - look for OUT landing on 3.3V instead of the GPIO.

## 🔒 Safety Guidelines

### DO's
✅ Disconnect power before wiring  
✅ Double-check connections before powering on  
✅ Use appropriate wire gauge  
✅ Keep wires neat and organized  
✅ Test components individually  
✅ Use anti-static precautions  

### DON'Ts
❌ Connect/disconnect while powered on  
❌ Connect 5V to GPIO signal pins  
❌ Short circuit power pins  
❌ Use damaged components  
❌ Exceed voltage/current ratings  
❌ Work on carpet without anti-static protection  

## 🛠️ Tools Needed

### Required
- Small flathead screwdriver (for sensor adjustments)
- Jumper wires (at least 5 wires)

### Recommended
- Multimeter (for testing continuity)
- Wire strippers (if using solid wire)
- Label maker (for labeling wires)
- Zip ties or velcro (cable management)

### Optional
- Breadboard (for prototyping)
- Soldering iron (for permanent installations)
- Heat shrink tubing
- 3D printed case/mounts

## 📐 Physical Mounting Tips

### Button Placement
- Mount on desk edge or side of monitor
- Should be easily accessible
- Consider a project enclosure box
- Use double-sided tape or drill mounting holes

### PIR Sensor Placement
- Mount 6-8 feet high for best coverage
- Point toward seating area
- Avoid aiming at windows (sun causes false triggers)
- Keep away from heaters/AC vents
- Fresnel lens should face room

### Wire Management
- Use zip ties to bundle wires
- Route wires along desk/monitor stand
- Leave slack for maintenance
- Label wires at both ends

## 🔧 Advanced: Custom PCB

For a permanent installation, consider designing a simple PCB:

### Features
- Screw terminals for sensors
- Proper pull-up/pull-down resistors
- LED indicators
- Protection diodes
- Compact design

### Layout
```
┌─────────────────────────┐
│  Family Dashboard HAT   │
│                         │
│  ┌──┐  Button Terminal │
│  └──┘  [+] [-]         │
│                         │
│  ┌──┐  PIR Terminal     │
│  └──┘  [V] [S] [G]     │
│                         │
│  ┌──┐  Power LED        │
│  ┌──┐  Motion LED       │
│                         │
│  [40-pin GPIO Header]   │
└─────────────────────────┘
```

## 📞 Hardware Support

### Common Issues

**Issue:** Button presses not detected
**Fix:** Ensure proper pull-up configuration in software

**Issue:** PIR constantly triggers
**Fix:** Adjust sensitivity pot, move away from heat

**Issue:** Intermittent connections
**Fix:** Check jumper wire quality, reseat connections

**Issue:** 5V rail not working
**Fix:** Check power supply capacity (3A+ recommended)

---

**Questions?** See README.md or TROUBLESHOOTING.md for more help.
