import os
import subprocess
from datetime import datetime

# Ask user for backup location
base_dir = input("Enter backup folder path: ").strip()

if not os.path.exists(base_dir):
    os.makedirs(base_dir)

# Create timestamped folder
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
backup_dir = os.path.join(base_dir, f"system_backup_{timestamp}")
os.makedirs(backup_dir)

print(f"\n📦 Backup will be saved in: {backup_dir}\n")


def run_command(command, output_file=None):
    try:
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                subprocess.run(command, shell=True, stdout=f, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(command, shell=True)
    except Exception as e:
        print(f"❌ Error: {e}")


# 1. System Info
print("🔹 Backing up system info...")
run_command("systeminfo", os.path.join(backup_dir, "system_info.txt"))

# 2. Installed Apps
print("🔹 Exporting installed apps...")
run_command(f'winget export -o "{os.path.join(backup_dir, "apps.json")}"')

# 3. WiFi Passwords
print("🔹 Exporting WiFi profiles...")
wifi_dir = os.path.join(backup_dir, "wifi")
os.makedirs(wifi_dir)
run_command(f'netsh wlan export profile key=clear folder="{wifi_dir}"')

# 4. Drivers
print("🔹 Backing up drivers...")
drivers_dir = os.path.join(backup_dir, "drivers")
os.makedirs(drivers_dir)
run_command(f'dism /online /export-driver /destination:"{drivers_dir}"')

# 5. Registry
print("🔹 Backing up registry...")
reg_dir = os.path.join(backup_dir, "registry")
os.makedirs(reg_dir)
run_command(f'reg export HKLM "{os.path.join(reg_dir, "HKLM.reg")}" /y')
run_command(f'reg export HKCU "{os.path.join(reg_dir, "HKCU.reg")}" /y')

# 6. Network Info
print("🔹 Saving network info...")
run_command("ipconfig /all", os.path.join(backup_dir, "network_info.txt"))

# 7. Environment Variables
print("🔹 Saving environment variables...")
run_command("set", os.path.join(backup_dir, "env_variables.txt"))

# 8. Power Plan
print("🔹 Exporting power plan...")
run_command(f'powercfg -export "{os.path.join(backup_dir, "powerplan.pow")}" SCHEME_CURRENT')


# 9. Diagnostics (NEW SECTION)
print("🔹 Running system diagnostics...")

diag_dir = os.path.join(backup_dir, "diagnostics")
os.makedirs(diag_dir)

# Battery report
run_command(f'powercfg /batteryreport /output "{os.path.join(diag_dir, "battery_report.html")}"')

# Energy report
run_command(f'powercfg /energy /output "{os.path.join(diag_dir, "energy_report.html")}"')

# Battery raw info
run_command(f'wmic path Win32_Battery get /format:list', os.path.join(diag_dir, "battery_info.txt"))

# Full system report
run_command(f'msinfo32 /report "{os.path.join(diag_dir, "system_full_report.txt")}"')


print("\n✅ FULL SYSTEM BACKUP COMPLETED!")
print(f"📁 Location: {backup_dir}")