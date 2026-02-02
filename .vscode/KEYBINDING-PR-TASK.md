# Restore Ctrl+Shift+5 for PR script

Keybindings are stored in your **user** settings, not in the repo. If Ctrl+Shift+5 stopped working (e.g. after an update or new profile), re-add it like this.

## Option 1: Keyboard Shortcuts UI (easiest)

1. **Open Keyboard Shortcuts**  
   `Ctrl+K` then `Ctrl+S`  
   (or: File → Preferences → Keyboard Shortcuts)

2. **Search** for: `Tasks: Run Task`

3. **Click the +** next to **"Tasks: Run Task"** to add a keybinding.

4. **Press** `Ctrl+Shift+5` when prompted.

5. **When asked "Which task?"**, choose:  
   **PR: create + merge (squash) + update main**

6. Save. Ctrl+Shift+5 should now run the PR script.

## Option 2: Edit keybindings.json

1. **Open Command Palette**  
   `Ctrl+Shift+P`

2. Run: **"Preferences: Open Keyboard Shortcuts (JSON)"**

3. **Add** this entry inside the `[]` array (use a comma after existing entries):

```json
{
  "key": "ctrl+shift+5",
  "command": "workbench.action.tasks.runTask",
  "args": "PR: create + merge (squash) + update main"
}
```

4. Save the file.

## Run the task without the keybinding

- **Command Palette** (`Ctrl+Shift+P`) → **"Tasks: Run Task"** → **"PR: create + merge (squash) + update main"**
- Or from terminal:  
  `powershell -NoProfile -ExecutionPolicy Bypass -File .vscode/pr_create_merge_update.ps1`
