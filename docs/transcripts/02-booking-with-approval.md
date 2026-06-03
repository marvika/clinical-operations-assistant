# Example session 2 — creating an appointment (human-in-the-loop)

**Coordinator:** Create an appointment for Patricia Adams with Dr. Alice Nguyen next week as a follow-up.

🔧 **Tool call** `find_patient` `{"name": "Patricia Adams"}`

<sub>↳ result</sub>

```json
[
  {
    "patient_id": 15,
    "name": "Patricia Adams",
    "dob": "1955-04-18"
  }
]
```

🔧 **Tool call** `find_clinician` `{"name": "Alice Nguyen"}`

<sub>↳ result</sub>

```json
[
  {
    "clinician_id": 2,
    "name": "Dr. Alice Nguyen"
  }
]
```

🔧 **Tool call** `find_location` `{}`

<sub>↳ result</sub>

```json
[
  {
    "location_id": 1,
    "name": "Room 101"
  },
  {
    "location_id": 2,
    "name": "Room 202"
  }
]
```

🔧 **Tool call** `list_appointments` `{"start_time": "2025-03-17T09:00:00+00:00", "end_time": "2025-03-24T00:00:00+00:00", "clinician_id": 2}`

<sub>↳ result</sub>

```json
[
  {
    "appointment_id": 13,
    "patient_id": 15,
    "start_time": "2025-03-18T09:00:00+00:00",
    "end_time": "2025-03-18T09:30:00+00:00",
    "type": "Nephrology review",
    "clinician_id": 2,
    "location_id": 2,
    "patient_name": "Patricia Adams",
    "clinician_name": "Dr. Alice Nguyen",
    "location_name": "Room 202"
  }
]
```

🔧 **Tool call** `create_appointment` `{"patient_id": 15, "clinician_id": 2, "location_id": 1, "start_time": "2025-03-17T09:00:00+00:00", "end_time": "2025-03-17T09:30:00+00:00", "type": "Follow-up"}`

⏸ **Approval required** — `create_appointment`, display: `{"patient": "Patricia Adams", "clinician": "Dr. Alice Nguyen", "location": "Room 101"}`

✅ **Coordinator approves**

🔧 **Tool call** `find_patient` `{"name": "Patricia Adams"}`

<sub>↳ result</sub>

```json
[
  {
    "patient_id": 15,
    "name": "Patricia Adams",
    "dob": "1955-04-18"
  }
]
```

🔧 **Tool call** `find_clinician` `{"name": "Alice Nguyen"}`

<sub>↳ result</sub>

```json
[
  {
    "clinician_id": 2,
    "name": "Dr. Alice Nguyen"
  }
]
```

🔧 **Tool call** `find_location` `{}`

<sub>↳ result</sub>

```json
[
  {
    "location_id": 1,
    "name": "Room 101"
  },
  {
    "location_id": 2,
    "name": "Room 202"
  }
]
```

🔧 **Tool call** `list_appointments` `{"start_time": "2025-03-17T09:00:00+00:00", "end_time": "2025-03-24T00:00:00+00:00", "clinician_id": 2}`

<sub>↳ result</sub>

```json
[
  {
    "appointment_id": 13,
    "patient_id": 15,
    "start_time": "2025-03-18T09:00:00+00:00",
    "end_time": "2025-03-18T09:30:00+00:00",
    "type": "Nephrology review",
    "clinician_id": 2,
    "location_id": 2,
    "patient_name": "Patricia Adams",
    "clinician_name": "Dr. Alice Nguyen",
    "location_name": "Room 202"
  }
]
```

🔧 **Tool call** `create_appointment` `{"patient_id": 15, "clinician_id": 2, "location_id": 1, "start_time": "2025-03-17T09:00:00+00:00", "end_time": "2025-03-17T09:30:00+00:00", "type": "Follow-up"}`

<sub>↳ result</sub>

```json
{
  "appointment_id": 15,
  "patient_id": 15,
  "start_time": "2025-03-17T09:00:00+00:00",
  "end_time": "2025-03-17T09:30:00+00:00",
  "type": "Follow-up",
  "clinician_id": 2,
  "location_id": 1,
  "patient_name": "Patricia Adams",
  "clinician_name": "Dr. Alice Nguyen",
  "location_name": "Room 101"
}
```

