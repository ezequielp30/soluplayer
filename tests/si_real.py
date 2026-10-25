"""Prueba real de la instancia única: 3 procesos a la vez, cada uno con un archivo (como el Explorador)."""
import math, os, re, struct, subprocess, sys, tempfile, time, wave

work = tempfile.mkdtemp(prefix="mp_si_")
data = os.path.join(work, "data")
files = []
for i in range(3):
    p = os.path.join(work, f"tono{i}.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * (400 + 100 * i) * n / 22050))) for n in range(22050 * 2)))
    files.append(p)
env = dict(os.environ, MUSICPLAYER_DATA_DIR=data, MUSICPLAYER_ORG="ReproductorMusicaTest", QT_QPA_PLATFORM="offscreen", MUSICPLAYER_SILENCIO="1")
exe = r"D:\reproductor-musica\.venv\Scripts\python.exe"

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)

def opened():
    """Archivos entregados a la ventana según el registro («Abrir N archivo(s) desde Windows»)."""
    try:
        log = open(os.path.join(data, "registro.log"), encoding="utf-8").read()
    except OSError:
        return 0
    return sum(int(n) for n in re.findall(r"Abrir (\d+) archivo\(s\) desde Windows", log))

def wait_for(cond, secs):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.2)
    return cond()

procs = [subprocess.Popen([exe, "main.py", f], cwd=r"D:\reproductor-musica", env=env) for f in files]
try:
    check("los 3 archivos llegan a una sola ventana", wait_for(lambda: opened() >= 3, 60), opened())
    wait_for(lambda: sum(p.poll() is None for p in procs) <= 1, 30)
    alive = [p for p in procs if p.poll() is None]
    check("queda una sola copia abierta; las otras salen con código 0",
          len(alive) == 1 and all(p.poll() == 0 for p in procs if p not in alive), [p.poll() for p in procs])
    # 4.ª copia ya abierto el programa: debe entregar y salir enseguida
    t = time.time()
    p4 = subprocess.Popen([exe, "main.py", files[0]], cwd=r"D:\reproductor-musica", env=env)
    try:
        p4.wait(30)
    except subprocess.TimeoutExpired:
        p4.kill()
    took = time.time() - t
    check("4.ª copia entrega el archivo y sale con código 0", p4.returncode == 0 and took < 15, f"{took:.1f} s, código {p4.returncode}")
    check("la ventana abierta recibe el archivo de la 4.ª copia", wait_for(lambda: opened() >= 4, 15), opened())
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()  # procesos de esta prueba (carpeta de datos temporal)
print("cerradas las copias de prueba")
print(f"RESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
