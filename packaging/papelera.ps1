# Envía a la Papelera de reciclaje la carpeta indicada en $env:REPRO_PAPELERA_DIR (la usa el desinstalador).
# Con FOF_WANTNUKEWARNING: si algo no se puede reciclar (no cabe en la Papelera, o está desactivada),
# Windows PREGUNTA antes de borrarlo para siempre. Código de salida 0 si la carpeta ya no está.
# crear-instalador.ps1 lo incrusta (codificado) en el desinstalador: no hace falta ningún archivo.
$dir = $env:REPRO_PAPELERA_DIR
if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { exit 2 }
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class ReproPapelera {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode, Pack = 1)]
    struct Op32 { public IntPtr hwnd; public uint wFunc; public string pFrom; public string pTo; public ushort fFlags; public int aborted; public IntPtr maps; public string title; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct Op64 { public IntPtr hwnd; public uint wFunc; public string pFrom; public string pTo; public ushort fFlags; public int aborted; public IntPtr maps; public string title; }
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, EntryPoint = "SHFileOperationW")] static extern int Run32(ref Op32 op);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, EntryPoint = "SHFileOperationW")] static extern int Run64(ref Op64 op);
    // FO_DELETE con FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_WANTNUKEWARNING
    const ushort Flags = 0x40 | 0x10 | 0x4 | 0x4000;
    public static int Send(string path) {
        string from = path + "\0";  // la lista termina en dos nulos (el segundo lo agrega el marshaling)
        if (IntPtr.Size == 4) { var op = new Op32(); op.wFunc = 3; op.pFrom = from; op.fFlags = Flags; int r = Run32(ref op); return r != 0 ? r : op.aborted; }
        var op64 = new Op64(); op64.wFunc = 3; op64.pFrom = from; op64.fFlags = Flags; int r64 = Run64(ref op64); return r64 != 0 ? r64 : op64.aborted;
    }
}
"@
$result = [ReproPapelera]::Send($dir)
if ($result -eq 0 -and -not (Test-Path -LiteralPath $dir)) { exit 0 } else { exit 1 }
