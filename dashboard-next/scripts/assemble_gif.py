# Stitches the PNG frames from gen-globe-gif.mjs into a seamless-loop animation, downscaled for
# small/email use. Output format follows the extension:
#   .gif  -> palette GIF. If frames have alpha, exports 1-bit transparency (hard edge; email-safe).
#   .webp -> animated WebP with true alpha (smooth orb edge; great for web, NOT email).
# Usage: python assemble_gif.py <framesDir> <out.(gif|webp)> [size] [ms]
import sys, glob, os
from PIL import Image

frames_dir = sys.argv[1]
out = sys.argv[2]
size = int(sys.argv[3]) if len(sys.argv) > 3 else 240
duration = int(sys.argv[4]) if len(sys.argv) > 4 else 90

paths = sorted(glob.glob(os.path.join(frames_dir, "f*.png")))
if not paths:
    sys.exit(f"no frames in {frames_dir}")

rgba = [Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS) for p in paths]
has_alpha = any(im.getchannel("A").getextrema()[0] < 255 for im in rgba)

if out.lower().endswith(".webp"):
    # True-alpha animation — smooth edges. loop=0 => infinite.
    rgba[0].save(out, save_all=True, append_images=rgba[1:], format="WEBP",
                 loop=0, duration=duration, method=6, quality=82, allow_mixed=True)
elif has_alpha:
    # Transparent GIF: adaptive 255-color palette + reserve index 255 for the clear area.
    TRANSP = 255
    out_frames = []
    for im in rgba:
        clear = im.getchannel("A").point(lambda a: 255 if a < 128 else 0)  # hard 1-bit cutoff
        p = im.convert("RGB").quantize(colors=255, method=Image.FASTOCTREE, dither=Image.Dither.NONE)
        p.paste(TRANSP, (0, 0), clear)  # set clear pixels to the reserved transparent index
        out_frames.append(p)
    out_frames[0].save(out, save_all=True, append_images=out_frames[1:], loop=0, duration=duration,
                       disposal=2, transparency=TRANSP, optimize=False)
else:
    # Opaque GIF (solid background).
    q = [im.convert("RGB").quantize(colors=64, method=Image.FASTOCTREE, dither=Image.Dither.NONE) for im in rgba]
    q[0].save(out, save_all=True, append_images=q[1:], loop=0, duration=duration, disposal=2, optimize=True)

kb = os.path.getsize(out) / 1024
print(f"wrote {os.path.basename(out)}  {size}x{size}  {len(rgba)} frames  {duration}ms  "
      f"{'alpha' if has_alpha else 'opaque'}  {kb:.0f} KB")
