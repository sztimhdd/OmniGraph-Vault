# wechat-cdp-credential-refresh

Copied from Hermes session 20260524-211033 (quick `260524-tvg` Track C).

## Runtime requirements

This skill ONLY runs on a Windows host with Microsoft Edge launched with
`--remote-debugging-port=9223` (CDP). Hermes is currently the only such
machine in this project; running this skill on Aliyun or any Linux box
will fail at the CDP-connect step.

## Usage

See SKILL.md for the canonical instructions. Operator-side wrapper /
when-to-trigger guidance lives in `docs/runbooks/wechat-cookie-refresh.md`.

## Do not commit

- Cookie values, TOKEN values — these are runtime data, never source-of-truth
- The output `kol_config.py` produced by this skill (gitignored)
