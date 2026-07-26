#!/usr/bin/env python3
# ============================================================
# pi_bridge.py — connects the mini data center to DataVault
#
# Run on Pi:
#   python pi_bridge.py
#
# Run on laptop (simulated mode):
#   python pi_bridge.py --simulate
# ============================================================

import os
import sys
import csv
import json
import time
import argparse
import subprocess
from datetime import datetime, timedelta
from collections import deque

# ── Configuration ─────────────────────────────────────────────
EXPORT_INTERVAL_SECONDS = 3600   # export every hour
READINGS_FILE           = "pi_readings.csv"    # live readings buffer
EXPORT_DIR              = "pi_exports"         # where hourly CSVs go
DATAVAULT_PROJECT       = "pi-datacenter"      # DataVault project name

# Anomaly thresholds
POWER_SPIKE_THRESHOLD   = 5.5    # watts — flag if Pi draws more than this
TEMP_DANGER_THRESHOLD   = 75.0   # celsius — flag if CPU hits this

# ── Reading buffer ─────────────────────────────────────────────
# Keep last 3600 readings in memory (1 per second = 1 hour)
readings_buffer = deque(maxlen=3600)

# ── Simulate sensor readings (laptop mode) ────────────────────

def simulated_reading():
    """Generate fake but realistic sensor data for testing on laptop"""
    import random
    import math
    t           = time.time()
    base_power  = 3.5 + math.sin(t / 300) * 0.8   # gentle wave
    spike       = random.random() < 0.02            # 2% chance of spike
    power       = base_power + (2.0 if spike else 0) + random.gauss(0, 0.1)
    cpu_temp    = 45 + power * 4 + random.gauss(0, 1.5)
    sink_temp   = cpu_temp - 15 + random.gauss(0, 0.5)
    teg_power   = max(0, (cpu_temp - sink_temp) * 0.008)
    fan_speed   = min(100, max(20, int((cpu_temp - 35) * 3)))

    return {
        "timestamp":      datetime.now().isoformat(),
        "pi_power_W":     round(power, 4),
        "teg_power_W":    round(teg_power, 4),
        "cpu_temp_C":     round(cpu_temp, 2),
        "heatsink_temp_C":round(sink_temp, 2),
        "thermal_delta_C":round(cpu_temp - sink_temp, 2),
        "fan_speed_pct":  fan_speed,
        "efficiency_pct": round((teg_power / power) * 100, 3) if power > 0 else 0,
        "anomaly":        spike
    }

def real_reading():
    """Read actual sensor data from the Pi (reads from shared state file)"""
    state_file = "/tmp/datavault_pi_state.json"
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        state["timestamp"] = datetime.now().isoformat()
        state["anomaly"]   = (
            state.get("pi_power_W", 0) > POWER_SPIKE_THRESHOLD or
            state.get("cpu_temp_C", 0) > TEMP_DANGER_THRESHOLD
        )
        return state
    except:
        return None

# ── DataVault integration ─────────────────────────────────────

