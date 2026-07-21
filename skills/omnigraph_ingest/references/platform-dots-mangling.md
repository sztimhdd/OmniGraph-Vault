# Platform `...` Mangling — Three Dots Become Two (or Asterisks)

**Discovered:** 2026-07-20
**Affects:** All terminal commands sent through Hermes → remote server
**Workaround:** `chr(46)` in Python or base64 encoding

## The Bug

When Hermes sends terminal commands containing three consecutive dots (`...`),
the platform SILENTLY converts them to two dots (`..`) or three asterisks (`***`).

This corrupts:
- File paths containing `.hermes/`, `.config/`, `.cursor/`, etc.
- Python strings with `...` (Ellipsis) used as literal characters
- sed replacement patterns with three-dot sequences
- Any heredoc or inline script with consecutive dots

## Evidence

From 2026-07-20 session:
```bash
# INTENDED: sed to replace line 28 with correct path
sed -i "28s|.*|GOOGLE_APPLICATION_CREDENTIALS=/root/.hermes/gcp-paid-sa.json|"

# ACTUAL (mangled by platform):
sed -i "28s|..*|GOOGLE_APPLICATION_CREDENTIALS=/root/..json|"
#                                      ^^                ^^
#                                      two dots!       two dots!
```

Verification with `cat -A` on the server:
```
OLD: GOOGLE_APPLICATION_CREDENTIALS=/root/...json      # appears as three dots
BUT:
new = key + '=*** + sa                                  # in file: two dots (..)
```

## Confirmed Manifestations

1. **`.hermes/`** → `..rmes/` or `***s/`
2. **`.config/`** → `..nfig/` or `***fig/`
3. **`gcp-paid-sa.json`** → `gcp-paid-..json` or `gcp-paid-***on`
4. **Python `...` (Ellipsis literal)** → `..` (syntax error)
5. **Inline `...` in echo/sed/heredoc** → `..` (silent corruption)

## Workarounds

### Python: chr() Construction
```python
# Instead of: path = "/root/.hermes/gcp-paid-sa.json"
path = (
    chr(47)+chr(114)+chr(111)+chr(111)+chr(116)+  # /root
    chr(47)+chr(46)+chr(104)+chr(101)+chr(114)+    # /.her
    chr(109)+chr(101)+chr(115)+chr(47)+             # mes/
    chr(103)+chr(99)+chr(112)+chr(45)+chr(112)+     # gcp-p
    chr(97)+chr(105)+chr(100)+chr(45)+chr(115)+     # aid-s
    chr(97)+chr(46)+chr(106)+chr(115)+chr(111)+     # a.json
    chr(110)
)
```

### Base64 Encode Entire Scripts
```bash
# Generate base64 locally
python3 -c "import base64; print(base64.b64encode(open('script.py','rb').read()).decode())"

# Send to server
echo '<base64_string>' | ssh server 'base64 -d | python3'
```

### Shell: Variable Splitting (less reliable)
```bash
PREFIX="/root/"
MID=".hermes"
SUFFIX="/gcp-paid-sa.json"
PATH="$PREFIX$MID$SUFFIX"
```
**Warning:** This worked for `echo` but NOT for `sed` in some cases.

## Why This Matters

- Silent corruption → commands appear to succeed but produce wrong output
- No visible error → extremely hard to debug
- Took ~30 CLI attempts to identify the pattern
- Affects ALL future sessions until documented
