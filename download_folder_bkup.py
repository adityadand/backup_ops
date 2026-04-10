import os
import shutil
from pathlib import Path

def get_folder_size(path):
    """Calculates total size of a folder, skipping errors for system files."""
    total_size = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total_size += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total_size += get_folder_size(entry.path)
    except (PermissionError, OSError):
        pass
    return total_size

def ignore_junk_during_copy(dir_path, folder_contents):
    """Tells shutil.copytree which subfolders to skip during the backup."""
    JUNK_NAMES = {'.venv', 'node_modules', '__pycache__', 'site-packages', 'Scripts', 'Lib'}
    return [item for item in folder_contents if item in JUNK_NAMES]

def run_backup_tool():
    print("--- Smart Folder Analyzer & Backup Tool ---")
    raw_source = input("Paste the source folder path (e.g., your D: drive): ").strip().replace('"', '')
    source_path = Path(raw_source)

    if not source_path.exists() or not source_path.is_dir():
        print(f"Error: '{raw_source}' is not a valid directory.")
        return

    # Configuration
    JUNK_NAMES = {'.venv', 'node_modules', '__pycache__', 'site-packages', 'Scripts', 'Lib'}
    PRIORITY_EXTS = {'.py', '.xlsx', '.csv', '.pdf', '.docx', '.json', '.env', '.sql'}
    
    items_to_backup = []
    total_backup_bytes = 0

    print(f"\nAnalyzing: {source_path}")
    print(f"{'ITEM NAME':<45} | {'SIZE':<10} | {'ACTION'}")
    print("-" * 80)

    try:
        for item in source_path.iterdir():
            action = "SKIP"
            
            size_bytes = get_folder_size(item) if item.is_dir() else item.stat().st_size
            
            if item.is_dir():
                if item.name in JUNK_NAMES:
                    action = "IGNORE"
                elif "CV" in item.name.upper() or "RETURN" in item.name.upper() or "ACCOUNT" in item.name.upper():
                    action = "BACKUP"
                else:
                    if any(f.suffix in PRIORITY_EXTS for f in item.rglob('*') if f.is_file()):
                        action = "BACKUP"
            else:
                if item.suffix.lower() in PRIORITY_EXTS:
                    action = "BACKUP"

            if action == "BACKUP":
                items_to_backup.append(item)
                total_backup_bytes += size_bytes
                
            if action != "IGNORE":
                display_name = (item.name[:42] + '...') if len(item.name) > 45 else item.name
                size_display = f"{size_bytes / (1024*1024):.2f} MB"
                print(f"{display_name:<45} | {size_display:<10} | {action}")

    except PermissionError:
        print("\nNote: Permission denied for some hidden system files. Skipped.")

    # --- Phase 2: The Backup Process ---
    if not items_to_backup:
        print("\nNo critical files found to backup.")
        return

    total_mb = total_backup_bytes / (1024 * 1024)
    print("=" * 80)
    print(f"TOTAL DATA TO BACKUP: {total_mb:.2f} MB")
    print("=" * 80)

    raw_dest = input("\nEnter destination folder path for the backup (or press Enter to cancel): ").strip().replace('"', '')
    if not raw_dest:
        print("Backup cancelled by user.")
        return

    dest_path = Path(raw_dest)
    dest_path.mkdir(parents=True, exist_ok=True) # Safely creates the folder if it doesn't exist

    print(f"\nStarting backup to: {dest_path}")
    for item in items_to_backup:
        target = dest_path / item.name
        print(f"Copying {item.name}...")
        try:
            if item.is_dir():
                # dirs_exist_ok allows merging if you run the backup twice
                shutil.copytree(item, target, ignore=ignore_junk_during_copy, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target) # copy2 preserves original creation/modification times
        except Exception as e:
            print(f"  [!] Failed to copy {item.name}: {e}")

    print("\n✅ Backup Complete!")

if __name__ == "__main__":
    run_backup_tool()
    input("\nPress Enter to exit...")