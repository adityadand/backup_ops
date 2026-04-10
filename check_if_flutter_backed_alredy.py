import os
import shutil

# Ask user for SOURCE
default_source = r"C:\Flutter\Flutter Apps"
SOURCE = input(f"Enter source folder (default: {default_source}): ").strip()

if not SOURCE:
    SOURCE = default_source

if not os.path.exists(SOURCE):
    print("❌ Source folder does not exist!")
    exit()

# Ask user for DESTINATION
DEST = input("Enter backup destination folder: ").strip()

if not DEST:
    print("❌ Destination is required!")
    exit()

os.makedirs(DEST, exist_ok=True)

# Folders to exclude (keeping your Flutter-specific exclusions)
EXCLUDE_DIRS = {
    "build",
    ".dart_tool",
    ".gradle",
    ".idea",
    "Pods",
    "ephemeral",
    ".plugin_symlinks"
}

def should_exclude(path):
    parts = path.split(os.sep)
    return any(part in EXCLUDE_DIRS for part in parts)

print("\n🚀 Starting incremental backup...\n")

stats = {"copied": 0, "skipped": 0}

for app in os.listdir(SOURCE):
    app_path = os.path.join(SOURCE, app)
    dest_path = os.path.join(DEST, app)

    if os.path.isdir(app_path):
        print(f"📂 Checking project: {app}")

        for root, dirs, files in os.walk(app_path):
            if should_exclude(root):
                continue

            # In-place modification to skip excluded directories efficiently
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            relative_path = os.path.relpath(root, app_path)
            target_dir = os.path.join(dest_path, relative_path)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_dir, file)

                try:
                    if os.path.islink(src_file):
                        continue

                    # --- INCREMENTAL CHECK LOGIC ---
                    # Check if file exists and compare modification times
                    if os.path.exists(dst_file):
                        if os.path.getmtime(src_file) <= os.path.getmtime(dst_file):
                            stats["skipped"] += 1
                            continue 
                    
                    # Ensure the directory exists only when we have a file to copy
                    os.makedirs(target_dir, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    stats["copied"] += 1
                    print(f"  ✅ Updated: {os.path.join(relative_path, file)}")

                except PermissionError:
                    print(f"  ⚠️ Skipped (permission): {src_file}")
                except Exception as e:
                    print(f"  ⚠️ Error: {e}")

print(f"\n✨ Backup completed!")
print(f"📊 Files updated: {stats['copied']}")
print(f"📊 Files already up-to-date: {stats['skipped']}")
