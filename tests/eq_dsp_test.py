"""Mide el ecualizador con señales de prueba: cada banda hace lo que dice, la curva plana no cambia el
sonido, no satura y un bloque tras otro no deja «costuras» (clics)."""
import sys
import numpy as np
sys.path.insert(0, r"D:\soluplayer")
from app.equalizer import BANDS_HZ, LATENCY_FRAMES, PRESETS, EqProcessor, EqSettings

RATE = 48000
results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")

def run(settings, signal):
    eq = EqProcessor(RATE, 2, settings)
    chunks = [eq.process(signal[i:i + 1000]) for i in range(0, len(signal), 1000)]  # trozos irregulares
    out = np.concatenate(chunks + [eq.flush()])
    return out[LATENCY_FRAMES:LATENCY_FRAMES + len(signal)]

def tone(freq, secs=1.0, amp=0.1):
    t = np.arange(int(RATE * secs)) / RATE
    s = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([s, s], axis=1)

def gain_db(a, b):
    mid = slice(len(a) // 4, 3 * len(a) // 4)
    return 20 * np.log10(np.sqrt(np.mean(b[mid] ** 2)) / np.sqrt(np.mean(a[mid] ** 2)))

flat = EqSettings()
x = tone(1000)
y = run(flat, x)
check("curva plana: el sonido no cambia (error < 0,1 %)", np.max(np.abs(y - x)) < 1e-3, f"{np.max(np.abs(y - x)):.2e}")
for i, f in enumerate(BANDS_HZ):
    gains = [0.0] * 10; gains[i] = 6.0
    s = EqSettings(tuple(gains), prevent_clipping=False)
    g = gain_db(tone(f), run(s, tone(f)))
    check(f"banda {f} Hz a +6 dB → {g:+.2f} dB", abs(g - 6.0) < 0.6)
s = EqSettings((0, 0, 0, 0, 0, -12, 0, 0, 0, 0), prevent_clipping=False)
check("−12 dB en 1 kHz no toca 125 Hz", abs(gain_db(tone(125), run(s, tone(125)))) < 0.5)
loud = tone(100, amp=0.9)
y = run(EqSettings(PRESETS["Más graves"]), loud)
check("con «evitar saturación» nunca pasa de 1.0", np.max(np.abs(y)) <= 1.0, f"pico {np.max(np.abs(y)):.3f}")
y = run(EqSettings((12,) * 10, prevent_clipping=False), loud)
check("sin protección, el limitador suave igual evita pasar de 1.0", np.max(np.abs(y)) <= 1.0, f"pico {np.max(np.abs(y)):.3f}")
y = run(EqSettings(PRESETS["Rock"]), tone(440, 2.0))
d = np.abs(np.diff(y[:, 0]))
check("sin clics entre bloques (salto máximo acotado)", d.max() < 0.05, f"{d.max():.4f}")
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
