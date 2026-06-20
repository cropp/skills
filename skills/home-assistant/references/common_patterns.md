# Common Home Assistant Automation Patterns

## 1. Motion-Activated Light (with Timeout)

```yaml
alias: "Motion light — hallway"
description: "Turn on hallway light when motion detected, off after 5 minutes of no motion"
mode: restart   # Restart timer each time motion fires

trigger:
  - platform: state
    entity_id: binary_sensor.hallway_motion
    to: "on"

action:
  - service: light.turn_on
    target:
      entity_id: light.hallway
    data:
      brightness_pct: 100

  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.hallway_motion
        to: "off"
        for: "00:05:00"

  - service: light.turn_off
    target:
      entity_id: light.hallway
```

## 2. Motion Light (Day/Night Brightness)

```yaml
alias: "Motion light — adaptive brightness"
mode: restart

trigger:
  - platform: state
    entity_id: binary_sensor.living_room_motion
    to: "on"

action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
    data:
      brightness_pct: >
        {% if now().hour >= 20 or now().hour < 7 %}
          20
        {% elif now().hour >= 18 %}
          60
        {% else %}
          100
        {% endif %}

  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.living_room_motion
        to: "off"
        for: "00:10:00"

  - service: light.turn_off
    target:
      entity_id: light.living_room
```

## 3. Good Morning Routine

```yaml
alias: "Good morning routine"
description: "Runs at wake time: lights, thermostat, coffee"
mode: single

trigger:
  - platform: time
    at: input_datetime.wake_up_time   # Use a helper for adjustable time

condition:
  - condition: time
    weekday: [mon, tue, wed, thu, fri]   # Weekdays only

action:
  - parallel:
      - service: light.turn_on
        target:
          area_id: bedroom
        data:
          brightness_pct: 1
          transition: 30       # Fade up over 30 seconds
          color_temp: 2700

      - service: climate.set_temperature
        target:
          entity_id: climate.home
        data:
          temperature: 21
          hvac_mode: heat

  - delay: "00:00:30"   # Wait for fade

  - service: light.turn_on
    target:
      area_id: bedroom
    data:
      brightness_pct: 80
      transition: 120    # Continue to brighten over 2 minutes
      color_temp: 3500

  - service: switch.turn_on
    target:
      entity_id: switch.coffee_maker
```

## 4. Bedtime / Goodnight

```yaml
alias: "Goodnight"
description: "Triggered by button press or voice: secure and dim"
mode: single

trigger:
  - platform: event
    event_type: conversation_command
  - platform: state
    entity_id: input_button.goodnight
    to: "unavailable"    # Button press

action:
  # Lock doors
  - service: lock.lock
    target:
      label_id: exterior_lock

  # Arm alarm
  - service: alarm_control_panel.alarm_arm_night
    target:
      entity_id: alarm_control_panel.home

  # Turn off all lights except bedroom
  - service: light.turn_off
    target:
      area_id:
        - living_room
        - kitchen
        - hallway

  # Dim bedroom for sleep
  - service: light.turn_on
    target:
      area_id: bedroom
    data:
      brightness_pct: 5
      color_temp: 2200
      transition: 60

  - delay: "00:30:00"    # 30 min later...

  - service: light.turn_off
    target:
      area_id: bedroom
```

## 5. Door Left Open Notification

```yaml
alias: "Front door left open alert"
mode: single

trigger:
  - platform: state
    entity_id: binary_sensor.front_door
    to: "on"            # Door opened
    for: "00:05:00"     # Still open after 5 minutes

action:
  - repeat:
      while:
        - condition: state
          entity_id: binary_sensor.front_door
          state: "on"
      sequence:
        - service: notify.mobile_app_all
          data:
            title: "🚪 Door Alert"
            message: "Front door has been open for {{ (as_timestamp(now()) - as_timestamp(states.binary_sensor.front_door.last_changed)) | int // 60 }} minutes"
        - delay: "00:05:00"    # Repeat every 5 minutes
```

## 6. Presence Detection (Away/Home Modes)

