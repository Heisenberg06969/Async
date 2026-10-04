' Async 2.0 - Silent Windows System Tray Launcher
' Bypasses WindowsApps execution aliases and locates the real Python 3.10+ runtime

Option Explicit

Dim fso, WshShell, scriptDir, localAppData, pythonwExe, candidates, p, cmd, ret

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

' Prioritize genuine Python installations with installed site-packages
candidates = Array( _
    scriptDir & "\.venv\Scripts\pythonw.exe", _
    scriptDir & "\venv\Scripts\pythonw.exe", _
    localAppData & "\Programs\Python\Python312\pythonw.exe", _
    localAppData & "\Programs\Python\Python311\pythonw.exe", _
    localAppData & "\Programs\Python\Python313\pythonw.exe", _
    localAppData & "\Programs\Python\Python310\pythonw.exe", _
    "C:\Python312\pythonw.exe", _
    "C:\Python311\pythonw.exe", _
    "C:\Python310\pythonw.exe" _
)

pythonwExe = ""
For Each p In candidates
    If fso.FileExists(p) Then
        pythonwExe = p
        Exit For
    End If
Next

' Fallback: Search WHERE pythonw, strictly filtering out WindowsApps stubs
If pythonwExe = "" Then
    Dim execObj, line
    On Error Resume Next
    Set execObj = WshShell.Exec("cmd.exe /c where pythonw")
    If Err.Number = 0 Then
        Do While Not execObj.StdOut.AtEndOfStream
            line = Trim(execObj.StdOut.ReadLine())
            If InStr(LCase(line), "windowsapps") = 0 And fso.FileExists(line) Then
                pythonwExe = line
                Exit Do
            End If
        Loop
    End If
    On Error GoTo 0
End If

If pythonwExe = "" Then
    MsgBox "Python (pythonw.exe) was not found in your standard installation directories." & vbCrLf & vbCrLf & _
           "Please ensure Python 3.10+ is installed from python.org with required packages.", _
           vbCritical, "Async 2.0 - Python Not Found"
    WScript.Quit 1
End If

cmd = """" & pythonwExe & """ """ & scriptDir & "\app_tray.py"""

On Error Resume Next
ret = WshShell.Run(cmd, 0, False)

If Err.Number <> 0 Then
    MsgBox "Failed to launch Async System Tray:" & vbCrLf & Err.Description, vbCritical, "Async 2.0 Error"
    WScript.Quit Err.Number
End If
