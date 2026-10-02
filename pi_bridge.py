#!/usr/bin/env python3
import os
import sys
import csv
import json
import time
import argparse
import subprocess
from datetime import datetime, timedelta
from collections import deque

EXPORT_INTERVAL_SECONDS = 3600
EXPORT_DIR              = "pi_exports"
DATAVAULT_PROJECT       = "pi-datacenter"
POWER_SPIKE_THRESHOLD   = 5.5
TEMP_DANGER_THRESHOLD   = 75.0

readings_buffer = deque(maxlen=3600)


def simulated_reading():
    import random, math
    t          = time.time()
    base_power = 3.5 + math.sin(t / 300) * 0.8
    spike      = random.random() < 0.02
    power      = base_power + (2.0 if spike else 0) + random.gauss(0, 0.1)
    cpu_temp   = 45 + power * 4 + random.gauss(0, 1.5)
    sink_temp  = cpu_temp - 15 + random.gauss(0, 0.5)
    teg_power  = max(0, (cpu_temp - sink_temp) * 0.008)
    return {
        "timestamp":       datetime.now().isoformat(),
        "pi_power_W":      round(power, 4),
        "teg_power_W":     round(teg_power, 4),
        "cpu_temp_C":      round(cpu_temp, 2),
        "heatsink_temp_C": round(sink_temp, 2),
        "thermal_delta_C": round(cpu_temp - sink_temp, 2),
        "fan_speed_pct":   min(100, max(20, int((cpu_temp - 35) * 3))),
        "efficiency_pct":  round((teg_power / power) * 100, 3) if power > 0 else 0,
        "anomaly":         spike
    }


def real_reading():
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
    except Exception:
        return None