```yaml
alias: "Presence — all away"
description: "When last person leaves: eco mode"
mode: single

trigger:
  - platform: state
    entity_id: group.all_persons
    to: "not_home"
    for: "00:05:00"    # All gone for 5 min (avoid false triggers)

action:
  - service: climate.set_temperature
    target:
      entity_id: climate.home
    data:
      temperature: 18
      hvac_mode: heat

  - service: light.turn_off
    target:
      area_id: home

  - service: input_boolean.turn_on
    target:
      entity_id: input_boolean.away_mode

---
alias: "Presence — someone arrived"
mode: single

trigger:
  - platform: state
    entity_id: group.all_persons
    from: "not_home"
    to: "home"

action:
  - service: climate.set_temperature
    target:
      entity_id: climate.home
    data:
      temperature: 21

  - service: input_boolean.turn_off
    target:
      entity_id: input_boolean.away_mode

  - service: light.turn_on
    target:
      area_id: living_room
    data:
      brightness_pct: 80
```

## 7. Low Battery Notification

```yaml
alias: "Battery level alerts"
description: "Daily check for low battery devices"
mode: single

trigger:
  - platform: time
    at: "09:00:00"

action:
  - variables:
      low_battery_devices: >
        {% set threshold = 20 %}
        {% set devices = [] %}
        {% for state in states.sensor %}
          {% if 'battery' in state.entity_id and state.state | int(default=100) < threshold %}
            {% set devices = devices + [state.attributes.friendly_name ~ ' (' ~ state.state ~ '%)'] %}
          {% endif %}
        {% endfor %}
        {{ devices }}

  - condition: template
    value_template: "{{ low_battery_devices | length > 0 }}"

  - service: notify.mobile_app_all
    data:
      title: "🔋 Low Battery Alert"
      message: "{{ low_battery_devices | join(', ') }}"
```

## 8. Adaptive Lighting (Manual Override Detection)

```yaml
alias: "Adaptive lighting — respect manual override"
description: "Dim lights at sunset, but skip if manually adjusted"
mode: single

trigger:
  - platform: sun
    event: sunset
    offset: "00:15:00"

condition:
  - condition: state
    entity_id: input_boolean.manual_light_override
    state: "off"

action:
  - service: light.turn_on
    target:
      area_id: living_room
    data:
      brightness_pct: 70
      color_temp: 3000
      transition: 60
```

## 9. Thermostat Schedule

```yaml
alias: "Thermostat schedule"
mode: queued

trigger:
  - platform: time
    at: "06:30:00"
    id: morning
  - platform: time
    at: "08:00:00"
    id: away
  - platform: time
    at: "17:00:00"
    id: home
  - platform: time
    at: "22:30:00"
    id: night

action:
  - choose:
      - conditions:
          - condition: trigger
            id: morning
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: climate.home
            data:
              temperature: 21
      - conditions:
          - condition: trigger
            id: away
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: climate.home
            data:
              temperature: 18
      - conditions:
          - condition: trigger
            id: home
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: climate.home
            data:
              temperature: 21
      - conditions:
          - condition: trigger
            id: night
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: climate.home
            data:
              temperature: 19
```

## 10. Security — Motion at Night

```yaml
alias: "Security — motion detected at night"
mode: single

trigger:
  - platform: state
    entity_id: binary_sensor.front_yard_motion
    to: "on"

condition:
  - condition: sun
    after: sunset
    after_offset: "00:30:00"
  - condition: state
    entity_id: alarm_control_panel.home
    state: armed_away

action:
  - service: light.turn_on
    target:
      area_id: exterior
    data:
      brightness_pct: 100

  - service: notify.mobile_app_all
    data:
      title: "🚨 Motion Alert"
      message: "Motion detected at front yard"
      data:
        push:
          sound:
            name: default
            critical: 1     # iOS critical alert — bypasses silent mode
            volume: 1.0

  - delay: "00:05:00"

  - condition: state
    entity_id: binary_sensor.front_yard_motion
    state: "off"

  - service: light.turn_off
    target:
      area_id: exterior
```
