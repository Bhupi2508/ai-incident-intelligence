# Security

## Reporting a vulnerability
Please use GitHub's **private vulnerability reporting** (Security tab > "Report a vulnerability") instead of opening a public issue. Don't include real credentials or customer data in reports.

## Handling secrets
- Provider API keys belong in server-side environment variables or an untracked `.env`. Never commit them.
- If a key is ever committed or shared, revoke and rotate it at the provider immediately; deleting the file or commit is not enough.

## Scope and known gaps
This is a demo-grade application. It has **no authentication or rate limiting**; don't expose it to untrusted networks without adding both. See "Known limitations" in the README.
