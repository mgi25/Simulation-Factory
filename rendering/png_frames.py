"""Reading rendered frames back: dimensions, digests and a sanity check.

Verification only. Nothing here draws anything - it opens the PNGs Godot
wrote and answers the questions a render has to pass before it is trusted:
is every frame really 1080x1920, is it actually a picture rather than a black
rectangle, and does rendering the same replay twice produce the same pixels.

Two digests, deliberately:

* `file_digest` hashes the file. It is the strict test, and the one that
  should pass - Godot's PNG encoder writes no timestamps and no run ids.
* `pixel_digest` hashes the *decoded* image. It is the fallback for the day
  an encoder change makes identical pictures land in non-identical files,
  and it is what "the same pixels" actually means.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# PNG colour types that carry real image data at 8 bits per channel. Godot
# writes truecolour or truecolour+alpha; anything else means the frame is not
# what the renderer is supposed to produce.
COLOR_TYPE_RGB = 2
COLOR_TYPE_RGBA = 6

_CHUNK_SIZE = 1 << 20


class PngError(ValueError):
    """A file is not a PNG this project produced."""


@dataclass(frozen=True)
class PngHeader:
    width: int
    height: int
    bit_depth: int
    color_type: int

    @property
    def channels(self) -> str:
        if self.color_type == COLOR_TYPE_RGBA:
            return "RGBA"
        if self.color_type == COLOR_TYPE_RGB:
            return "RGB"
        return f"colour type {self.color_type}"


def read_header(path: str) -> PngHeader:
    """Width, height and pixel format, from the 33 bytes that hold them.

    The IHDR chunk is always first and always the same size, so this reads a
    frame's dimensions without decoding two million pixels - which is what
    makes checking every frame of a render affordable.
    """
    with open(path, "rb") as handle:
        head = handle.read(33)
    if len(head) < 33 or head[:8] != PNG_SIGNATURE:
        raise PngError(f"not a PNG file: {path}")
    length, kind = struct.unpack(">I4s", head[8:16])
    if kind != b"IHDR" or length != 13:
        raise PngError(f"PNG does not start with an IHDR chunk: {path}")
    width, height = struct.unpack(">II", head[16:24])
    return PngHeader(width, height, head[24], head[25])


def file_digest(path: str) -> str:
    """SHA-256 of any file on disk, read in chunks.

    Frames use it to prove two renders are identical; the source replay uses
    it to prove rendering never wrote to it.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(_CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class FrameSample:
    """A decoded frame, reduced to what verification actually asks of it."""

    width: int
    height: int
    digest: str
    darkest: int
    brightest: int
    distinct: int

    @property
    def is_black(self) -> bool:
        """Nothing was drawn at all."""
        return self.brightest == 0

    @property
    def is_blank(self) -> bool:
        """One flat colour edge to edge: a clear colour, not a picture."""
        return self.distinct <= 1


def sample(path: str) -> FrameSample:
    """Decode one frame and reduce it to a digest plus a few statistics.

    Decoding goes through pygame, which the project already depends on and
    which needs no display to read a PNG. The digest is taken over plain RGB
    bytes so it describes the picture rather than the file.
    """
    surface = _load_surface(path)
    width, height = surface.get_size()
    pixels = _pygame().image.tobytes(surface, "RGB")
    return FrameSample(
        width=width,
        height=height,
        digest=hashlib.sha256(pixels).hexdigest(),
        darkest=min(pixels),
        brightest=max(pixels),
        distinct=len(set(pixels)),
    )


def pixel_digest(path: str) -> str:
    """SHA-256 of a frame's decoded RGB bytes."""
    return sample(path).digest


def _pygame():
    import pygame  # imported here so planning a render never needs it

    return pygame


def _load_surface(path: str):
    pygame = _pygame()
    try:
        return pygame.image.load(path)
    except Exception as error:  # pygame raises its own error type
        raise PngError(f"could not decode {path}: {error}") from error
