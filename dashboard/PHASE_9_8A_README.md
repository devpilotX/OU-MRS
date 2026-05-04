# Dashboard 2.0 - Phase 9.8a Foundation

These three files are the design system foundation. They are NOT yet wired into
the existing dashboard templates - that is Phase 9.8b (tomorrow evening, after
market close at 15:30 IST).

Files:
- static/css/tokens.css - design tokens, dark/light themes, base ou-card styles
- static/js/components/Card.js - reusable OuCard vanilla JS component
- static/js/theme-toggle.js - dark/light toggle persisting in localStorage

Phase 9.8b plan:
1. Add link tag for tokens.css in dashboard base template
2. Add Card.js script tag before closing body
3. Add theme-toggle.js script tag before closing body
4. Migrate one card at a time to use the new ou-card class
5. Remove old hand-rolled CSS once all cards are migrated

Status: foundation only, no template changes, no production risk.
