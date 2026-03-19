# IFS-004: Token & Signing Interface

*How Rondo handles signing tokens — passes tokens to workers so they can sign on behalf of the issuer.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** classified
**Clearance:** not-cleared
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-001 (Core), STD-008 (Security)
**Connects to:** OB-IFS-004 (Token & Signing — master spec)

---

## 1. Purpose

Rondo's side of the token signing interface. Rondo TRANSPORTS tokens to workers so they can sign code on behalf of the issuer. Rondo itself never signs — it's the courier.

---

## 3. Requirements

### Token Transport

1. When OAPayload contains auth.token: pass it to worker subprocess
2. Token passed via environment variable to worker (not CLI arg — args visible in process list)
3. Worker receives token → can call `caliber-sign` using that token
4. Token never logged — masked in all output as `***TOKEN***`

### Worker Signing

5. Workers in worktrees can sign files using the passed token
6. Worker calls Rust binary for signing — never implements signing logic
7. If no token passed: worker skips signing, reports unsigned

### Spool Signing

8. Rondo spool files (results waiting for pickup) signed with session token if available
9. Signed spool files verifiable by OB on pickup — proves results are authentic
10. Unsigned spool files accepted with WARNING — backwards compatible

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial spec. Token transport to workers, spool signing. 10 requirements. Session 79. |
