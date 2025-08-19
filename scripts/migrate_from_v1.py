#!/usr/bin/env python3
"""
Migration script to help users transition from v1 to v2.

This script creates compatibility wrappers for the old scripts
so existing workflows continue to work.
"""

import os
import sys
from pathlib import Path


def create_compatibility_wrapper(old_script: str, new_command: str) -> str:
    """Create a wrapper script that calls the new CLI."""
    return f"""#!/usr/bin/env python3
\"\"\"
Compatibility wrapper for {old_script}.
This script now uses the new unified CLI.
\"\"\"

import sys
import subprocess

# Map old arguments to new CLI
print("Note: This script is deprecated. Please use 'yt-organizer {new_command}' instead.")
print()

# Run the new command
subprocess.run(["yt-organizer", "{new_command}"] + sys.argv[1:])
"""


def main():
    """Create compatibility wrappers for old scripts."""
    
    print("YouTube Playlist Organizer - Migration to v2")
    print("=" * 50)
    
    # Define mappings from old scripts to new commands
    mappings = {
        "app.py": "organize",
        "move_watch_later_to_playlist.py": "copy",
        "move_watch_later_playwright.py": "move-browser",
        "move_watch_later_robust.py": "move-browser",
        "debug_playlists.py": "list-playlists",
    }
    
    project_root = Path(__file__).parent.parent
    
    # Check if running from correct location
    if not (project_root / "src" / "yt_organizer").exists():
        print("Error: Please run this script from the project root.")
        sys.exit(1)
    
    print("\nCreating compatibility wrappers for old scripts...")
    print()
    
    created = []
    skipped = []
    
    for old_script, new_command in mappings.items():
        script_path = project_root / old_script
        backup_path = project_root / f"{old_script}.v1.backup"
        
        if script_path.exists():
            # Backup original
            if not backup_path.exists():
                script_path.rename(backup_path)
                print(f"✓ Backed up {old_script} to {backup_path.name}")
            
            # Create wrapper
            wrapper_content = create_compatibility_wrapper(old_script, new_command)
            with open(script_path, "w") as f:
                f.write(wrapper_content)
            
            # Make executable
            os.chmod(script_path, 0o755)
            
            created.append(old_script)
            print(f"✓ Created compatibility wrapper for {old_script}")
        else:
            skipped.append(old_script)
    
    print()
    print("Migration Summary:")
    print("-" * 30)
    print(f"Wrappers created: {len(created)}")
    print(f"Scripts not found: {len(skipped)}")
    
    print()
    print("Next steps:")
    print("1. Install the new package: pip install -e .")
    print("2. Your old scripts will continue to work but will show deprecation notices")
    print("3. Start using the new 'yt-organizer' command for new workflows")
    print()
    print("New CLI commands:")
    print("  yt-organizer organize      - Organize videos with AI (replaces app.py)")
    print("  yt-organizer copy          - Copy videos between playlists")
    print("  yt-organizer move-browser  - Move videos using browser automation")
    print("  yt-organizer auth          - Authenticate with YouTube")
    print("  yt-organizer list-playlists - List your playlists")
    print("  yt-organizer --help        - Show all commands")
    print()
    print("Your .env file and credentials will continue to work without changes.")
    

if __name__ == "__main__":
    main()
