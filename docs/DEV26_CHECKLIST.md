# Dev.26 — checklist de validation

- [x] Branche créée depuis dev.25 validée terrain.
- [x] Contrat HA-MCP 8.3.0 relu dans la source officielle.
- [x] Bornes fixes définies : 6 candidats, 3 traces/candidat, 1 détail.
- [x] Détail limité à trigger/conditions/actions/error.
- [x] Variables supprimées de la sortie compacte.
- [x] Aucun appel sans événement History horodaté.
- [x] Aucun appel si readOnlyHint != true.
- [x] causal_verdict = null.
- [x] investigator_status_unchanged = true.
- [ ] CI GitHub Actions verte.
- [ ] Image privée dev.26 construite et manifeste vérifié.
- [ ] Installation terrain — uniquement après Go explicite séparé.
- [ ] Test terrain de recherche bornée.
