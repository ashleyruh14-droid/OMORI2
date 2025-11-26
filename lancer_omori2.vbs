Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Dossier où se trouve ce script .vbs
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder

' Lancer le .bat en mode caché (0 = pas de fenêtre)
shell.Run "demarrer_omori2.bat", 0, False
