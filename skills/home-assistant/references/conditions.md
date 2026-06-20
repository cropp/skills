# Home Assistant Conditions Reference

Conditions are optional guards — ALL must pass for the action to run.

## State Condition
```yaml
condition:
  - condition: state
    entity_id: light.living_room
    state: "on"

  # Multiple states (OR within)
  - condition: state
    entity_id: alarm_control_panel.home
    state:
      - "armed_home"
      - "armed_away"

  # Duration — must have been in this state for at least X
  - condition: state
    entity_id: binary_sensor.door
    state: "on"
    for: "00:05:00"

  # Attribute check
  - condition: state
    entity_id: media_player.tv
    attribute: source
    state: "Netflix"
```

## Numeric State Condition
```yaml
condition:
  - condition: numeric_state
    entity_id: sensor.temperature
    above: 20
    below: 28

  # Template value
  - condition: numeric_state
    entity_id: sensor.battery
    below: 20
```

## Time Condition
```yaml
condition:
  # Between two times (wraps midnight if after > before)
  - condition: time
    after: "07:00:00"
    before: "22:00:00"

  # Specific weekdays
  - condition: time
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri

  # Combined: weekdays, 8am-6pm
  - condition: time
    after: "08:00:00"
    before: "18:00:00"
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
```

## Sun Condition
```yaml
condition:
  # After sunset (it's dark)
  - condition: sun
    after: sunset
    after_offset: "00:30:00"   # 30 min after sunset

  # Before sunrise (still dark)
  - condition: sun
    before: sunrise
```

## Zone Condition
```yaml
condition:
  - condition: zone
    entity_id: person.john
    zone: zone.home
```

## Template Condition
```yaml
condition:
  - condition: template
    value_template: "{{ states('sensor.temperature') | float > 20 }}"

  # Multiple conditions in one template
  - condition: template
    value_template: >
      {{ is_state('binary_sensor.door', 'off') and
         states('sensor.humidity') | float < 80 }}
```

## AND / OR / NOT Combinators

```yaml
# AND — all must pass (default when using a list)
condition:
  - condition: state
    entity_id: binary_sensor.motion
    state: "on"
  - condition: time
    after: "07:00:00"
    before: "22:00:00"

# OR — at least one must pass
condition:
  - condition: or
    conditions:
      - condition: state
        entity_id: person.john
        state: home
      - condition: state
        entity_id: person.jane
        state: home

# NOT — inverts the condition
condition:
  - condition: not
    conditions:
      - condition: state
        entity_id: input_boolean.guest_mode
        state: "on"

# Nested AND/OR/NOT
condition:
  - condition: and
    conditions:
      - condition: time
        after: "22:00:00"
      - condition: or
        conditions:
          - condition: state
            entity_id: person.john
            state: home
          - condition: state
            entity_id: person.jane
            state: home
```

## Device Condition
```yaml
condition:
  - condition: device
    device_id: abc123def456
    domain: binary_sensor
    entity_id: binary_sensor.door_contact
    type: is_open
```

## Trigger Condition
Only passes for specific trigger IDs (useful with multiple triggers):

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.motion
    id: motion_detected
  - platform: time
    at: "22:00:00"
    id: bedtime

action:
  - choose:
      - conditions:
          - condition: trigger
            id: motion_detected
        sequence:
          - service: light.turn_on
            target:
              entity_id: light.hallway
      - conditions:
          - condition: trigger
            id: bedtime
        sequence:
          - service: light.turn_off
            target:
              area_id: living_room
```
