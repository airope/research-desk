# Du besoin utilisateur au catalogue utilisable

Référence produit — 17 septembre 2026. **Mise à jour : le premier parcours borné CSV/exemple → INSPIRE → décisions/corrections → exports CSV est maintenant implémenté ; voir [le guide actuel](catalogue-guide.md). Les extensions ci-dessous restent une direction produit.** Proposition fondée sur les capacités publiques des services cités et sur la nouvelle direction donnée par l’utilisateur. Ce n’est pas le compte rendu d’un entretien avec un documentaliste du CERN, ni une description de fonctionnalités toutes livrées.

## But

**Cet outil sert à réunir les listes d’articles scientifiques de plusieurs bases, repérer les doublons et obtenir un catalogue fiable sans devoir tout vérifier à la main.**

Le bénéfice à vérifier : moins de comparaisons manuelles pour mettre à jour une liste, sans perdre les sources ni fusionner des publications différentes. Une proposition de doublon reste une proposition : l’automatisation des décisions est actuellement désactivée.

## Une personne, un travail à terminer

Utilisateur principal retenu : une documentaliste ou une personne responsable de la liste des publications d’un laboratoire.

Sa demande, dans un scénario représentatif : « Je prépare le bilan des publications de mon équipe pour une période donnée. J’ai déjà un catalogue. Je veux trouver les articles qui manquent, éviter de compter deux fois le même et compléter les références avant de transmettre la liste. »

Elle ne vient pas regarder des scores. Elle veut repartir avec une liste exploitable, et savoir ce qui a changé. Ce scénario est une hypothèse de travail à confronter à une personne réelle.

| Travail | Pourquoi une liste est nécessaire | Livrable utile |
|---|---|---|
| Mettre à jour le catalogue du laboratoire — priorité | Retrouver les publications et maintenir des références correctes | Catalogue corrigé + changements à appliquer |
| Préparer un bilan de publications | Ne pas compter deux fois une publication et rendre le périmètre explicite | Tableau des publications retenues et des exclusions |
| Préparer une bibliographie — secondaire | Citer les bons articles dans un document | Bibliographie BibTeX ou RIS |

L’outil ne juge pas la qualité scientifique des articles. Une recherche thématique seule ne prouve pas non plus qu’un article appartient au bilan d’une équipe.

## D’où viennent les listes ?

On récupère d’abord des fiches : titre, auteurs, date, revue, DOI ou identifiant arXiv et lien vers le document. Télécharger tous les PDF n’est pas nécessaire pour ce travail.

Deux services sont particulièrement pertinents dans le contexte CERN :

