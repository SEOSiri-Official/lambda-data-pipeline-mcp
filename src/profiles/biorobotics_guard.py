# src/profiles/biorobotics_guard.py
import re

MAX_X_LIMIT_MM = 200.0
MAX_Y_LIMIT_MM = 150.0
MAX_Z_LIMIT_MM = 100.0

def enforce_biorobotics_guard(gcode_command: str) -> dict:
    """Scans G-code commands against physical deck limits and safe velocity envelopes."""
    cmd = gcode_command.strip()
    violations = []
    recommendations = []
    sanitized_cmd = cmd

    if not cmd.startswith("G1"):
        return {
            "profile": "BIOROBOTICS_SAFETY_INTERLOCK",
            "status": "COMPLIANT",
            "violations_found": [],
            "recommendations": [],
            "payload": cmd
        }

    # 1. Boundary Check: X Axis
    x_match = re.search(r"X([0-9\.]+)", cmd)
    if x_match:
        x_val_str = x_match.group(1)
        x_val = float(x_val_str)
        if x_val > MAX_X_LIMIT_MM:
            violations.append("DECK_LIMIT_X_EXCEEDED")
            recommendations.append(f"Clamp X to physical boundary ({MAX_X_LIMIT_MM}mm)")
            sanitized_cmd = sanitized_cmd.replace(f"X{x_val_str}", f"X{MAX_X_LIMIT_MM}")

    # 2. Boundary Check: Y Axis
    y_match = re.search(r"Y([0-9\.]+)", cmd)
    if y_match:
        y_val_str = y_match.group(1)
        y_val = float(y_val_str)
        if y_val > MAX_Y_LIMIT_MM:
            violations.append("DECK_LIMIT_Y_EXCEEDED")
            recommendations.append(f"Clamp Y to physical boundary ({MAX_Y_LIMIT_MM}mm)")
            sanitized_cmd = sanitized_cmd.replace(f"Y{y_val_str}", f"Y{MAX_Y_LIMIT_MM}")

    # 3. Boundary Check: Z Axis
    z_match = re.search(r"Z([0-9\.]+)", cmd)
    if z_match:
        z_val_str = z_match.group(1)
        z_val = float(z_val_str)
        if z_val > MAX_Z_LIMIT_MM:
            violations.append("DECK_LIMIT_Z_EXCEEDED")
            recommendations.append(f"Clamp Z to physical boundary ({MAX_Z_LIMIT_MM}mm)")
            sanitized_cmd = sanitized_cmd.replace(f"Z{z_val_str}", f"Z{MAX_Z_LIMIT_MM}")

    # 4. Velocity Check: Feedrate
    f_match = re.search(r"F([0-9\.]+)", cmd)
    if f_match:
        f_val_str = f_match.group(1)
        f_val = float(f_val_str)
        if f_val > 1500.0:
            violations.append("EXCESSIVE_VELOCITY_CAVITATION_RISK")
            recommendations.append("Reduce feedrate to F500.0 to prevent fluid splashing")
            sanitized_cmd = sanitized_cmd.replace(f"F{f_val_str}", "F500.0")

    return {
        "profile": "BIOROBOTICS_SAFETY_INTERLOCK",
        "status": "REMEDIATED" if violations else "COMPLIANT",
        "violations_found": violations,
        "recommendations": recommendations,
        "payload": sanitized_cmd
    }
