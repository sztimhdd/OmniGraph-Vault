# Local Development & Testing Guide

## Quick Start

### One-Line Setup
```bash
bash scripts/install-for-hermes.sh
```

### Pre-Commit Validation
Before committing skill changes, run:

```bash
# All skills
python skill_runner.py skills/ --test-all

# Single skill
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json
```

---

## Environment Setup

### Prerequisites
- Python 3.11+
- Edge browser (Windows) or Chrome/Chromium (Linux/Mac)
- CDP support enabled (local development)

### Local CDP Configuration

Start Edge with Chrome DevTools Protocol enabled:

**Windows:**
```powershell
Start-Process "msedge.exe" -ArgumentList "--remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223"
```

**Linux/Mac:**
```bash
google-chrome --remote-debugging-port=9223 &
```

### Environment Variables

Set these in `~/.hermes/.env`:

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Apify (primary scraping)
APIFY_TOKEN=your_apify_token_here

# Optional: Chrome DevTools Protocol
CDP_URL=http://localhost:9223
```

Verify with:
```bash
cat ~/.hermes/.env | grep GEMINI_API_KEY
```

---

## Testing Workflow

### Single Skill Test
```bash
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json
```

Expected output:
```
Running skill_runner for: skills/omnigraph_query
Loaded 10 test cases from tests/skills/test_omnigraph_query.json
Case 1/10: [test_name] ... PASS
Case 2/10: [test_name] ... PASS
...
All tests passed: 10/10
Exit code: 0
```

### All Skills Test
```bash
python skill_runner.py skills/ --test-all
```

Runs all test suites in `tests/skills/` sequentially and reports aggregate results.

### Structure Validation Only
```bash
python skill_runner.py skills/ --validate
```

Checks SKILL.md format, evals.json schema, scripts/ wrappers without executing tests.

### Quick Local Test (Smoke Test)
```bash
python skill_runner.py skills/omnigraph_ingest --quick
```

Runs only first 3 test cases per skill (fast feedback loop during development).

---

## Manual Script Execution

### Ingest a WeChat Article
```bash
cd ~/Desktop/OmniGraph-Vault
source venv/bin/activate  # Unix/Mac
# or: venv\Scripts\activate  # Windows

python ingest_wechat.py "https://mp.weixin.qq.com/s/..."
```

Expected output:
- HTML download (Apify or CDP)
- Image extraction and description
- LightRAG insertion
- Success message with entity count

### Query Knowledge Graph
```bash
python kg_synthesize.py "What are the latest trends in AI Agents?" hybrid
```

Expected output:
- Graph retrieval (hybrid mode combines local and global)
- Cognee context recall
- Markdown report to stdout
- Report also saved to `~/.hermes/omonigraph-vault/synthesis_output.md`

---

## Troubleshooting

### skill_runner.py Not Found
**Issue:** `command not found: skill_runner.py`

**Solution:**
- Run from project root: `cd ~/Desktop/OmniGraph-Vault`
- Check Python is in venv: `which python` should show `/venv/bin/python`

### GEMINI_API_KEY Not Set
**Issue:** `⚠️ Configuration error: GEMINI_API_KEY is not set.`

**Solution:**
1. Check env file exists: `ls -la ~/.hermes/.env`
2. Verify key is present: `cat ~/.hermes/.env | grep GEMINI_API_KEY`
3. If missing, add to `~/.hermes/.env`:
   ```bash
   echo "GEMINI_API_KEY=your_key_here" >> ~/.hermes/.env
   ```
4. Restart shell or source env: `source ~/.hermes/.env`

### Gemini API Error
**Issue:** `google.api_core.exceptions.InvalidArgument: 400 Invalid input`

**Possible causes:**
- API key is invalid or expired
- API key lacks required permissions (embedding, vision, generation)
- Query contains invalid Unicode or too-large input

**Solution:**
- Verify API key in Google Cloud Console
- Check quota and billing is enabled
- Try simpler query first: `python kg_synthesize.py "hello" naive`

### CDP Connection Refused
**Issue:** `ConnectionRefusedError: [Errno 111] Connection refused`

**Cause:** Edge browser not running with remote debugging port open.

**Solution:**
- Kill any existing Edge processes: `pkill msedge` (or `taskkill /IM msedge.exe` on Windows)
- Restart Edge with debugging: `msedge --remote-debugging-port=9223 --user-data-dir=$env:LOCALAPPDATA\EdgeDebug9223`
- Verify port is listening: `netstat -an | grep 9223` (Windows: `netstat -ano | findstr 9223`)

### venv Not Found
**Issue:** `Setup error: venv not found.`

**Solution:**
```bash
cd ~/Desktop/OmniGraph-Vault
python -m venv venv
./venv/Scripts/activate  # Windows
source venv/bin/activate  # Unix/Mac
pip install -r requirements.txt
```

### Image Server Not Running
**Issue:** Synthesis output contains `![image]()` with broken links

**Cause:** Local HTTP server on port 8765 is not running.

**Solution:**
```bash
cd ~/.hermes/omonigraph-vault
python -m http.server 8765 --directory images &
```

Verify:
```bash
curl http://localhost:8765/
```

---

## Advanced Options

### Verbose Logging
```bash
LOGLEVEL=DEBUG python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json
```

### Test Only One Case
```bash
python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json --case 5
```

### Save Test Results to JSON
```bash
python skill_runner.py skills/ --test-all --output results.json
```

---

## Development Cycle

### Before Each Commit

1. **Run all skill tests:**
   ```bash
   python skill_runner.py skills/ --test-all
   ```
   Expect exit code 0.

2. **Manual sanity check (pick one test scenario):**
   ```bash
   cd ~/Desktop/OmniGraph-Vault
   source venv/bin/activate
   python ingest_wechat.py "https://mp.weixin.qq.com/s/xyzabc..."
   python kg_synthesize.py "What did I just ingest?" hybrid
   ```

3. **Check synthesis output:**
   ```bash
   cat ~/.hermes/omonigraph-vault/synthesis_output.md
   ```

4. **Commit with message:**
   ```bash
   git add skills/
   git commit -m "docs: update omnigraph_query SKILL.md description per SkillHub"
   ```

---

## For CI/CD Integration

### Exit Codes
- `0` — all tests passed
- `1` — one or more tests failed
- `2` — setup error (missing env var, venv not found)

Use in CI pipelines:
```yaml
- name: Run skill tests
  run: python skill_runner.py skills/ --test-all
  # GitHub Actions auto-fails if exit code != 0
```

### Test Results Format
When `--output` is specified, `skill_runner.py` writes JSON:
```json
{
  "summary": {
    "total": 19,
    "passed": 19,
    "failed": 0,
    "exit_code": 0
  },
  "skills": [
    {
      "name": "omnigraph_ingest",
      "cases": [
        {
          "id": 0,
          "name": "ingest_weChat_url",
          "passed": true
        }
      ]
    }
  ]
}
```
