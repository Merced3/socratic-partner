# Windows Autostart with Task Scheduler

This guide documents the exact method validated on Windows to run Socratic Partner automatically after logon, without opening a terminal. It uses the headless `pythonw.exe` so no console window appears.

## Prerequisite

Socratic Partner is already installed and running manually on the target computer. Stop the manual terminal first with `Ctrl+C`.

## Create the task

1. Open **Task Scheduler**.
2. Right-click **Task Scheduler Library** → **Create Task...** (not "Create Basic Task").
3. **General tab:**
   - Name: `SocraticPartner`
   - Select **Run only when user is logged on**
   - Leave **Run with highest privileges** unchecked.
4. **Triggers tab → New...:**
   - Begin the task: **At log on**
   - Enabled: checked → OK.
5. **Actions tab → New...:**
   - Program/script:

     ```text
     C:\Users\cedgo\Documents\Coding\Automations\socratic-partner\.venv\Scripts\pythonw.exe
     ```

   - Arguments:

     ```text
     -m socratic_partner.main
     ```

   - **Start in:** (required; without it the task cannot find `.env` or the database)

     ```text
     C:\Users\cedgo\Documents\Coding\Automations\socratic-partner
     ```

6. **Conditions tab:** uncheck **Start the task only if the computer is on AC power** (laptop).
7. **Settings tab:**
   - Check **If the task fails, restart every: 1 minute**.
   - Uncheck **Stop the task if it runs longer than**.
8. OK. No password prompt appears when **Run only when user is logged on** is selected.

## Test without rebooting

1. Ensure no terminal is running `socratic-partner`.
2. Right-click the task → **Run**.
3. Wait 30–60 seconds.
4. Run `/status` in Discord. It should answer.

## Test with a reboot

1. Restart the computer.
2. Log in normally.
3. Wait 60–90 seconds without opening any terminal.
4. Run `/status` in Discord. It should answer.

## Notes

- **Do not use "Run whether user is logged on or not" with "At startup"** if you cannot provide a stored password; that combination can silently fail. The validated combination is **"Run only when user is logged on" + "At log on"**.
- With `pythonw.exe` there is no console window and logs go only to the terminal scrollback. To see logs later, run `socratic-partner` manually in a terminal or wrap it in a small script that redirects output to a file.
