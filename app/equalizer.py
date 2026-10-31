"""Ecualizador gráfico de 10 bandas (procesamiento del audio, sin interfaz).

Cómo funciona: con las ganancias de las bandas se arma la curva de respuesta (interpolada en escala
logarítmica de frecuencia) y de ella un filtro FIR de fase lineal largo (32 768 coeficientes: ±0,5 dB
también en las bandas de 31 y 62 Hz a 44,1/48 kHz; ±1 dB a 96 kHz). El audio se filtra en bloques cortos
(93 ms) con FFT y «solapar y sumar» (overlap-add), así el ecualizador responde rápido aunque el filtro sea
largo. Fase lineal = no deforma el sonido; el retardo fijo del filtro se descuenta al reproducir.
Por debajo de 20 Hz (inaudible) las bandas no refuerzan: subir 31 Hz no mueve los parlantes en vano.

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
BLOCK = 4096  # audio que se filtra de una vez a 44,1/48 kHz: 93 ms (un cambio de ajuste se oye enseguida)


def taps_for(rate: int) -> int:
    """Largo del filtro (la resolución en Hz es rate / taps). A 96 kHz uno más largo daría ±0,5 dB en 31 Hz
    pero costaría un tercio de un núcleo en el hilo de la ventana: se queda en ±1 dB."""
    return 32768


def block_for(rate: int) -> int:
    """Frames que se filtran de una vez: ~90 ms a 44,1/48 kHz; a 96 kHz bloques del doble (mismo costo)."""
    return BLOCK if rate <= 48000 else 2 * BLOCK


TAPS = taps_for(44100)
LATENCY_FRAMES = TAPS // 2  # retardo del filtro a 44,1/48 kHz (cada EqProcessor dice el suyo: .latency)

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
    curve = np.interp(log_f, centers, np.array(settings.gains, dtype=float))
    # Por debajo de 20 Hz no se refuerza (se desvanece de 25 a 10 Hz): no se oye y solo gasta parlante.
    fade = np.clip((np.asarray(freqs, dtype=float) - 10.0) / 15.0, 0.0, 1.0)
    return np.where(curve > 0, curve * fade, curve)


def design_fir(settings: EqSettings, rate: int, taps: int | None = None) -> np.ndarray:
    """Filtro FIR de fase lineal que reproduce la curva del ecualizador."""
    taps = taps or taps_for(rate)
    freqs = np.fft.rfftfreq(taps, 1.0 / rate)
    gain = 10 ** ((response_db(settings, freqs) + settings.total_preamp_db) / 20)
    impulse = np.fft.irfft(gain, n=taps)  # fase cero, centrado en 0
    impulse = np.roll(impulse, taps // 2) * np.hanning(taps)  # causal, retardo taps/2
    return impulse.astype(np.float64)


class EqProcessor:
    """Filtra audio intercalado (frames, canales) por bloques, manteniendo el estado entre llamadas."""

    def __init__(self, rate: int, channels: int, settings: EqSettings | None = None) -> None:
        self.rate = rate
        self.channels = channels
        self.taps = taps_for(rate)
        self.block = block_for(rate)
        self.latency = self.taps // 2  # frames de retardo fijo del filtro (se descuentan al reproducir)
        self._fft = 2 * self.taps  # ≥ taps + block − 1, y alcanza para recalcular la cola con el historial
        self._tail = np.zeros((self._fft - self.block, channels))
        self._history = np.zeros((self.taps, channels))  # lo último que entró: para el fundido cruzado
        self._pending = np.zeros((0, channels), dtype=np.float32)
        self._spectrum: np.ndarray | None = None
        self._previous: np.ndarray | None = None  # filtro anterior, mientras dura el fundido cruzado
        self.set_settings(settings or EqSettings())

    def set_settings(self, settings: EqSettings) -> None:
        """Cambia la curva. El siguiente bloque pasa del filtro anterior al nuevo con un fundido cruzado:
        cambiarlo de golpe a mitad de la señal sonaba como un clic."""
        self.settings = settings.clamped()
        spectrum = np.fft.rfft(design_fir(self.settings, self.rate, self.taps), n=self._fft)
        if self._spectrum is not None and self._previous is None:
            self._previous = self._spectrum
        self._spectrum = spectrum

    def reset(self) -> None:
        """Tras un salto (buscar otra posición): se descarta la «cola» del filtro para no mezclar audios."""
        self._tail[:] = 0
        self._history[:] = 0
        self._pending = np.zeros((0, self.channels), dtype=np.float32)
        self._previous = None  # no hay sonido anterior con el que fundir

    def process(self, frames: np.ndarray) -> np.ndarray:
        """Entrada (n, canales) float. Devuelve los frames listos (múltiplos de self.block; el resto queda
        pendiente hasta la próxima llamada o flush())."""
        data = np.concatenate([self._pending, frames]) if len(self._pending) else frames
        whole = (len(data) // self.block) * self.block
        self._pending = data[whole:]
        if not whole:
            return np.zeros((0, self.channels), dtype=np.float32)
        out = np.empty((whole, self.channels), dtype=np.float32)
        for start in range(0, whole, self.block):
            out[start:start + self.block] = self._block(data[start:start + self.block])
        return out

    def flush(self) -> np.ndarray:
        """Al terminar el archivo: lo pendiente más la cola del filtro (el final del sonido)."""
        need = len(self._pending) + self.latency
        blocks = -(-need // self.block)
        padded = np.zeros((blocks * self.block, self.channels), dtype=np.float32)
        padded[: len(self._pending)] = self._pending
        self._pending = np.zeros((0, self.channels), dtype=np.float32)
        out = np.concatenate([self._block(padded[i:i + self.block]) for i in range(0, len(padded), self.block)])
        return out[:need]

    def _block(self, block: np.ndarray) -> np.ndarray:
        fft = self._fft
        spectrum = np.fft.rfft(block, n=fft, axis=0)
        full = np.fft.irfft(spectrum * self._spectrum[:, None], n=fft, axis=0)
        if self._previous is None:
            full[: fft - self.block] += self._tail
            out = full[:self.block]
        else:
            # Fundido cruzado de un bloque entre dos salidas completas: todo con el filtro anterior (con su
            # cola) y todo con el nuevo, cuya cola se recalcula con el historial (el filtro es más largo que
            # el bloque: lo que viene sonando de antes también tiene que pasar por el filtro nuevo).
            old = np.fft.irfft(spectrum * self._previous[:, None], n=fft, axis=0)
            old[: fft - self.block] += self._tail
            full[: fft - self.block] += self._tail_from_history()
            ramp = (np.arange(self.block, dtype=np.float64) + 0.5)[:, None] / self.block
            out = old[:self.block] * (1.0 - ramp) + full[:self.block] * ramp
            self._previous = None
        self._tail = full[self.block:].copy()
        self._history = np.concatenate([self._history[self.block:], block])
        return soft_limit(out).astype(np.float32)

    def _tail_from_history(self) -> np.ndarray:
        """Lo que el audio ya entrado aporta, con el filtro ACTUAL, a lo que sale desde ahora (la «cola»)."""
        conv = np.fft.irfft(np.fft.rfft(self._history, n=self._fft, axis=0) * self._spectrum[:, None], n=self._fft, axis=0)
        tail = np.zeros((self._fft - self.block, self.channels))
        rest = conv[self.taps:]
        tail[: len(rest)] = rest
        return tail


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


def to_pcm16(samples: np.ndarray, rng: np.random.Generator) -> bytes:
    """Muestras float (±1) a PCM de 16 bits con dither TPDF y redondeo. Sin dither, truncar dejaba los
    pasajes muy suaves (colas de reverberación, fundidos) con distorsión armónica en vez de un ruido de
    fondo parejo e inaudible."""
    lsb = 1.0 / 32767
    noise = (rng.random(samples.shape) - rng.random(samples.shape)) * lsb  # triangular, ±1 LSB
    return np.round(np.clip(samples + noise, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def gain_at(settings: EqSettings, freq: float) -> float:
    """Ganancia (dB) que aplica el ecualizador a una frecuencia, incluido el nivel general."""
    return float(response_db(settings, np.array([freq]))[0] + settings.total_preamp_db)


def db_to_linear(db: float) -> float:
    return math.pow(10, db / 20)
