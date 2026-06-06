sample = 'PaintCare Stewardship Program â€" Vermont'

# Show exact codepoints of the 3-char mojibake sequence
seq = sample[30:33]
print(f"seq repr: {seq!r}")
print(f"codepoints: {[hex(ord(c)) for c in seq]}")

# Show what our replacement string looks like
replacement_target = "â\u20ac\""
print(f"\nreplacement_target repr: {replacement_target!r}")
print(f"codepoints: {[hex(ord(c)) for c in replacement_target]}")

print(f"\nmatch: {seq == replacement_target}")
print(f"\nfixed: {sample.replace(replacement_target, chr(0x2014))!r}")
