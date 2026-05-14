Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\admin\.claude\projects\Generador de Pagos"
sh.Run """C:\Users\admin\.claude\projects\Generador de Pagos\venv\Scripts\pythonw.exe"" -m src.main", 0, False
