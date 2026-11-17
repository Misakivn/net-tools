"""Khởi động cùng Windows bằng Task Scheduler (quyền cao nhất -> không hiện UAC mỗi lần bật máy)."""
from nettools import APP_ID
from nettools.core.system import IS_WINDOWS, launch_command, powershell, ps_quote


def is_enabled():
    if not IS_WINDOWS:
        return False
    rc, out = powershell(f"if(Get-ScheduledTask -TaskName {ps_quote(APP_ID)} -ErrorAction SilentlyContinue)"
                         "{'yes'}else{'no'}")
    return rc == 0 and out.strip().endswith("yes")


def enable():
    exe, args, workdir = launch_command()
    script = (
        f"$a=New-ScheduledTaskAction -Execute {ps_quote(exe)} -Argument {ps_quote(args)} "
        f"-WorkingDirectory {ps_quote(workdir)};"
        "$t=New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\\$env:USERNAME\";$t.Delay='PT15S';"
        "$p=New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\\$env:USERNAME\" -LogonType Interactive -RunLevel Highest;"
        "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew;"
        f"Register-ScheduledTask -TaskName {ps_quote(APP_ID)} -Action $a -Trigger $t -Principal $p "
        "-Settings $s -Description 'Net Tools - khoi dong cung Windows' -Force|Out-Null")
    return powershell(script)


def disable():
    return powershell(f"Unregister-ScheduledTask -TaskName {ps_quote(APP_ID)} -Confirm:$false "
                      "-ErrorAction SilentlyContinue")
