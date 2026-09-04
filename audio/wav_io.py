"""Writing and reading back the PCM master.

A canonical 44-byte RIFF/WAVE header and nothing else: no LIST chunk, no
INFO, no encoder name, no date. That is deliberate - the WAV is the audio
half of a deterministic render, and the only way two runs can be compared
byte for byte is if the file contains nothing that is not audio.

The read side exists for validation rather than for playback. Before FFmpeg
is called, the file that was just written is opened again and asked the
questions production depends on: is it really 48 kHz stereo, is it exactly
the length the render plan says, is there actually signal in it and does
anything clip.
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
from array import array
from dataclasses import dataclass

# 24-bit is the default: the ambient bed sits around -33 dBFS and the quiet
# end of a hit is lower still, and there is no reason to spend a phase of
# work on dithering decisions that a wider word makes irrelevant.
DEFAULT_BIT_DEPTH = 24
BIT_DEPTHS = (16, 24)

WAVE_FORMAT_PCM = 1
HEADER_SIZE = 44


class WavError(ValueError):
    """A WAV file is not the one this project writes."""


def full_scale(bit_depth: int) -> int:
    """The largest magnitude a sample of this width may take.

    Symmetric on purpose: two's complement reaches one further negative than
    positive, and using that last step would make the same float quantise to
    a different distance from full scale depending on its sign.
    """
    if bit_depth not in BIT_DEPTHS:
        raise WavError(f"unsupported bit depth {bit_depth}; expected one of {BIT_DEPTHS}")
    return (1 << (bit_depth - 1)) - 1


def quantise(left: array, right: array, bit_depth: int = DEFAULT_BIT_DEPTH) -> array:
    """Two float channels to one interleaved array of signed integers.

    Clamped rather than allowed to wrap: a sample past full scale is a
    mastering failure, and wrapping would turn it into the loudest possible
    click in the opposite direction.
    """
    if len(left) != len(right):
        raise WavError(f"channels differ in length: {len(left)} and {len(right)}")
    limit = full_scale(bit_depth)
    values = array("i", bytes(4 * 2 * len(left)))

    for index in range(len(left)):
        value = int(round(left[index] * limit))
        values[2 * index] = limit if value > limit else -limit if value < -limit else value
        value = int(round(right[index] * limit))
        values[2 * index + 1] = (
            limit if value > limit else -limit if value < -limit else value
        )
    return values


def pcm_bytes(
    left: array, right: array, bit_depth: int = DEFAULT_BIT_DEPTH
) -> bytes:
    """Interleaved little-endian PCM for two float channels."""
    values = quantise(left, right, bit_depth)
    if sys.byteorder == "big":
        values.byteswap()
    raw = bytearray(values.tobytes())
    if bit_depth == 24:
        # The integers are already correct; 24-bit PCM is simply the low three
        # bytes of each, so the sign byte is dropped rather than recomputed.
        del raw[3::4]
    else:
        del raw[2::4]
        del raw[2::3]
    return bytes(raw)


def wav_header(sample_count: int, sample_rate: int, channels: int, bit_depth: int) -> bytes:
    """The 44 bytes in front of the samples, and nothing more."""
    block_align = channels * bit_depth // 8
    data_size = sample_count * block_align
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        HEADER_SIZE - 8 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        WAVE_FORMAT_PCM,
        channels,
        sample_rate,
        sample_rate * block_align,
        block_align,
        bit_depth,
        b"data",
        data_size,
    )


def write_wav(
    path: str,
    left: array,
    right: array,
    *,
    sample_rate: int,
    bit_depth: int = DEFAULT_BIT_DEPTH,
) -> str:
    """Write the PCM master, creating parent directories as needed."""
    data = pcm_bytes(left, right, bit_depth)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(wav_header(len(left), sample_rate, 2, bit_depth))
        handle.write(data)
    return path


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class WavInfo:
    """What a WAV file claims to be, read back off disk."""

    channels: int
    sample_rate: int
    bit_depth: int
    sample_count: int
    data_size: int

    @property
    def duration(self) -> float:
        return 0.0 if self.sample_rate == 0 else self.sample_count / self.sample_rate


def read_wav(path: str) -> tuple[WavInfo, bytes]:
    """A WAV file's format and its raw sample bytes.

    Chunks are walked rather than assumed, so a file written by something
    other than `write_wav` is still read correctly - or rejected clearly.
    """
    with open(path, "rb") as handle:
        head = handle.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise WavError(f"not a RIFF/WAVE file: {path}")

        fmt: tuple[int, int, int, int] | None = None
        data = b""
        while True:
            header = handle.read(8)
            if len(header) < 8:
                break
            kind, size = struct.unpack("<4sI", header)
            payload = handle.read(size)
            if kind == b"fmt " and len(payload) >= 16:
                tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", payload[:16])
                if tag != WAVE_FORMAT_PCM:
                    raise WavError(f"{path}: format tag {tag}, expected uncompressed PCM")
                fmt = (channels, rate, bits, 0)
            elif kind == b"data":
                data = payload
            # RIFF pads odd-sized chunks to an even boundary.
            if size % 2:
                handle.read(1)

    if fmt is None:
        raise WavError(f"{path}: no fmt chunk")
    channels, rate, bits, _ = fmt
    block_align = max(1, channels * bits // 8)
    info = WavInfo(
        channels=channels,
        sample_rate=rate,
        bit_depth=bits,
        sample_count=len(data) // block_align,
        data_size=len(data),
    )
    return info, data


def decode_samples(data: bytes, bit_depth: int) -> array:
    """Raw PCM bytes back to signed integers, interleaved as stored."""
    if bit_depth == 16:
        values = array("h")
        values.frombytes(data[: len(data) // 2 * 2])
        if sys.byteorder == "big":
            values.byteswap()
        return values
    if bit_depth != 24:
        raise WavError(f"cannot decode {bit_depth}-bit PCM")

    # Widen three bytes to four by re-creating the sign byte, then let `array`
    # do the conversion in one step rather than a million.
    count = len(data) // 3
    trimmed = data[: count * 3]
    wide = bytearray(count * 4)
    wide[0::4] = trimmed[0::3]
    wide[1::4] = trimmed[1::3]
    wide[2::4] = trimmed[2::3]
    wide[3::4] = bytes(0xFF if byte & 0x80 else 0x00 for byte in trimmed[2::3])
    values = array("i")
    values.frombytes(bytes(wide))
    if sys.byteorder == "big":
        values.byteswap()
    return values


def pcm_peak(data: bytes, bit_depth: int) -> float:
    """Loudest sample in a decoded PCM buffer, as a fraction of full scale."""
    values = decode_samples(data, bit_depth)
    if not values:
        return 0.0
    loudest = max(max(values), -min(values))
    return loudest / full_scale(bit_depth)


def wav_problems(
    info: WavInfo,
    data: bytes,
    *,
    sample_rate: int,
    channels: int,
    sample_count: int,
    ceiling: float = 1.0,
) -> list[str]:
    """Everything wrong with a WAV before it is handed to an encoder.

    Every check is a production requirement, and every one of them fails the
    encode rather than being repaired here: an audio master that is not the
    length the render plan says it is has a bug behind it, and re-timing it
    at the last moment would hide that bug in a finished video.
    """
    problems: list[str] = []
    if info.sample_rate != sample_rate:
        problems.append(f"sample rate is {info.sample_rate}, expected {sample_rate}")
    if info.channels != channels:
        problems.append(f"{info.channels} channels, expected {channels}")
    if info.bit_depth not in BIT_DEPTHS:
        problems.append(f"{info.bit_depth}-bit PCM, expected one of {BIT_DEPTHS}")
        return problems
    if info.sample_count != sample_count:
        problems.append(
            f"{info.sample_count} samples per channel, expected exactly {sample_count}"
        )
    if not data:
        problems.append("no sample data at all")
        return problems

    peak = pcm_peak(data, info.bit_depth)
    if peak <= 0.0:
        problems.append("every sample is silent")
    # One least-significant bit of slack. The master targets a ceiling
    # expressed in decibels, which is not a value a finite word length can
    # land on exactly - rounding the loudest sample to the nearest integer
    # can leave it a single step the wrong side of the target. A step is
    # -144 dBFS at 24-bit, so the slack cannot hide anything real.
    if peak > ceiling + 1.0 / full_scale(info.bit_depth):
        problems.append(f"peak {peak:.6f} is above the {ceiling:.6f} ceiling")
    if peak >= 1.0:
        problems.append("a sample reached full scale")
    return problems