def run_datavault(command_args):
    """Run a datavault command from Python"""
    result = subprocess.run(
        [sys.executable, "datavault.py"] + command_args,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    return result.returncode == 0, result.stdout + result.stderr

def ensure_datavault_initialized():
    """Make sure DataVault is set up for this project"""
    if not os.path.exists(".datavault"):
        success, output = run_datavault(["init", DATAVAULT_PROJECT])
        if success:
            print(f"[DataVault] Initialized project '{DATAVAULT_PROJECT}'")
        else:
            print(f"[DataVault] Init failed: {output}")
            return False
    return True

# ── CSV export ────────────────────────────────────────────────

def export_hourly_csv(readings, export_time):
    
    os.makedirs(EXPORT_DIR, exist_ok=True)

    timestamp_str = export_time.strftime("%Y-%m-%d_%H-%M")
    filename      = f"pi_power_{timestamp_str}.csv"
    filepath      = os.path.join(EXPORT_DIR, filename)

    if not readings:
        return None

    fieldnames = list(readings[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(readings)

    return filepath

def compute_hourly_stats(readings):
    """Compute summary statistics for the hour's readings"""
    if not readings:
        return {}

    powers   = [r["pi_power_W"]  for r in readings if r.get("pi_power_W")]
    temps    = [r["cpu_temp_C"]  for r in readings if r.get("cpu_temp_C")]
    teg      = [r["teg_power_W"] for r in readings if r.get("teg_power_W")]
    anomalies = sum(1 for r in readings if r.get("anomaly"))

    def safe_avg(lst): return round(sum(lst)/len(lst), 3) if lst else 0
    def safe_max(lst): return round(max(lst), 3) if lst else 0
    def safe_min(lst): return round(min(lst), 3) if lst else 0

    total_energy_Wh = safe_avg(powers) * (len(readings) / 3600)
    total_teg_Wh    = safe_avg(teg)    * (len(readings) / 3600)

    return {
        "readings":          len(readings),
        "avg_power_W":       safe_avg(powers),
        "max_power_W":       safe_max(powers),
        "min_power_W":       safe_min(powers),
        "avg_cpu_temp_C":    safe_avg(temps),
        "max_cpu_temp_C":    safe_max(temps),
        "total_energy_Wh":   round(total_energy_Wh, 6),
        "total_teg_Wh":      round(total_teg_Wh, 6),
        "heat_recovery_pct": round((total_teg_Wh/total_energy_Wh)*100, 3) if total_energy_Wh > 0 else 0,
        "anomalies":         anomalies
    }

# ── Main commit cycle ─────────────────────────────────────────

def commit_hourly_export(readings, export_time):
   
    filepath = export_hourly_csv(list(readings), export_time)
    if not filepath:
        print("[Bridge] No readings to export")
        return

    stats   = compute_hourly_stats(list(readings))
    hour_str = export_time.strftime("%Y-%m-%d %H:00")

    # Build commit message with stats
    anomaly_note = f" ⚠ {stats['anomalies']} anomalies" if stats.get("anomalies") else ""
    message = (
        f"Pi power data {hour_str} | "
        f"avg:{stats['avg_power_W']}W max:{stats['max_power_W']}W "
        f"temp:{stats['avg_cpu_temp_C']}°C "
        f"TEG:{stats['heat_recovery_pct']}% recovered"
        f"{anomaly_note}"
    )

    # Check if this file is already tracked
    history_file = ".datavault/history.json"
    csv_filename = os.path.basename(filepath)

    if os.path.exists(history_file):
        with open(history_file) as f:
            history = json.load(f)
        already_tracked = csv_filename in history.get("files", {})
    else:
        already_tracked = False

    # Add or commit
    if not already_tracked:
        success, output = run_datavault(["add", filepath, message])
        action = "Added"
    else:
        success, output = run_datavault(["commit", filepath, message])
        action = "Committed"

    if success:
        print(f"[DataVault] {action}: {csv_filename}")
        print(f"            {message}")

        # Auto-tag if anomalies detected
        if stats.get("anomalies", 0) > 0:
            # Get latest version
            with open(history_file) as f:
                hist = json.load(f)
            versions = hist["files"][csv_filename]["versions"]
            latest_v = versions[-1]["version_id"]
            run_datavault([
                "tag", filepath, latest_v,
                f"ANOMALY: {stats['anomalies']} power/temp events detected"
            ])
            print(f"[DataVault] Tagged {latest_v} with anomaly warning")

        # Verify chain after every commit
        success2, output2 = run_datavault(["chain", csv_filename])
        chain_ok = "CHAIN INTACT" in output2
        print(f"[DataVault] Chain: {'✓ intact' if chain_ok else '✗ BROKEN'}")
    else:
        print(f"[DataVault] Failed: {output}")

    return filepath, stats

# ── Main loop ─────────────────────────────────────────────────

def main(simulate=False):
    print("\n" + "="*55)
    print("   PI BRIDGE — DataVault ↔ Mini Data Center")
    print("="*55)
    print(f"  Mode:     {'SIMULATED (laptop)' if simulate else 'REAL (Raspberry Pi)'}")
    print(f"  Export:   every {EXPORT_INTERVAL_SECONDS//60} minutes")
    print(f"  Storage:  {EXPORT_DIR}/")
    print(f"  Vault:    .datavault/")
    print(f"\n  Press Ctrl+C to stop\n")

    if not ensure_datavault_initialized():
        sys.exit(1)

    next_export  = datetime.now() + timedelta(seconds=EXPORT_INTERVAL_SECONDS)
    reading_fn   = simulated_reading if simulate else real_reading
    reading_count = 0

    try:
        while True:
            # Take a reading
            reading = reading_fn()

            if reading:
                readings_buffer.append(reading)
                reading_count += 1

                # Print status every 10 readings
                if reading_count % 10 == 0:
                    r = reading
                    anomaly_flag = " ⚠" if r.get("anomaly") else ""
                    print(
                        f"  [{datetime.now().strftime('%H:%M:%S')}] "
                        f"power:{r['pi_power_W']:.2f}W "
                        f"temp:{r['cpu_temp_C']:.1f}°C "
                        f"TEG:{r['teg_power_W']:.4f}W "
                        f"fan:{r['fan_speed_pct']}%"
                        f"{anomaly_flag}"
                    )

            # Check if it's time to export
            now = datetime.now()
            if now >= next_export:
                print(f"\n[{now.strftime('%H:%M:%S')}] Hourly export triggered...")
                commit_hourly_export(readings_buffer, now)
                next_export = now + timedelta(seconds=EXPORT_INTERVAL_SECONDS)
                time_to_next = EXPORT_INTERVAL_SECONDS // 60
                print(f"[Bridge] Next export in {time_to_next} minutes\n")

            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\nBridge stopped.")
        print(f"  Readings collected: {reading_count}")
        print(f"  Buffer size:        {len(readings_buffer)}")

        # Final export on exit
        if len(readings_buffer) > 10:
            print(f"\nRunning final export before exit...")
            commit_hourly_export(readings_buffer, datetime.now())

        # Show vault status
        print(f"\nDataVault status:")
        run_cmd = subprocess.run(
            [sys.executable, "datavault.py", "status"],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pi Bridge — connects mini data center to DataVault")
    parser.add_argument("--simulate", action="store_true",
                        help="Run in simulation mode (no real Pi sensors needed)")
    parser.add_argument("--fast",     action="store_true",
                        help="Export every 60 seconds instead of 60 minutes (for testing)")
    args = parser.parse_args()

    if args.fast:
        EXPORT_INTERVAL_SECONDS = 60
        print("[Bridge] Fast mode: exporting every 60 seconds")

    main(simulate=args.simulate)