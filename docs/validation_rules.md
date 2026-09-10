# Data Validation Rules

The following validation rules are applied during the ETL pipeline.

| Rule ID | Validation Rule                           | Action           |
| ------- | ----------------------------------------- | ---------------- |
| DQ-001  | Timestamp cannot be NULL                  | Reject record    |
| DQ-002  | Station name cannot be NULL               | Reject record    |
| DQ-003  | Latitude must be between -90 and 90       | Reject record    |
| DQ-004  | Longitude must be between -180 and 180    | Reject record    |
| DQ-005  | Pollutant value cannot be negative        | Reject record    |
| DQ-006  | Humidity must be between 0 and 100        | Reject record    |
| DQ-007  | Rainfall cannot be negative               | Reject record    |
| DQ-008  | Wind speed cannot be negative             | Reject record    |
| DQ-009  | Duplicate observations must be identified | Remove duplicate |
| DQ-010  | Pollutant units must be standardized      | Transform unit   |

## Rejected Records

Records that fail validation are stored separately in:

```text
data/rejected/
```