def run_datavault(command_args):
    result = subprocess.run(
        [sys.executable, "datavault.py"] + command_args,
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    return result.returncode == 0, result.stdout + result.stderr


def ensure_datavault_initialized():
    if not os.path.exists(".datavault"):
        success, output = run_datavault(["init", DATAVAULT_PROJECT])
        if success:
            print(f"[DataVault] Initialized project '{DATAVAULT_PROJECT}'")
        else:
            print(f"[DataVault] Init failed: {output}")
            return False
    return True


def export_hourly_csv(readings, export_time):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    if not readings:
        return None
    filename = f"pi_power_{export_time.strftime('%Y-%m-%d_%H-%M')}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(readings[0].keys()))
        writer.writeheader()
        writer.writerows(readings)
    return filepath


def compute_hourly_stats(readings):
    if not readings:
        return {}
    powers    = [r["pi_power_W"]  for r in readings if r.get("pi_power_W")]
    temps     = [r["cpu_temp_C"]  for r in readings if r.get("cpu_temp_C")]
    teg       = [r["teg_power_W"] for r in readings if r.get("teg_power_W")]
    anomalies = sum(1 for r in readings if r.get("anomaly"))
    def avg(lst): return round(sum(lst)/len(lst), 3) if lst else 0
    total_Wh  = avg(powers) * (len(readings) / 3600)
    teg_Wh    = avg(teg)    * (len(readings) / 3600)
    return {
        "readings":          len(readings),
        "avg_power_W":       avg(powers),
        "max_power_W":       round(max(powers), 3) if powers else 0,
        "avg_cpu_temp_C":    avg(temps),
        "max_cpu_temp_C":    round(max(temps), 3) if temps else 0,
        "total_energy_Wh":   round(total_Wh, 6),
        "total_teg_Wh":      round(teg_Wh, 6),
        "heat_recovery_pct": round((teg_Wh/total_Wh)*100, 3) if total_Wh > 0 else 0,
        "anomalies":         anomalies
    }


def commit_hourly_export(readings, export_time):
    filepath = export_hourly_csv(list(readings), export_time)
    if not filepath:
        print("[Bridge] No readings to export")
        return

    stats        = compute_hourly_stats(list(readings))
    hour_str     = export_time.strftime("%Y-%m-%d %H:00")
    anomaly_note = f" ⚠ {stats['anomalies']} anomalies" if stats.get("anomalies") else ""
    message      = (
        f"Pi power data {hour_str} | "
        f"avg:{stats['avg_power_W']}W max:{stats['max_power_W']}W "
        f"temp:{stats['avg_cpu_temp_C']}C "
        f"TEG:{stats['heat_recovery_pct']}% recovered"
        f"{anomaly_note}"
    )

    history_file    = ".datavault/history.json"
    csv_filename    = os.path.basename(filepath)
    already_tracked = False
    if os.path.exists(history_file):
        with open(history_file) as f:
            already_tracked = csv_filename in json.load(f).get("files", {})

    action  = "commit" if already_tracked else "add"
    success, output = run_datavault([action, filepath, message])

    if success:
        print(f"[DataVault] {'Committed' if already_tracked else 'Added'}: {csv_filename}")
        print(f"            {message}")
        if stats.get("anomalies", 0) > 0:
            with open(history_file) as f:
                hist = json.load(f)
            latest_v = hist["files"][csv_filename]["versions"][-1]["version_id"]
            run_datavault(["tag", filepath, latest_v, f"ANOMALY: {stats['anomalies']} power/temp events detected"])
            print(f"[DataVault] Tagged {latest_v} with anomaly warning")
        _, output2 = run_datavault(["chain", csv_filename])
        print(f"[DataVault] Chain: {'✓ intact' if 'CHAIN INTACT' in output2 else '✗ BROKEN'}")
    else:
        print(f"[DataVault] Failed: {output}")

    return filepath, stats


def main(simulate=False):
    print("\n" + "="*55)
    print("   PI BRIDGE — DataVault ↔ Mini Data Center")
    print("="*55)
    print(f"  Mode:   {'SIMULATED' if simulate else 'REAL (Raspberry Pi)'}")
    print(f"  Export: every {EXPORT_INTERVAL_SECONDS//60} minutes")
    print(f"\n  Press Ctrl+C to stop\n")

    if not ensure_datavault_initialized():
        sys.exit(1)

    next_export   = datetime.now() + timedelta(seconds=EXPORT_INTERVAL_SECONDS)
    reading_fn    = simulated_reading if simulate else real_reading
    reading_count = 0

    try:
        while True:
            reading = reading_fn()
            if reading:
                readings_buffer.append(reading)
                reading_count += 1
                if reading_count % 10 == 0:
                    r = reading
                    flag = " ⚠" if r.get("anomaly") else ""
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] power:{r['pi_power_W']:.2f}W temp:{r['cpu_temp_C']:.1f}C TEG:{r['teg_power_W']:.4f}W fan:{r['fan_speed_pct']}%{flag}")

            now = datetime.now()
            if now >= next_export:
                print(f"\n[{now.strftime('%H:%M:%S')}] Hourly export triggered...")
                commit_hourly_export(readings_buffer, now)
                next_export = now + timedelta(seconds=EXPORT_INTERVAL_SECONDS)
                print(f"[Bridge] Next export in {EXPORT_INTERVAL_SECONDS//60} minutes\n")

            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\nBridge stopped. Readings: {reading_count} | Buffer: {len(readings_buffer)}")
        if len(readings_buffer) > 10:
            print("Running final export...")
            commit_hourly_export(readings_buffer, datetime.now())
        print("\nDataVault status:")
        subprocess.run([sys.executable, "datavault.py", "status"], cwd=os.path.dirname(os.path.abspath(__file__)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pi Bridge — connects mini data center to DataVault")
    parser.add_argument("--simulate", action="store_true", help="Simulation mode (no real Pi sensors)")
    parser.add_argument("--fast",     action="store_true", help="Export every 60s instead of 60min (testing)")
    args = parser.parse_args()

    if args.fast:
        EXPORT_INTERVAL_SECONDS = 60
        print("[Bridge] Fast mode: exporting every 60 seconds")

    main(simulate=args.simulate)