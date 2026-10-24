"""Prueba real de la instancia única: 3 procesos a la vez, cada uno con un archivo (como el Explorador)."""
import math, os, struct, subprocess, sys, tempfile, time, wave

work = tempfile.mkdtemp(prefix="mp_si_")
data = os.path.join(work, "data")
files = []
for i in range(3):
    p = os.path.join(work, f"tono{i}.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * (400 + 100 * i) * n / 22050))) for n in range(22050 * 2)))
    files.append(p)
env = dict(os.environ, MUSICPLAYER_DATA_DIR=data, QT_QPA_PLATFORM="offscreen", MUSICPLAYER_SILENCIO="1")
exe = r"D:\reproductor-musica\.venv\Scripts\python.exe"
procs = [subprocess.Popen([exe, "main.py", f], cwd=r"D:\reproductor-musica", env=env) for f in files]
time.sleep(12)
alive = [p for p in procs if p.poll() is None]
codes = [p.poll() for p in procs]
print("procesos vivos tras 12 s:", len(alive), "códigos de los que terminaron:", codes)
log = open(os.path.join(data, "registro.log"), encoding="utf-8").read()
print("\n".join(l for l in log.splitlines() if "Abrir" in l or "Inicio" in l))
# 4.ª copia ya abierto el programa: debe entregar y salir enseguida
t = time.time()
p4 = subprocess.Popen([exe, "main.py", files[0]], cwd=r"D:\reproductor-musica", env=env)
p4.wait(30)
print(f"4.ª copia terminó en {time.time() - t:.1f} s con código {p4.returncode}")
time.sleep(1)
log = open(os.path.join(data, "registro.log"), encoding="utf-8").read()
print("registro de colas:", [l.split("INFO", 1)[1].strip() for l in log.splitlines() if "INFO" in l and "Reproduciendo:" in l]); print("aperturas registradas:", [l.split("INFO", 1)[1].strip() for l in log.splitlines() if "INFO" in l and "Abrir" in l])
for p in alive:
    p.kill()  # procesos de esta prueba (carpeta de datos temporal)
print("cerradas las copias de prueba")