- **CDS**, le dépôt institutionnel, conserve les productions du CERN. La documentation actuelle indique une migration en cours : un futur connecteur devra vérifier l’interface réellement utilisée et conserver les identifiants historiques. [Documentation officielle CDS](https://repository.cern/docs/).
- **INSPIRE**, pour la littérature en physique des hautes énergies, rassemble notamment des contenus issus d’arXiv, de laboratoires, d’éditeurs et des utilisateurs. [Sources officielles INSPIRE](https://help.inspirehep.net/knowledge-base/inspire-content-sources/).

Les auteurs ou les services de leur groupe peuvent déposer leurs documents dans CDS ; le parcours dépend du département ou de l’expérience. Cela ne signifie pas que nous avons accès aux systèmes internes. [Procédure CERN](https://sis.web.cern.ch/submit-and-publish/how-and-where-submit/document).

INSPIRE fournit une API de lecture et des recherches par auteur, collaboration, institution, dates ou type de document. C’est une première connexion adaptée à un scénario de physique des hautes énergies. [API officielle](https://github.com/inspirehep/rest-api-doc), [recherche officielle](https://help.inspirehep.net/knowledge-base/inspire-paper-search/).

| Entrée proposée | Ce que fait l’utilisateur | Priorité et limite |
|---|---|---|
| Fichier de son catalogue | Dépose un CSV ; vérifie l’aperçu et l’association des colonnes | Première version ; garder les identifiants locaux et signaler les lignes invalides |
| Recherche INSPIRE | Choisit une collaboration ou un auteur, une période et un type | Première connexion à ajouter ; aperçu avant collecte, limites explicites |
| Liste d’identifiants | Colle des DOI ou des identifiants arXiv | Recherche ciblée ; montrer ceux qui n’ont pas été retrouvés |
| Exports BibTeX/RIS | Dépose une bibliographie existante | Extension après CSV ; montrer les informations non importables |
| Crossref/OpenAlex | Complète ou compare les références sélectionnées | Réutiliser les connecteurs existants ; ne pas interroger tout le Web sans périmètre |
| Catalogue interne simulé | Choisit un exemple local clairement marqué « Démonstration » | Permet de vivre le parcours complet sans prétendre être connecté au CERN |
| Base ou service interne réel | Choisit une connexion préparée par un administrateur | Ensuite ; lecture seule et export de changements au départ, configuration propre au système |
| CDS | Sélectionne une collection ou fournit un export compatible | Ensuite ; intégration à qualifier pendant la migration |

Une base interne peut être représentée en démonstration par un catalogue local séparé, avec quelques notices manquantes, incomplètes et dupliquées. Toute altération volontaire doit être étiquetée comme scénario simulé, pas comme erreur réelle du fournisseur.

## Sélection ergonomique : partir du travail, pas du fournisseur

L’écran d’entrée devient « Mes catalogues » avec une action « Mettre à jour un catalogue » et une possibilité « Créer un catalogue ». Chaque travail conserve son propre périmètre ; les résultats ne se mélangent pas dans une file mondiale.

1. **Mon catalogue de départ.** Choisir une liste existante, importer un fichier ou utiliser l’exemple. Prévisualiser les colonnes, les erreurs et les références avant de continuer.
2. **Ce que je cherche.** Choisir une collaboration, une institution, un auteur identifié ou une liste d’identifiants. Les noms sont proposés avec leur identité pour éviter les homonymes. Les mots-clés sont un filtre facultatif.
3. **La période et les documents.** Indiquer des dates et ce qu’elles signifient : année de publication en revue, par exemple. Choisir articles, prépublications ou actes ; préciser si une prépublication doit rester distincte de l’article publié. Ne pas promettre un regroupement de versions qui n’existe pas.
4. **Vérifier la sélection.** Afficher les sources, le volume annoncé s’il est disponible, un échantillon, les limites et le résumé lisible des filtres. Action « Analyser cette sélection ». Pour sélectionner tous les résultats, distinguer explicitement toute la recherche de la seule page affichée.
5. **Suivre et reprendre.** Montrer récupération, analyse et éléments à vérifier ; garder les erreurs et les résultats partiels visibles. Une recherche enregistrée peut être relancée manuellement, avec date et périmètre du nouvel import.

Ne pas demander au documentaliste d’écrire une requête SQL ou de connaître la syntaxe INSPIRE. Les filtres disponibles dépendent de la source ; une fonction non prise en charge doit être indiquée, pas silencieusement ignorée. Une recherche interrompue ou plafonnée ne doit jamais être affichée comme exhaustive.

## Les résultats doivent répondre à « Que dois-je faire ? »

Le premier résultat est un bilan du travail sur CE catalogue : éléments récupérés, éléments déjà présents, nouveaux éléments proposés, cas à vérifier et erreurs d’import. Distinguer le nombre de fiches sources, le nombre de publications regroupées et les problèmes, qui peuvent se recouvrir. Ne pas afficher un pourcentage de confiance non calibré.

| Ce qu’elle repère | Pourquoi c’est important | Action proposée |
|---|---|---|
| Article probablement absent du catalogue local | Compléter la liste | Ajouter, exclure du périmètre ou examiner |
| Deux fiches décrivant potentiellement le même article | Éviter les doublons et les doubles comptes | Regrouper ou garder séparé |
| Même article avec un DOI, une date ou une revue manquants | Rendre la référence trouvable et citable | Accepter un complément en voyant sa source |
| Informations contradictoires | Éviter de propager une erreur | Comparer puis choisir la valeur, ou laisser à vérifier |
| Prépublication, article publié, correction | Ne pas confondre des objets liés | Conserver distincts ; relation de versions à traiter séparément |
| Notice hors périmètre ou auteur homonyme | Éviter un bilan trompeur | Exclure du lot sans supprimer la source |

« Absent du catalogue importé » ne veut pas dire « absent du CERN ». « Aucun doublon trouvé » ne signifie pas « aucun doublon possible ». Un manque documentaire n’est constaté que relativement au catalogue et à la sélection réellement chargés.

Le tableau présente titre, auteurs, année, revue, identifiants, présence dans le catalogue local et action attendue. Les filtres « Nouveaux », « Doublons possibles », « Informations à vérifier » et « Traités » servent le travail. Cliquer ouvre les différences ; les champs identiques restent secondaires. Après décision, passer au cas suivant et permettre de revenir en arrière. Un motif est demandé pour les arbitrages importants, pas pour chaque clic.

## Ce qu’elle récupère et ce qu’elle en fait

Le catalogue final reste consultable dans l’application, avec une ligne par publication selon les décisions prises, ses sources et ses liens. La comparaison de fiches est une étape, pas le livrable final.

- **CSV** : liste retenue pour travailler dans un tableur ou préparer un bilan ; colonnes et encodage documentés.
- **BibTeX/RIS** : bibliographie utilisable dans le flux de rédaction ou un gestionnaire bibliographique ; formats à implémenter et tester.
- **JSON/API** : intégration dans un autre outil ; reprendre l’API existante en ajoutant un périmètre de catalogue stable.
- **Relevé des changements** : ajouts, regroupements, valeurs corrigées, identifiants locaux conservés, exclusions et cas non résolus. Il sert à contrôler ou préparer une mise à jour du système d’origine.

L’utilisateur choisit tout le catalogue ou une sélection. Un export avec des cas non résolus doit l’indiquer et permettre de les inclure avec leur statut ou de les exclure explicitement. Conserver la date, le périmètre et une version reproductible de l’export.

Une connexion de lecture à INSPIRE ne permet pas d’y réécrire des données : l’API documentée est en lecture seule. Pour le MVP, le résultat est exporté et réutilisé par le responsable dans son processus existant. Aucun export ne doit prétendre être directement réimportable dans CDS ou une base interne sans adaptation et validation de leur schéma.

## Première livraison utile

Construire un seul parcours vertical complet : **catalogue CSV ou simulé → sélection INSPIRE → comparaison avec le catalogue → décisions → export CSV et relevé des changements**. Les connecteurs existants restent disponibles pour les comparaisons complémentaires. Éviter de commencer par multiplier les bases connectées.

Ces éléments sont maintenant livrés pour le premier parcours borné : catalogues privés, sélections enregistrées, identifiants locaux, import CSV, recherche INSPIRE guidée, indications de doublons/conflits, exclusion, corrections et exports CSV. Les filtres d’identité avec autocomplétion, les autres connecteurs et les autres formats restent des extensions. La qualité des rapprochements et le gain de temps réel restent à mesurer avec un utilisateur.

## Comment reconnaître que cela sert vraiment

Une personne doit pouvoir partir de son fichier et repartir avec un résultat réutilisable sans terminal ni explication du développeur. Vérifier avec elle cinq situations : nouvel article, vrai doublon, titres proches mais articles différents, champ contradictoire et décision annulée. Tester aussi une erreur d’import et un export partiel.

Comparer sur un même petit corpus le temps passé, le nombre de fiches réellement examinées et les erreurs restantes avec sa méthode actuelle. Aucune économie de temps ni précision ne sera revendiquée avant cette mesure. Si son outil existant fait déjà ce travail aussi bien, ajuster le périmètre au problème encore non résolu plutôt que construire un autre moteur de recherche.
