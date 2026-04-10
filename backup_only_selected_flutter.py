import os
import shutil

# 1. SETUP SOURCE
default_source = r"D:\Flutter\Flutter Apps"
SOURCE = input(f"Enter source folder (default: {default_source}): ").strip() or default_source

if not os.path.exists(SOURCE):
    print("❌ Source folder does not exist!")
    exit()

# 2. LIST ALL OPTIONS
all_projects = [d for d in os.listdir(SOURCE) if os.path.isdir(os.path.join(SOURCE, d))]

if not all_projects:
    print("❌ No projects found in the source directory.")
    exit()

print("\n" + "="*30)
print("   FLUTTER PROJECT BACKUP")
print("="*30)
for idx, project in enumerate(all_projects, 1):
    # This shows you everything available, like Flow Forge, Riga OS, etc.
    print(f"[{idx}] {project}")
print("="*30)

print("\nOPTIONS:")
print(" single: '1'")
print(" multiple: '1,3,5'")
print(" range: '1-3'")
print(" all: 'all'")

selection = input("\nYour choice: ").strip().lower()

# 3. PARSE SELECTION LOGIC
selected_projects = []

if selection == 'all':
    selected_projects = all_projects
elif '-' in selection:
    try:
        start, end = map(int, selection.split('-'))
        selected_projects = all_projects[start-1:end]
    except:
        print("❌ Invalid range format.")
        exit()
else:
    try:
        # Handles "1, 2, 3" or just "1"
        indices = [int(i.strip()) - 1 for i in selection.split(",") if i.strip().isdigit()]
        selected_projects = [all_projects[i] for i in indices if 0 <= i < len(all_projects)]
    except:
        print("❌ Invalid selection.")
        exit()

if not selected_projects:
    print("❌ No valid projects selected.")
    exit()

# 4. SETUP DESTINATION
DEST = input(f"\nEnter backup destination folder: ").strip()
if not DEST:
    print("❌ Destination is required!")
    exit()

# 5. EXECUTE INCREMENTAL BACKUP
EXCLUDE_DIRS = {"build", ".dart_tool", ".gradle", ".idea", "Pods", "ephemeral", ".plugin_symlinks"}

print(f"\n🚀 Processing {len(selected_projects)} projects...")
stats = {"copied": 0, "skipped": 0}

for app in selected_projects:
    app_path = os.path.join(SOURCE, app)
    dest_path = os.path.join(DEST, app)
    print(f"📦 Syncing: {app}")

    for root, dirs, files in os.walk(app_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        rel_path = os.path.relpath(root, app_path)
        target_dir = os.path.join(dest_path, rel_path)

        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(target_dir, file)

            # Only copy if file is missing or source is newer
            if os.path.exists(dst_file) and os.path.getmtime(src_file) <= os.path.getmtime(dst_file):
                stats["skipped"] += 1
                continue

            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            stats["copied"] += 1

print(f"\n✅ Done! {stats['copied']} files updated, {stats['skipped']} files skipped.")