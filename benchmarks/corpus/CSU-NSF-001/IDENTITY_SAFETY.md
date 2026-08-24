# Identity Safety Policy

CSU-NSF-001 is a synthetic benchmark case. Its synthetic roles are represented by stable non-person identifiers, not by names or pseudonyms:

- `CSU-PI-001`: principal investigator role
- `CSU-COI-001`: co-investigator role
- `CSU-VPR-001`: institutional research-official role
- `FED-NEG-001`: federal cost-negotiator role

Fictional biosketch products use `SYN-PUB-*` record identifiers. They are not publications and do not carry human authors, journal assignments, DOIs, volumes, or pages.

Real personal names may appear only as accurate attribution for verified scholarly references or open-license source credits. They must never be used for a synthetic role, signature, credential, project record, or fictional research product.

Run `python tools/validate_identity_safety.py .` before publishing a release.
