"""Medición de sonoridad según ITU-R BS.1770-4 / EBU R128 y decisión de normalización.

- Sonoridad integrada (LUFS): ponderación K (cómo percibe el oído el volumen), bloques de 400 ms
  con 75 % de solapamiento, puerta absoluta de −70 LUFS y puerta relativa de −10 LU.
- Pico real (dBTP): sobremuestreo ×4, para saber cuánto se puede subir sin distorsionar.

La ponderación K se aplica en el dominio de la frecuencia sobre tramos de 100 ms (equivalente al
filtro de la norma salvo los transitorios de borde, con un error típico < 0,2 LU). El audio se
decodifica a 48 kHz, la frecuencia para la que la norma define los filtros.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

RATE = 48000
SEGMENT = RATE // 10  # 100 ms
ABS_GATE = -70.0
REL_GATE = -10.0

# Filtros de la norma BS.1770 a 48 kHz: estante (≈ +4 dB por encima de 1,5 kHz) y paso alto (RLB).
_SHELF_B, _SHELF_A = (1.53512485958697, -2.69169618940638, 1.19839281085285), (1.0, -1.69065929318241, 0.73248077421585)
_HPF_B, _HPF_A = (1.0, -2.0, 1.0), (1.0, -1.99004745483398, 0.99007225036621)


def _response(b, a, n: int) -> np.ndarray:
    w = np.linspace(0, math.pi, n // 2 + 1)
    z1, z2 = np.exp(-1j * w), np.exp(-2j * w)
    return (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)


_K_POWER = (np.abs(_response(_SHELF_B, _SHELF_A, SEGMENT)) * np.abs(_response(_HPF_B, _HPF_A, SEGMENT))) ** 2
_PARSEVAL = np.full(SEGMENT // 2 + 1, 2.0)
_PARSEVAL[0] = 1.0
_PARSEVAL[-1] = 1.0  # SEGMENT es par


# Pico real: interpolación ×4 por FFT en bloques solapados. De cada bloque solo se usa el centro
# (se descartan MARGIN muestras a cada lado), así los bordes no generan picos falsos.
TP_BLOCK = 8192
TP_MARGIN = 256
TP_FACTOR = 4


class LoudnessMeter:
    """Acumula audio estéreo float32 a 48 kHz por trozos (como llega del decodificador)."""

    def __init__(self) -> None:
        self._pending = np.zeros((0, 2), dtype=np.float32)
        self._segment_ms: list[np.ndarray] = []  # potencia ponderada media por canal de cada tramo de 100 ms
        self._true_peak = 0.0
        self._tp_buffer = np.zeros((0, 2), dtype=np.float32)  # muestras pendientes para el pico real
        self._tp_started = False
        self.frames = 0
        self.invalid = False

    def add(self, interleaved: np.ndarray) -> None:
        frames = interleaved.reshape(-1, 2)
        if not np.isfinite(frames).all():
            # Tramas dañadas que el decodificador entrega como NaN/infinito: un solo NaN arruina la suma
            # de todo lo que sigue y la medición parecería válida. Se descarta la medición entera.
            self.invalid = True
            return
        self.frames += len(frames)
        self._update_true_peak(frames)
        data = np.concatenate([self._pending, frames]) if len(self._pending) else frames
        whole = (len(data) // SEGMENT) * SEGMENT
        if whole:
            self._process(data[:whole].reshape(-1, SEGMENT, 2))
        self._pending = data[whole:].copy()

    def _process(self, segments: np.ndarray) -> None:
        # (tramos, muestras, canales) → espectro por canal
        spectrum = np.fft.rfft(segments, axis=1)
        power = np.abs(spectrum) ** 2
        weighted = (power * (_K_POWER * _PARSEVAL)[None, :, None]).sum(axis=1) / (SEGMENT * SEGMENT)
        self._segment_ms.append(weighted)

    def _update_true_peak(self, frames: np.ndarray, final: bool = False) -> None:
        """Pico real ×4 continuo: bloques de TP_BLOCK con TP_MARGIN de solapamiento a cada lado."""
        if len(frames):
            self._true_peak = max(self._true_peak, float(np.abs(frames).max()))
        if not self._tp_started:  # el primer bloque empieza con un margen de silencio
            self._tp_buffer = np.zeros((TP_MARGIN, 2), dtype=np.float32)
            self._tp_started = True
        data = np.concatenate([self._tp_buffer, frames]) if len(frames) else self._tp_buffer
        if final:
            data = np.concatenate([data, np.zeros((TP_MARGIN, 2), dtype=np.float32)])
        hop = TP_BLOCK - 2 * TP_MARGIN
        count = (len(data) - 2 * TP_MARGIN) // hop if len(data) >= TP_BLOCK else 0
        if final and len(data) > 2 * TP_MARGIN and (len(data) - 2 * TP_MARGIN) % hop:
            data = np.concatenate([data, np.zeros((TP_BLOCK, 2), dtype=np.float32)])
            count = (len(data) - 2 * TP_MARGIN) // hop
        if count:
            starts = np.arange(count) * hop
            # Se sobremuestrean TODOS los bloques: descartar los de muestras bajas (para ir más rápido)
            # puede subestimar el pico en masters muy recortados, y un pico subestimado distorsionaría
            # al subir el volumen.
            windows = np.lib.stride_tricks.sliding_window_view(data, TP_BLOCK, axis=0)[starts]  # (n, 2, BLOCK)
        if count and len(windows):
            spectrum = np.fft.rfft(windows, axis=2)
            up = np.fft.irfft(spectrum, n=TP_BLOCK * TP_FACTOR, axis=2) * TP_FACTOR
            core = up[:, :, TP_MARGIN * TP_FACTOR:(TP_BLOCK - TP_MARGIN) * TP_FACTOR]
            self._true_peak = max(self._true_peak, float(np.abs(core).max()))
        if count:
            data = data[count * hop:]
        self._tp_buffer = data.copy()

    def result(self) -> tuple[float | None, float | None]:
        """(sonoridad integrada en LUFS, pico real en dBTP). None si no hay audio suficiente o válido."""
        if self.invalid:
            return None, None
        self._update_true_peak(np.zeros((0, 2), dtype=np.float32), final=True)
        if self.frames < SEGMENT * 4:
            # Menos de 400 ms: la norma no define la sonoridad sin un bloque completo (rellenar con
            # silencio daría un valor más bajo de lo real). Solo se informa el pico.
            return None, _db(self._true_peak)
        if len(self._pending):
            padded = np.zeros((SEGMENT, 2), dtype=np.float32)
            padded[: len(self._pending)] = self._pending
            self._process(padded[None])
            self._pending = np.zeros((0, 2), dtype=np.float32)
        if not self._segment_ms:
            return None, None
        seg = np.concatenate(self._segment_ms)  # (tramos, 2)
        if len(seg) < 4:
            blocks = seg.mean(axis=0, keepdims=True)
        else:
            # Bloques de 400 ms con salto de 100 ms = media de 4 tramos consecutivos.
            cumulative = np.cumsum(np.vstack([np.zeros((1, 2)), seg]), axis=0)
            blocks = (cumulative[4:] - cumulative[:-4]) / 4
        block_power = blocks.sum(axis=1)  # G = 1 para izquierda y derecha
        with np.errstate(divide="ignore"):
            block_loudness = -0.691 + 10 * np.log10(block_power)
        above_abs = block_power[block_loudness > ABS_GATE]
        if not len(above_abs):
            return None, _db(self._true_peak)
        relative = -0.691 + 10 * math.log10(above_abs.mean()) + REL_GATE
        gated = block_power[(block_loudness > ABS_GATE) & (block_loudness > relative)]
        integrated = -0.691 + 10 * math.log10(gated.mean())
        return round(integrated, 2), _db(self._true_peak)


def _db(linear: float) -> float | None:
    return round(20 * math.log10(linear), 2) if linear > 0 else None


# ---------------------------------------------------------------------- decisión


CEILING_DBTP = -1.0  # pico real máximo tras subir el volumen (margen recomendado por EBU R128)
STEP_DB = 1.5  # el paso del MP3 sin pérdida (global_gain): ±0,75 dB alrededor de la referencia es «igual»
LOW_THRESHOLD_LU = 3.0  # a partir de 3 LU por debajo de la referencia se considera «muy bajo»
MIN_USEFUL_GAIN = 1.0  # menos de 1 dB no se nota: no se aplica
MAX_GAIN = 12.0


@dataclass(frozen=True)
class Decision:
    status: str  # "bajo", "correcto", "alto", "sin datos"
    gain_db: float  # ganancia a aplicar (0 si no hace falta)
    wanted_db: float  # ganancia que haría falta para llegar a la referencia
    limited_by_peak: bool
    reason: str


def plausible(loudness: float | None, true_peak: float | None) -> bool:
    """Una grabación real está por debajo de 0 LUFS y su pico real no pasa de unos +6 dBTP.
    Valores fuera de eso indican un archivo con tramas dañadas que el decodificador interpreta mal."""
    return loudness is not None and -70 < loudness < 0 and (true_peak is None or true_peak < 6)


def original_loudness(track) -> float | None:
    """Sonoridad que tenía la canción antes de los ajustes del programa (lo medido menos lo aplicado)."""
    if track.loudness_lufs is None:
        return None
    return track.loudness_lufs - (track.norm_gain_db or 0.0)


def library_reference(tracks) -> float:
    """Referencia de la biblioteca calculada con la sonoridad ORIGINAL de cada canción: así no se corre al
    igualar (si se calculara con lo ya ajustado, cada «Igualar» la movería un poco y reescribiría archivos)."""
    return reference_level([original_loudness(t) for t in tracks])


def reference_level(loudness_values: list[float]) -> float:
    """Nivel de referencia: la mediana de la biblioteca (así las bajas se igualan a las demás),
    acotada entre −16 y −9 LUFS para no apuntar a valores extremos."""
    values = sorted(v for v in loudness_values if v is not None and -70 < v < 0)
    if not values:
        return -14.0
    median = values[len(values) // 2]
    return max(-16.0, min(-9.0, median))


PLAYBACK_MAX_UP = 12.0  # al reproducir: lo más que se sube una canción
PLAYBACK_MAX_DOWN = 20.0  # y lo más que se baja


def playback_gain(loudness: float | None, true_peak: float | None, target: float) -> float:
    """Ganancia lineal (dB, toda la canción por igual: sin compresión ni «bombeo») para que suene al objetivo
    al reproducirla, sin tocar el archivo. Al subir, el pico real nunca pasa de CEILING_DBTP; bajar no
    distorsiona. Sin medición fiable (o sin pico conocido, si habría que subir): 0."""
    if loudness is None or not plausible(loudness, true_peak):
        return 0.0
    gain = target - loudness
    if gain > 0:
        if true_peak is None:
            return 0.0
        gain = max(0.0, min(gain, CEILING_DBTP - true_peak, PLAYBACK_MAX_UP))
    else:
        gain = max(gain, -PLAYBACK_MAX_DOWN)
    return round(gain, 1)


def decide(loudness: float | None, true_peak: float | None, reference: float, applied: float = 0.0) -> Decision:
    """Igualar a la referencia DENTRO del MP3 (sin pérdida, pasos de STEP_DB): sube las bajas y baja las
    fuertes, para que suenen parejas en cualquier reproductor. Ganancia lineal (toda la canción por igual).
    Al subir, el pico real nunca pasa de CEILING_DBTP; bajar no distorsiona. `applied` = dB ya aplicados a
    esta canción (con signo): el tope de ±MAX_GAIN es en total, no por cada vez."""
    if loudness is None:
        return Decision("sin datos", 0.0, 0.0, False, "No se pudo medir (silencio o archivo dañado).")
    if not plausible(loudness, true_peak):
        return Decision(
            "sin datos", 0.0, 0.0, False,
            "Medición no fiable (el archivo tiene tramas anómalas): no se toca por seguridad.",
        )
    wanted = reference - loudness
    if abs(wanted) <= STEP_DB / 2:  # justo a medio paso también es «igual»: ni subir ni bajar mejora
        return Decision("correcto", 0.0, round(wanted, 1), False, "Volumen igual al de tu biblioteca: no se toca.")
    if wanted > 0:
        allowed = MAX_GAIN - max(0.0, applied)  # lo que queda del tope por canción
        if allowed < STEP_DB:
            return Decision(
                "bajo", 0.0, round(wanted, 1), False,
                f"Ya se subió +{applied:.1f} dB, que es el máximo por canción (+{MAX_GAIN:.0f} dB): no se sube más.",
            )
        if true_peak is None:
            return Decision("bajo", 0.0, round(wanted, 1), True,
                            f"Está {wanted:.1f} dB por debajo, pero no se conoce su pico: no se sube por seguridad.")
        by_peak = math.floor((CEILING_DBTP - true_peak) / STEP_DB + 1e-9)
        steps = min(round(wanted / STEP_DB), by_peak, math.floor(allowed / STEP_DB + 1e-9))
        limited = by_peak < min(round(wanted / STEP_DB), math.floor(allowed / STEP_DB + 1e-9))
        if steps <= 0:
            return Decision("bajo", 0.0, round(wanted, 1), True,
                            f"Está {wanted:.1f} dB por debajo, pero sus picos ya llegan a {true_peak:.1f} dBTP: subirla distorsionaría.")
        gain = steps * STEP_DB
        if limited:
            detail = f" (de {wanted:.1f} necesarios; limitado por los picos para no distorsionar)."
        elif round(wanted / STEP_DB) * STEP_DB > allowed:
            detail = f" (de {wanted:.1f} necesarios; el tope por canción es +{MAX_GAIN:.0f} dB en total)."
        else:
            detail = " hasta el nivel de referencia."
        return Decision("bajo", gain, round(wanted, 1), limited, f"Sube +{gain:.1f} dB{detail}")
    allowed_down = MAX_GAIN + min(0.0, applied)  # lo que queda del tope hacia abajo
    steps = max(round(wanted / STEP_DB), -math.floor(allowed_down / STEP_DB + 1e-9))
    if steps >= 0:
        return Decision("alto", 0.0, round(wanted, 1), False,
                        f"Ya se bajó {applied:.1f} dB, que es el máximo por canción (−{MAX_GAIN:.0f} dB): no se baja más.")
    gain = steps * STEP_DB
    return Decision("alto", gain, round(wanted, 1), False, f"Baja {gain:.1f} dB hasta el nivel de referencia (sin pérdida).")
