"""Ecualizador gráfico de 10 bandas (procesamiento del audio, sin interfaz).

Cómo funciona: con las ganancias de las bandas se arma la curva de respuesta (interpolada en escala
logarítmica de frecuencia) y de ella un filtro FIR de fase lineal de 8192 coeficientes (resolución suficiente para 31 Hz). El audio se
filtra por bloques con FFT y «solapar y sumar» (overlap-add): numpy hace todo el cálculo, rápido y sin
dependencias nuevas. Fase lineal = no deforma el sonido, solo añade 85 ms de retardo fijo.

Saturación: subir bandas o el nivel general puede pasar de 0 dBFS. Con «evitar saturación» (por defecto)
el nivel general baja lo que sube la parte más alta de la curva (bandas + nivel general), y un limitador
suave atrapa los picos que aún pasarían de 1.0. Lo que no satura sale intacto: con la curva plana el
sonido es idéntico al original.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BANDS_HZ = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
BAND_LABELS = ("31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k")
MAX_DB = 12.0
TAPS = 8192
BLOCK = 8192
FFT_SIZE = 16384  # ≥ TAPS + BLOCK − 1
LATENCY_FRAMES = TAPS // 2

# Presets (dB por banda). Inspirados en las curvas habituales de los reproductores; suaves a propósito.
PRESETS: dict[str, tuple[float, ...]] = {
    "Normal": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Pop": (-1, 1, 3, 4, 3, 0, -1, -1, 1, 2),
    "Rock": (5, 4, 2, -1, -2, -1, 2, 3, 4, 4),
    "Clásica": (4, 3, 2, 1, -1, -1, 0, 2, 3, 4),
    "Jazz": (3, 2, 1, 2, -1, -1, 0, 1, 2, 3),
    "Electrónica": (6, 5, 2, 0, -2, 1, 0, 2, 4, 5),
    "Hip-Hop": (6, 5, 3, 1, -1, -1, 1, 0, 2, 3),
    "Vocal": (-2, -2, -1, 1, 3, 4, 4, 2, 0, -1),
    "Más graves": (7, 6, 4, 2, 0, 0, 0, 0, 0, 0),
    "Más agudos": (0, 0, 0, 0, 0, 1, 2, 4, 6, 7),
}


@dataclass(frozen=True)
class EqSettings:
    gains: tuple[float, ...] = PRESETS["Normal"]
    preamp: float = 0.0  # dB, de −12 a +12
    prevent_clipping: bool = True

    def clamped(self) -> "EqSettings":
        gains = tuple(max(-MAX_DB, min(MAX_DB, float(g))) for g in self.gains[: len(BANDS_HZ)])
        gains += (0.0,) * (len(BANDS_HZ) - len(gains))
        return EqSettings(gains, max(-MAX_DB, min(MAX_DB, float(self.preamp))), self.prevent_clipping)

    @property
    def total_preamp_db(self) -> float:
        """Nivel general que se aplica. Con «evitar saturación» la curva nunca sube de 0 dB: se descuenta lo
        que suba su parte más alta, contando el nivel general (antes solo las bandas: un nivel general
        positivo saturaba y todo lo cargaba el limitador, con distorsión clara)."""
        if not self.prevent_clipping:
            return self.preamp
        return self.preamp - max(0.0, max(self.gains) + self.preamp)


def response_db(settings: EqSettings, freqs: np.ndarray) -> np.ndarray:
    """Curva de la respuesta (dB) en las frecuencias pedidas: interpolación lineal en log2(f) entre los
    centros de banda, plana fuera de los extremos."""
    log_f = np.log2(np.maximum(freqs, 1.0))
    centers = np.log2(np.array(BANDS_HZ, dtype=float))
    return np.interp(log_f, centers, np.array(settings.gains, dtype=float))


def design_fir(settings: EqSettings, rate: int) -> np.ndarray:
    """Filtro FIR de fase lineal (TAPS coeficientes) que reproduce la curva del ecualizador."""
    freqs = np.fft.rfftfreq(TAPS, 1.0 / rate)
    gain = 10 ** ((response_db(settings, freqs) + settings.total_preamp_db) / 20)
    impulse = np.fft.irfft(gain, n=TAPS)  # fase cero, centrado en 0
    impulse = np.roll(impulse, TAPS // 2) * np.hanning(TAPS)  # causal, retardo TAPS/2
    return impulse.astype(np.float64)


class EqProcessor:
    """Filtra audio intercalado (frames, canales) por bloques, manteniendo el estado entre llamadas."""

    def __init__(self, rate: int, channels: int, settings: EqSettings | None = None) -> None:
        self.rate = rate
        self.channels = channels
        self._tail = np.zeros((FFT_SIZE - BLOCK, channels))
        self._pending = np.zeros((0, channels), dtype=np.float32)
        self._spectrum: np.ndarray | None = None
        self._previous: np.ndarray | None = None  # filtro anterior, mientras dura el fundido cruzado
        self._last_input: np.ndarray | None = None  # espectro del bloque anterior (para el fundido cruzado)
        self.set_settings(settings or EqSettings())

    def set_settings(self, settings: EqSettings) -> None:
        """Cambia la curva. El siguiente bloque pasa del filtro anterior al nuevo con un fundido cruzado:
        cambiarlo de golpe a mitad de la señal sonaba como un clic."""
        self.settings = settings.clamped()
        spectrum = np.fft.rfft(design_fir(self.settings, self.rate), n=FFT_SIZE)
        if self._spectrum is not None and self._previous is None:
            self._previous = self._spectrum
        self._spectrum = spectrum

    def reset(self) -> None:
        """Tras un salto (buscar otra posición): se descarta la «cola» del filtro para no mezclar audios."""
        self._tail[:] = 0
        self._pending = np.zeros((0, self.channels), dtype=np.float32)
        self._previous = None  # no hay sonido anterior con el que fundir
        self._last_input = None

    def process(self, frames: np.ndarray) -> np.ndarray:
        """Entrada (n, canales) float. Devuelve los frames listos (múltiplos de BLOCK; el resto queda
        pendiente hasta la próxima llamada o flush())."""
        data = np.concatenate([self._pending, frames]) if len(self._pending) else frames
        whole = (len(data) // BLOCK) * BLOCK
        self._pending = data[whole:]
        if not whole:
            return np.zeros((0, self.channels), dtype=np.float32)
        out = np.empty((whole, self.channels), dtype=np.float32)
        for start in range(0, whole, BLOCK):
            out[start:start + BLOCK] = self._block(data[start:start + BLOCK])
        return out

    def flush(self) -> np.ndarray:
        """Al terminar el archivo: lo pendiente más la cola del filtro (el final del sonido)."""
        need = len(self._pending) + LATENCY_FRAMES
        blocks = -(-need // BLOCK)
        padded = np.zeros((blocks * BLOCK, self.channels), dtype=np.float32)
        padded[: len(self._pending)] = self._pending
        self._pending = np.zeros((0, self.channels), dtype=np.float32)
        out = np.concatenate([self._block(padded[i:i + BLOCK]) for i in range(0, len(padded), BLOCK)])
        return out[:need]

    def _block(self, block: np.ndarray) -> np.ndarray:
        spectrum = np.fft.rfft(block, n=FFT_SIZE, axis=0)
        full = np.fft.irfft(spectrum * self._spectrum[:, None], n=FFT_SIZE, axis=0)
        if self._previous is None:
            full[: FFT_SIZE - BLOCK] += self._tail
            out = full[:BLOCK]
        else:
            # Fundido cruzado de un bloque entre dos salidas completas: todo con el filtro anterior (con su
            # cola) y todo con el nuevo (su cola se recalcula con el bloque anterior). Mezclar la cola vieja
            # con el filtro nuevo dejaba un escalón a mitad del bloque.
            old = np.fft.irfft(spectrum * self._previous[:, None], n=FFT_SIZE, axis=0)[:BLOCK] + self._tail[:BLOCK]
            if self._last_input is not None:
                full[:BLOCK] += np.fft.irfft(self._last_input * self._spectrum[:, None], n=FFT_SIZE, axis=0)[BLOCK:]
            ramp = (np.arange(BLOCK, dtype=np.float64) + 0.5)[:, None] / BLOCK
            out = old * (1.0 - ramp) + full[:BLOCK] * ramp
            self._previous = None
        self._last_input = spectrum
        self._tail = full[BLOCK:].copy()
        self._tail = np.concatenate([self._tail, np.zeros((FFT_SIZE - BLOCK - len(self._tail), self.channels))]) \
            if len(self._tail) < FFT_SIZE - BLOCK else self._tail[: FFT_SIZE - BLOCK]
        return soft_limit(out).astype(np.float32)


def soft_limit(x: np.ndarray, threshold: float = 0.99) -> np.ndarray:
    """Limitador suave: solo actúa si algo pasaría de 1.0 (lo demás sale intacto: antes redondeaba todo lo
    que superaba 0,95 aunque no saturara, y la música masterizada cerca de 0 dBFS salía distorsionada).
    Cuando actúa, redondea lo que supera el umbral sin pasar nunca de 1.0, en vez de un recorte duro."""
    if not (np.abs(x) > 1.0).any():
        return x
    over = np.abs(x) > threshold
    y = x.copy()
    room = 1.0 - threshold
    excess = np.abs(x[over]) - threshold
    y[over] = np.sign(x[over]) * (threshold + room * np.tanh(excess / room))
    return y


def gain_at(settings: EqSettings, freq: float) -> float:
    """Ganancia (dB) que aplica el ecualizador a una frecuencia, incluido el nivel general."""
    return float(response_db(settings, np.array([freq]))[0] + settings.total_preamp_db)


def db_to_linear(db: float) -> float:
    return math.pow(10, db / 20)