**Assistant:** I have created a follow-up appointment for Patricia Adams with Dr. Alice Nguyen on Monday, March 17, 2025, at 09:00 UTC in Room 101. Let me know if you need any other assistance.

**Coordinator:** Thanks! What does Patricia's schedule look like next week now?

🔧 **Tool call** `find_patient` `{"name": "Patricia Adams"}`

<sub>↳ result</sub>

```json
[
  {
    "patient_id": 15,
    "name": "Patricia Adams",
    "dob": "1955-04-18"
  }
]
```

🔧 **Tool call** `find_clinician` `{"name": "Alice Nguyen"}`

<sub>↳ result</sub>

```json
[
  {
    "clinician_id": 2,
    "name": "Dr. Alice Nguyen"
  }
]
```

🔧 **Tool call** `find_location` `{}`

<sub>↳ result</sub>

```json
[
  {
    "location_id": 1,
    "name": "Room 101"
  },
  {
    "location_id": 2,
    "name": "Room 202"
  }
]
```

🔧 **Tool call** `list_appointments` `{"start_time": "2025-03-17T09:00:00+00:00", "end_time": "2025-03-24T00:00:00+00:00", "clinician_id": 2}`

<sub>↳ result</sub>

```json
[
  {
    "appointment_id": 13,
    "patient_id": 15,
    "start_time": "2025-03-18T09:00:00+00:00",
    "end_time": "2025-03-18T09:30:00+00:00",
    "type": "Nephrology review",
    "clinician_id": 2,
    "location_id": 2,
    "patient_name": "Patricia Adams",
    "clinician_name": "Dr. Alice Nguyen",
    "location_name": "Room 202"
  }
]
```

🔧 **Tool call** `create_appointment` `{"patient_id": 15, "clinician_id": 2, "location_id": 1, "start_time": "2025-03-17T09:00:00+00:00", "end_time": "2025-03-17T09:30:00+00:00", "type": "Follow-up"}`

<sub>↳ result</sub>

```json
{
  "appointment_id": 15,
  "patient_id": 15,
  "start_time": "2025-03-17T09:00:00+00:00",
  "end_time": "2025-03-17T09:30:00+00:00",
  "type": "Follow-up",
  "clinician_id": 2,
  "location_id": 1,
  "patient_name": "Patricia Adams",
  "clinician_name": "Dr. Alice Nguyen",
  "location_name": "Room 101"
}
```

**Assistant:** I have created a follow-up appointment for Patricia Adams with Dr. Alice Nguyen on Monday, March 17, 2025, at 09:00 UTC in Room 101. Let me know if you need any other assistance.

**Coordinator:** Thanks! What does Patricia's schedule look like next week now?

🔧 **Tool call** `list_appointments` `{"start_time": "2025-03-17T00:00:00+00:00", "end_time": "2025-03-24T00:00:00+00:00", "patient_id": 15}`

<sub>↳ result</sub>

```json
[
  {
    "appointment_id": 15,
    "patient_id": 15,
    "start_time": "2025-03-17T09:00:00+00:00",
    "end_time": "2025-03-17T09:30:00+00:00",
    "type": "Follow-up",
    "clinician_id": 2,
    "location_id": 1,
    "patient_name": "Patricia Adams",
    "clinician_name": "Dr. Alice Nguyen",
    "location_name": "Room 101"
  },
  {
    "appointment_id": 13,
    "patient_id": 15,
    "start_time": "2025-03-18T09:00:00+00:00",
    "end_time": "2025-03-18T09:30:00+00:00",
    "type": "Nephrology review",
    "clinician_id": 2,
    "location_id": 2,
    "patient_name": "Patricia Adams",
    "clinician_name": "Dr. Alice Nguyen",
    "location_name": "Room 202"
  }
]
```

**Assistant:** Patricia Adams has two appointments next week:
- Follow-up with Dr. Alice Nguyen on March 17, 2025, at 09:00 UTC in Room 101
- Nephrology review with Dr. Alice Nguyen on March 18, 2025, at 09:00 UTC in Room 202

Let me know if you need anything else.
