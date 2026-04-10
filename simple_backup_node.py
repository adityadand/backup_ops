import os
import shutil

IGNORE_FOLDERS = {
    "node_modules",
    "dist",
    ".git",
    "build",
    ".venv",      # 🔥 important (your issue)
    "__pycache__"
}

# 👉 Ask user input
SOURCE_DIR = input("Enter SOURCE folder path: ").strip()
DEST_DIR = input("Enter DESTINATION folder path: ").strip()

confirm = input(f"\nBackup from '{SOURCE_DIR}' to '{DEST_DIR}'? (y/n): ").lower()

if confirm != "y":
    print("❌ Backup cancelled.")
    exit()


def copy_folder(src, dest):
    if not os.path.exists(dest):
        os.makedirs(dest)

    for item in os.listdir(src):
        src_path = os.path.join(src, item)
        dest_path = os.path.join(dest, item)

        if os.path.isdir(src_path):
            if item in IGNORE_FOLDERS:
                print(f"⏭ Skipping: {src_path}")
                continue
            copy_folder(src_path, dest_path)
        else:
            shutil.copy2(src_path, dest_path)
            print(f"✔ Copied: {src_path}")


copy_folder(SOURCE_DIR, DEST_DIR)

print("\n✅ Backup completed!")