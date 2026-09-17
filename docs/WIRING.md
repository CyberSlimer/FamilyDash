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
- Position: L (Repeatable Trigger Mode)
- This allows continuous detection

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
GPIO.setup(MOTION_PIN, GPIO.IN)

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

**Troubleshooting:**
- Always detects motion: Turn sensitivity down, check for heat sources
- Never detects motion: Check wiring, ensure jumper in L position
- Sensor not powered: Check 5V connection, ensure VCC connected

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
