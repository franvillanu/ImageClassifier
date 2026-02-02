# Ctrl+Shift+5 for PR script (user shortcut, all repos)

Add the shortcut in your **user** keybindings so it’s available in every repo. The keybinding is global; the task that runs is defined in this repo’s `.vscode/tasks.json`.

- **In this repo:** Ctrl+Shift+5 runs the PR script.
- **In other repos:** The same shortcut still runs “Run Task” for that task name; if the task doesn’t exist there, you’ll get the task list or nothing. No harm.

## Option 1: Keyboard Shortcuts UI (easiest)

1. **Open Keyboard Shortcuts (user)**  
   `Ctrl+K` then `Ctrl+S`  
   (or: File → Preferences → Keyboard Shortcuts)

2. **Search:** `Tasks: Run Task`

3. **Click the +** next to **“Tasks: Run Task”** and press **Ctrl+Shift+5**.

4. When asked **“Which task?”**, choose:  
   **PR: create + merge (squash) + update main**

5. Save. The shortcut is now in your **user** keybindings and applies to all repos.

## Option 2: Edit user keybindings.json

1. **Open Command Palette**  
   `Ctrl+Shift+P`

2. Run: **“Preferences: Open Keyboard Shortcuts (JSON)”**  
   (This opens your **user** keybindings file, e.g. `%APPDATA%\Code\User\keybindings.json` or Cursor’s equivalent.)

3. **Add** this entry inside the `[]` array (use a comma after existing entries):

```json
{
  "key": "ctrl+shift+5",
  "command": "workbench.action.tasks.runTask",
  "args": "PR: create + merge (squash) + update main"
}
```

4. Save. The shortcut is global and works in all repos.

## Run the task without the keybinding

- **Command Palette** (`Ctrl+Shift+P`) → **“Tasks: Run Task”** → **“PR: create + merge (squash) + update main”**
- Or from terminal (in this repo):  
  `powershell -NoProfile -ExecutionPolicy Bypass -File .vscode/pr_create_merge_update.ps1`
