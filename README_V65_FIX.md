# V6.5 Diverse Media one-click fix

This fixes the V6.4 upgrade package mistake where `APPLY_DIVERSE_MEDIA_FORCE.bat` was omitted.

Recommended: run `APPLY_DIVERSE_MEDIA_SAFE.bat`.
It deletes only `TEST_PLACEHOLDER` assets/links, preserves real/admin-uploaded artwork, then rebuilds diverse semantic media for missing entities.

Use `APPLY_DIVERSE_MEDIA_FORCE.bat` only if every current PRIMARY image is disposable test art.

After completion restart Admin or Ctrl+F5, then run `CHECK_MEDIA_NOW.bat` or the **Check Bot/Web** button.
