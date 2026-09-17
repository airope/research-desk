# Corrections de l'audit — 17 septembre 2026

> État au terme du durcissement. L’ajout ultérieur des [fournisseurs API](llm-providers.md) permet désormais une IA serveur configurée, distincte du mode Codex personnel.

Les dix constats de l'audit ont reçu des corrections dans le code ou le parcours d'exploitation. La démonstration locale a été migrée et relancée, sans modification des conclusions des rapports. Il ne s'agit pas d'une certification de production : les limites d'environnement ci-dessous restent explicites.

| Constat | Correction livrée | Preuve principale |
|---|---|---|
| A1 Configuration | Profil production strict, secrets/hosts obligatoires, DEBUG et Codex personnel refusés, cookies Secure, HTTPS/HSTS | Tests settings ; `check --deploy --fail-level WARNING` réussi avec deux exclusions justifiées W005/W021 (sous-domaines et preload) |
| A2 Secrets | `.env*` exclus de Git/Docker sauf exemple ; scan de signatures de credentials en CI ; fonctionnement de l'environnement documenté | `git check-ignore` confirme `.env`, `.env.local`, `.env.production` ignorés et exemple conservé |
| A3 Quotas | Compteurs PostgreSQL, limites de connexion IP/compte, écritures et recherches par compte, création quotidienne, admission atomique de jobs par utilisateur/globale | Tests concurrence multi-connexions, refus 429 avant appels externes, annulation toujours possible, méthodes non autorisées refusées |
| A4 Recherche | GET/HEAD en lecture seule, `count` de complétude puis `msearch` ; indexation dans le worker | Test réel et journaux de la page : aucun bulk pendant la recherche |
| A5 Rétention index | IDs par source, indexation idempotente, purge anciennes révisions et scopes supprimés ; commande de rattrapage | Contrat Elasticsearch réel, nettoyage isolé entre dossiers |
| A6 Stockage | Sources immuables dédupliquées par dossier ; références dans les rapports et versions ; listes/statut légers ; progression mise à jour par colonnes | Tests stockage/historique/confidentialité ; dossier existant compacté avec égalité vérifiée |
| A7 PDF | Environnement minimal, répertoire dédié, sandbox-exec macOS / Bubblewrap Linux, refus fermé sans isolation | Vrai PDF extrait ; test hôte refusant fichier privé et réseau |
| A8 Durées | Budget réseau commun PDF/INSPIRE, interruption des flux lents et en-têtes, verrou arXiv interprocess ; heartbeat avec délais SQL | Tests serveurs locaux lents et annulation ; pas de thread SQL bloqué indéfiniment sur un verrou |
| A9 Installation | Worker recherche dans Compose, variables ES, contrôles production et contrat ES réel en CI, guide de déploiement | Configuration et tests validés ; exécution Docker restant à vérifier sur hôte équipé |
| A10 Maintenabilité | Commandes métier extraites des vues, état rechargé sous verrou, statuts/étapes centralisés et contraintes SQL, index de file/liste | Tests de concurrence, autorisation, état périmé, annulation et suppression pendant traitement |

## Validation exécutée

- Suite complète avec intégrations PDF/HTTP activées : **265 tests réussis**, un test Elasticsearch réservé à son environnement dédié ignoré dans cette invocation.
- Ce contrat Elasticsearch a ensuite été exécuté séparément contre le moteur local : **1 test réussi**, soit **266 tests validés** sur ces deux exécutions. Deux scopes UUID temporaires ont été nettoyés ; aucun index partagé ni dossier utilisateur supprimé.
- Ruff et format : réussis ; contrôles Django, cohérence des migrations et OpenAPI : réussis.
- Migration `0005_audit_hardening` appliquée. Sauvegarde locale préalable à la compaction dans `/tmp/srr-before-source-compaction-20260917.dump` (fichier privé ; emplacement temporaire, pas une stratégie de sauvegarde durable).
- Un dossier existant compacté et relu à contenu égal. Son index a été reconstruit avec purge des anciennes révisions.
- Vérification navigateur après relance : rapport, page PDF 11 et **8 anciennes versions** présents ; recherche « latency » renvoyant des passages Elasticsearch/BM25.

