# Home Assistant Triggers Reference

## State Trigger
Fires when an entity's state changes.

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.motion_hallway
    to: "on"              # Optional: only fire on this new state
    from: "off"           # Optional: only fire from this old state
    for: "00:00:30"       # Optional: state must hold for this duration
    not_to: "unavailable" # Optional: fire unless state becomes this
```

**Tips:**
- Omit `to` and `from` to fire on any state change
- Use `for` to avoid false triggers (e.g., motion stays on for 30s)
- Works with any entity: lights, sensors, binary_sensors, switches, etc.

## Time Trigger
Fires at a specific time of day.

```yaml
trigger:
  - platform: time
    at: "07:30:00"

  # Multiple times
  - platform: time
    at:
      - "07:30:00"
      - "12:00:00"
      - "20:00:00"

  # Dynamic time from input_datetime helper
  - platform: time
    at: input_datetime.wake_up_time
```

## Time Pattern Trigger
Fires repeatedly on a pattern (like cron).

```yaml
trigger:
  - platform: time_pattern
    hours: "/1"    # Every hour
    minutes: "0"   # At :00

  # Every 15 minutes
  - platform: time_pattern
    minutes: "/15"

  # Every day at noon
  - platform: time_pattern
    hours: "12"
    minutes: "0"
    seconds: "0"
```

Values: specific number, `/N` for every N, `*` for every.

## Sun Trigger
Fires at sunrise or sunset (optionally offset).

```yaml
trigger:
  - platform: sun
    event: sunset
    offset: "-00:30:00"   # 30 min before sunset (negative = before)

  - platform: sun
    event: sunrise
    offset: "00:15:00"    # 15 min after sunrise
```

## Numeric State Trigger
Fires when a numeric sensor crosses a threshold.

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.temperature
    above: 25         # fires when value rises above 25
    below: 30         # fires when value falls below 30
    for: "00:05:00"   # must stay in range for 5 mins

  # Temperature dropped below 18
  - platform: numeric_state
    entity_id: sensor.temperature
    below: 18
```

## Zone Trigger
Fires when a person/device enters or leaves a zone.

```yaml
trigger:
  - platform: zone
    entity_id: person.john
    zone: zone.home
    event: enter      # enter | leave
```

## Webhook Trigger
Fires when your HA webhook URL is called.

```yaml
trigger:
  - platform: webhook
    webhook_id: "my_secret_webhook_id"
    allowed_methods:
      - POST
      - PUT
    local_only: false   # true = only local network
```

Webhook URL: `https://your-ha.com/api/webhook/my_secret_webhook_id`

## MQTT Trigger
Fires when a message arrives on an MQTT topic.

```yaml
trigger:
  - platform: mqtt
    topic: "home/doorbell/button"
    payload: "PRESSED"    # Optional: only fire on this payload
```

## Event Trigger
Fires on HA events.

```yaml
trigger:
  - platform: event
    event_type: call_service
    event_data:
      domain: light
      service: turn_on

  # Custom event
  - platform: event
    event_type: MY_CUSTOM_EVENT
```

## Conversation Trigger
Fires when a voice command matches.

```yaml
trigger:
  - platform: conversation
    command:
      - "turn off everything"
      - "goodnight"
```

## Calendar Trigger
Fires at the start or end of a calendar event.

```yaml
trigger:
  - platform: calendar
    entity_id: calendar.my_calendar
    event: start
    offset: "-00:15:00"  # 15 min before start
```

## Template Trigger
Fires when a template evaluates to true (with optional duration).

```yaml
trigger:
  - platform: template
    value_template: "{{ states('sensor.power') | float > 2000 }}"
    for: "00:01:00"
```

## Persistent Notification Trigger
Fires when a persistent notification is created or dismissed.

```yaml
trigger:
  - platform: persistent_notification
    update_type:
      - added
      - removed
    notification_id: "my_notification"
```

## Device Trigger
Fires on device-specific events (defined by the device's integration).

```yaml
trigger:
  - platform: device
    domain: zha
    device_id: abc123def456  # Find in HA developer tools
    type: "remote_button_short_press"
    subtype: "turn_on"
```
