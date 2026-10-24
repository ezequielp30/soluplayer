"""Valida el medidor contra valores conocidos de la norma (señales sintéticas)."""
import sys, math
sys.path.insert(0, r"D:\reproductor-musica")
import numpy as np
from app.loudness import LoudnessMeter, RATE
def measure(sig_l, sig_r):
    m = LoudnessMeter()
    inter = np.empty(len(sig_l) * 2, np.float32); inter[0::2] = sig_l; inter[1::2] = sig_r
    for i in range(0, len(inter), 9600 * 3): m.add(inter[i:i + 9600 * 3])  # trozos irregulares
    return m.result()
t = np.arange(RATE * 20) / RATE
ok = True
# 1) Seno 1 kHz a -20 dBFS en ambos canales → EBU Tech 3341: -23 LUFS (estéreo: -20 dBFS → -23.0 LUFS)
s = (10 ** (-20 / 20)) * np.sin(2 * np.pi * 997 * t)
L, TP = measure(s, s); print(f"seno 997 Hz -20 dBFS estéreo: {L} LUFS (esperado -20.0, EBU 3341)  pico {TP} dBTP (esperado -20.0)"); ok &= abs(L + 20.0) < 0.2 and abs(TP + 20.0) < 0.3
# 2) Mismo seno solo en un canal → -26 LUFS
L, _ = measure(s, np.zeros_like(s)); print(f"seno en un canal: {L} LUFS (esperado -23.0)"); ok &= abs(L + 23.0) < 0.2
# 3) Gating: 10 s a -20 dBFS + 10 s a -40 dBFS (estéreo) → la parte baja queda fuera del gate relativo → ≈ -23 LUFS
s2 = np.where(t < 10, 10 ** (-20 / 20), 10 ** (-40 / 20)) * np.sin(2 * np.pi * 997 * t)
L, _ = measure(s2, s2); print(f"gating (parte baja ignorada): {L} LUFS (esperado ≈ -20.0)"); ok &= abs(L + 20.0) < 0.3
# 4) Pico real: seno de fs/4 desfasado 45° tiene pico real 3 dB sobre el de muestra
x = 0.5 * np.sin(2 * np.pi * (RATE / 4) * t[:RATE] + math.pi / 4)
L, TP = measure(x, x); sp = 20 * math.log10(np.abs(x).max())
print(f"pico de muestra {sp:.2f} dBFS → pico real {TP} dBTP (esperado ≈ {20*math.log10(0.5):.2f})"); ok &= abs(TP - 20 * math.log10(0.5)) < 0.3
print("VALIDACIÓN:", "OK" if ok else "FALLA")