La vérification n'a pas déclenché une nouvelle synthèse LLM payante ou consommé volontairement un nouveau rapport sur l'abonnement personnel. Le chemin IA utilise les tests de contrats et les rapports existants pour cette régression.

## Revue contradictoire et résolution

| Problème découvert pendant la revue | Résolution |
|---|---|
| Exception de quota figée incompatible avec la gestion de traceback | Exception rendue mutable |
| HEAD et autres méthodes pouvaient éviter le quota de recherche | GET/HEAD limités ; autres méthodes refusées avec 405 |
| Vérification du login CLI répétée à chaque page | Cache 30 secondes avec verrou, désactivation contrôlée avant le cache |
| Appel métier depuis un objet périmé | Rechargement et verrouillage dans le service lui-même |
| Suppression du dossier pendant le travail | Traité comme annulation, sans tuer le worker |
| Heartbeat pouvant attendre une rowlock longtemps | Délais PostgreSQL locaux sur verrou et requête |
| Résolution des références pendant leur sauvegarde | Suspension temporaire de l'hydratation, insertion atomique, contrôle des références privées |
| Purge de snapshots pendant qu'un lecteur détient d'anciennes références | Purge uniquement avec `--prune-unreferenced --offline`, arrêt préalable web/workers documenté |
| Budget PDF ne couvrant pas INSPIRE et les en-têtes lents | Helper réseau commun, socket capturée avant lecture des en-têtes, tests réels |

Aucune faille critique supplémentaire n'a été identifiée par cette revue. Ce résultat reste limité au périmètre inspecté et testé.

## Exploitation et limites restantes

Voir [le guide de déploiement](deployment.md).

- Docker n'est pas installé sur ce poste. Le build de l'image, le lancement Compose et Bubblewrap sous Linux doivent être vérifiés sur l'hôte cible. La CI comporte désormais le service Elasticsearch d'intégration, mais elle n'a pas été exécutée sur GitHub pendant cette tâche.
- Le mode ChatGPT/Codex reste personnel et local. Aucun fournisseur IA destiné à un serveur partagé n'a été ajouté.
- Les quotas bornent le nombre de travaux ; ils ne mesurent pas un coût monétaire ni des tokens non exposés par le fournisseur.
- La résolution DNS dépend du resolver système. Les limites HTTP interrompent connexion/lecture une fois la socket accessible ; elles ne tuent pas un syscall DNS bloqué. Les clients injectés doivent conserver des connexions neuves pour la garantie sur les en-têtes.
- Le verrou arXiv coordonne les processus d'un même hôte. Des conteneurs doivent partager son fichier ; un déploiement sur plusieurs machines nécessite une coordination distribuée.
- Le nettoyage des sources non référencées est une commande de maintenance **hors trafic**. La compaction sans purge fonctionne en ligne. Programmer également `cleanup_research_limits` quotidiennement et `reindex_research --purge-orphans` pour rattraper une indisponibilité d'Elasticsearch lors d'une suppression.
- Le web peut utiliser une clé Elasticsearch limitée à la lecture ; le worker utilise la clé d'écriture. La démo locale conserve sa clé d'index existante, privée et restreinte. La suppression directe d'un scope par un web en lecture seule échouera sans conséquence sur PostgreSQL et sera rattrapée par la maintenance avec la clé d'écriture.
- Les snapshots doivent passer par la sauvegarde du modèle ; les écritures SQL directes des champs sources restent réservées aux migrations/maintenance. Aucune fonction d'édition de ces snapshots n'est exposée.
- Aucun chiffre de capacité ou gain de qualité scientifique n'est revendiqué : un benchmark représentatif reste nécessaire avant de fixer une capacité de production.
