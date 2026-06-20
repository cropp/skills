# Home Assistant Actions Reference

## Call Service

The most common action — calls any HA service.

```yaml
action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
    data:
      brightness_pct: 80
      color_temp: 3000    # Kelvin: warm 2700K → cool 6500K
      transition: 2       # seconds

  - service: switch.turn_off
    target:
      entity_id: switch.coffee_maker

  - service: media_player.play_media
    target:
      entity_id: media_player.living_room_speaker
    data:
      media_content_id: "https://url-to-audio.mp3"
      media_content_type: music

  # Reload automations after editing
  - service: automation.reload
```

## Common Service Quick Reference

| Service | Use |
|---------|-----|
| `light.turn_on` | Turn on light, set brightness/color |
| `light.turn_off` | Turn off light |
| `light.toggle` | Toggle light |
| `switch.turn_on/off/toggle` | Control switches |
| `cover.open_cover/close_cover/stop_cover` | Blinds/garage/covers |
| `climate.set_temperature` | Thermostat set point |
| `climate.set_hvac_mode` | heat/cool/auto/off |
| `media_player.play_media` | Play audio/video |
| `media_player.volume_set` | Set volume 0.0–1.0 |
| `media_player.media_pause` | Pause |
| `input_boolean.turn_on/off/toggle` | Toggle helper |
| `input_number.set_value` | Set number helper |
| `input_select.select_option` | Choose dropdown |
| `notify.notify` | Send notification |
| `notify.mobile_app_<device>` | Push notification |
| `scene.turn_on` | Activate scene |
| `script.turn_on` | Run script |
| `automation.turn_on/off/trigger` | Control automations |
| `homeassistant.restart` | Restart HA |
| `homeassistant.reload_all` | Reload configs |
| `tts.speak` | Text-to-speech |

## Delay

Pause before next action:

```yaml
action:
  - service: light.turn_on
    target:
      entity_id: light.bedroom

  - delay: "00:00:30"    # HH:MM:SS

  - delay:
      hours: 0
      minutes: 5
      seconds: 30

  # Template delay
  - delay: "{{ states('input_number.delay_minutes') | int }}:00"
```

## Wait for State / Trigger

```yaml
action:
  # Wait for a state (with timeout)
  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.door
        to: "off"
    timeout: "00:05:00"
    continue_on_timeout: true   # continue even if timed out

  # Check if wait succeeded
  - condition: template
    value_template: "{{ not wait.completed }}"
  - service: notify.notify
    data:
      message: "Door still open after 5 minutes!"
```

## Variables (Set in Action)

```yaml
action:
  - variables:
      current_brightness: "{{ state_attr('light.living_room', 'brightness') }}"
      is_night: "{{ now().hour > 20 or now().hour < 7 }}"

  - service: light.turn_on
    target:
      entity_id: light.living_room
    data:
      brightness: "{% if is_night %}50{% else %}255{% endif %}"
```

## Notify (Push Notifications)

```yaml
action:
  # Generic (all configured notify platforms)
  - service: notify.notify
    data:
      message: "Motion detected in living room"
      title: "🚨 Alert"

  # Mobile app (companion app)
  - service: notify.mobile_app_johns_iphone
    data:
      message: "Someone's at the door"
      title: "Doorbell"
      data:
        push:
          sound: default
        image: /local/doorbell_snapshot.jpg

  # Persistent notification in HA UI
  - service: persistent_notification.create
    data:
      message: "Water leak detected!"
      title: "⚠️ Warning"
      notification_id: "water_leak"
```

## Scenes

```yaml
action:
  - service: scene.turn_on
    target:
      entity_id: scene.movie_time
    data:
      transition: 2   # seconds
```

## Conditionals in Actions

```yaml
# If / Else
action:
  - if:
      - condition: state
        entity_id: binary_sensor.someone_home
        state: "on"
    then:
      - service: light.turn_on
        target:
          entity_id: light.living_room
    else:
      - service: light.turn_off
        target:
          area_id: home

# Choose (multi-branch)
action:
  - choose:
      - conditions:
          - condition: state
            entity_id: input_select.mode
            state: "away"
        sequence:
          - service: alarm_control_panel.alarm_arm_away
      - conditions:
          - condition: state
            entity_id: input_select.mode
            state: "night"
        sequence:
          - service: alarm_control_panel.alarm_arm_night
    default:
      - service: alarm_control_panel.alarm_disarm
```

## Repeat

```yaml
action:
  # Count-based
  - repeat:
      count: 3
      sequence:
        - service: light.toggle
          target:
            entity_id: light.alarm_light
        - delay: "00:00:01"

  # While condition
  - repeat:
      while:
        - condition: state
          entity_id: binary_sensor.flood_sensor
          state: "on"
      sequence:
        - service: notify.mobile_app_all
          data:
            message: "Still flooding!"
        - delay: "00:05:00"

  # Until condition (do-while)
  - repeat:
      until:
        - condition: state
          entity_id: binary_sensor.door
          state: "off"
      sequence:
        - service: notify.mobile_app_john
          data:
            message: "Door still open"
        - delay: "00:01:00"
```

## Stop / Error

```yaml
action:
  # Stop automation with a reason
  - stop: "Conditions no longer valid"

  # Stop with error (visible in logs)
  - stop: "Critical: sensor unavailable"
    error: true
```

## Fire Event

```yaml
action:
  - event: MY_CUSTOM_EVENT
    event_data:
      device: "front_door"
      action: "opened"
```
