# Home Assistant Automation YAML Reference

## Full Structure

```yaml
automation:
  alias: "Human-readable name"          # Required — shown in HA UI
  description: "What this does"         # Optional but recommended
  id: "unique_id_string"               # Optional — enables UI editing
  mode: single                          # single | restart | queued | parallel
  max: 10                              # Only for queued/parallel — max concurrent runs

  trigger:                             # What starts the automation
    - platform: <trigger_type>
      # ... trigger-specific fields

  condition:                           # Optional — ALL must pass for action to run
    - condition: <condition_type>
      # ... condition-specific fields

  action:                              # What to do
    - service: <domain.service>
      # ... action-specific fields
```

## Mode Options

| Mode | Behavior |
|------|----------|
| `single` | Only one instance runs at a time; new triggers ignored while running |
| `restart` | Running instance is stopped, new one starts |
| `queued` | New triggers queue up; run in order |
| `parallel` | Multiple instances run simultaneously |

Use `single` for most automations. Use `restart` for things like "start a timer when motion detected". Use `queued` for door notifications.

## Shorthand vs List Form

Both are valid — list form is preferred for clarity:

```yaml
# Shorthand (single trigger/condition/action)
trigger:
  platform: state
  entity_id: binary_sensor.motion

# List form (can have multiple)
trigger:
  - platform: state
    entity_id: binary_sensor.motion
  - platform: state
    entity_id: binary_sensor.motion_2
```

## Variables

Set variables for reuse across conditions and actions:

```yaml
variables:
  brightness: >
    {% if now().hour < 20 %}200{% else %}50{% endif %}

action:
  - service: light.turn_on
    data:
      brightness: "{{ brightness }}"
```

## Choose (If/Else in Actions)

```yaml
action:
  - choose:
      - conditions:
          - condition: time
            after: "07:00:00"
            before: "22:00:00"
        sequence:
          - service: light.turn_on
            data:
              brightness: 255
    default:
      - service: light.turn_on
        data:
          brightness: 50
```

## Repeat

```yaml
action:
  - repeat:
      count: 3
      sequence:
        - service: light.toggle
          target:
            entity_id: light.alarm
        - delay: "00:00:01"
```

## Parallel Actions

```yaml
action:
  - parallel:
      - service: light.turn_on
        target:
          entity_id: light.living_room
      - service: media_player.play_media
        target:
          entity_id: media_player.speaker
```

## Templates

Use `{{ }}` for expressions, `{% %}` for logic:

```yaml
# State templates
"{{ states('sensor.temperature') | float }}"
"{{ state_attr('light.living_room', 'brightness') }}"
"{{ is_state('binary_sensor.door', 'on') }}"

# Time templates
"{{ now().hour }}"
"{{ now().strftime('%H:%M') }}"
"{{ as_timestamp(now()) }}"

# Conditional
"{% if states('sensor.temp') | float > 25 %}hot{% else %}cool{% endif %}"
```

## Common Data Patterns

```yaml
# Target by entity ID
target:
  entity_id: light.living_room

# Target multiple entities
target:
  entity_id:
    - light.living_room
    - light.bedroom

# Target by area
target:
  area_id: living_room

# Target by label
target:
  label_id: outdoor

# Service data
data:
  brightness: 200           # 0-255
  brightness_pct: 80        # 0-100%
  color_temp: 4000          # Kelvin (warm ~2700K, cool ~6500K)
  rgb_color: [255, 100, 0]  # RGB
  transition: 2             # seconds
```
