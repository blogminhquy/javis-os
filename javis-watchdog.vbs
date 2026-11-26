' Javis OS watchdog runner: Task Scheduler calls this every minute so that
' javis-watchdog.ps1 check runs with NO console window flashing on screen.
' ASCII only: wscript reads this file in the ANSI code page.
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File """ & root & "\javis-watchdog.ps1"" check", 0, True
