# Document des Exigences

## Introduction

Le système d'analyse automatique des réclamations SAV d'Atlantem (menuiserie industrielle) permet de traiter en lot des réclamations clients. Chaque réclamation est fournie sous forme de fichier CSV accompagné, le cas échéant, de pièces jointes (photos JPG ou documents PDF). Un agent IA basé sur Strands Agents SDK et AWS Bedrock (Claude claude-sonnet-4-6) analyse le texte de chaque réclamation ainsi que ses pièces jointes, puis produit un CSV enrichi avec quatre champs de classification : type de litige, responsabilité, solution préconisée et précision produit.

## Glossaire

- **Système** : l'application Python d'analyse automatique des réclamations SAV.
- **Agent** : le composant IA basé sur Strands Agents SDK et AWS Bedrock (Claude claude-sonnet-4-6) qui effectue la classification.
- **Réclamation** : une ligne du CSV d'entrée représentant un dossier SAV, contenant au minimum une description texte et un type de produit.
- **Pièce_Jointe** : fichier JPG ou PDF associé à une réclamation, référencé par son chemin ou identifiant dans le CSV d'entrée.
- **CSV_Entrée** : fichier CSV fourni par l'utilisateur contenant les réclamations à analyser.
- **CSV_Sortie** : fichier CSV produit par le Système, reprenant toutes les colonnes du CSV_Entrée et ajoutant les quatre champs de classification.
- **Type_Litige** : classification du motif de la réclamation parmi : Fonctionnement, Produit Abimé, Manque, Non Conformité, Esthétique, Doublon, Prix.
- **Responsabilité** : classification de la partie responsable parmi : Fournisseur, Fabrication, Client, Transport, Hors Garantie, Saisie.
- **Solution** : action préconisée parmi : Envoi Pieces, Envoi Vitrage, Refabrication, Intervention SAV.
- **Précision_Produit** : composant concerné parmi : Crémone/Serrure, Vitrage, Acc Quincaillerie, Moteur.
- **Lot** : ensemble de réclamations traitées en une seule exécution du Système.
- **Confiance** : score numérique entre 0 et 1 indiquant la certitude de l'Agent pour chaque champ classifié.

---

## Exigences

### Exigence 1 : Chargement du CSV d'entrée

**User Story :** En tant qu'opérateur SAV, je veux fournir un fichier CSV de réclamations au Système, afin que toutes les réclamations soient prises en charge pour analyse.

#### Critères d'acceptation

1. THE Système SHALL accepter un fichier CSV_Entrée dont les colonnes minimales obligatoires sont : identifiant de réclamation, description texte et type de produit.
2. WHEN le CSV_Entrée est fourni avec un encodage UTF-8 ou Latin-1, THE Système SHALL détecter automatiquement l'encodage et lire le fichier sans erreur de décodage.
3. IF le CSV_Entrée est absent ou illisible, THEN THE Système SHALL interrompre le traitement et retourner un message d'erreur indiquant le chemin du fichier et la nature du problème.
4. IF une ligne du CSV_Entrée ne contient pas de valeur pour la colonne description texte, THEN THE Système SHALL ignorer cette ligne, la consigner dans un journal d'erreurs et poursuivre le traitement des lignes restantes.
5. WHEN le CSV_Entrée contient plus de 10 000 lignes, THE Système SHALL traiter les réclamations par lots de 100 lignes maximum afin de maîtriser la consommation mémoire.

---

### Exigence 2 : Résolution des pièces jointes

**User Story :** En tant qu'opérateur SAV, je veux que le Système charge automatiquement les photos et documents associés à chaque réclamation, afin que l'Agent dispose de toutes les informations visuelles pour classifier correctement.

#### Critères d'acceptation

1. WHEN une réclamation référence une Pièce_Jointe de format JPG ou PDF, THE Système SHALL charger le fichier correspondant et le transmettre à l'Agent lors de l'analyse de cette réclamation.
2. IF une Pièce_Jointe référencée est introuvable au chemin indiqué, THEN THE Système SHALL consigner l'absence dans le journal d'erreurs et analyser la réclamation sans cette pièce jointe.
3. IF une Pièce_Jointe dépasse 10 Mo, THEN THE Système SHALL rejeter ce fichier, consigner l'événement dans le journal d'erreurs et analyser la réclamation sans cette pièce jointe.
4. THE Système SHALL prendre en charge les formats de pièces jointes JPG et PDF uniquement ; tout autre format SHALL être ignoré et consigné dans le journal d'erreurs.

---

### Exigence 3 : Classification par l'Agent IA

**User Story :** En tant qu'opérateur SAV, je veux que l'Agent IA attribue automatiquement les quatre champs de classification à chaque réclamation, afin de réduire le temps de traitement manuel.

#### Critères d'acceptation

1. WHEN l'Agent reçoit une réclamation, THE Agent SHALL produire une valeur pour chacun des quatre champs : Type_Litige, Responsabilité, Solution et Précision_Produit.
2. THE Agent SHALL choisir la valeur de Type_Litige exclusivement parmi : Fonctionnement, Produit Abimé, Manque, Non Conformité, Esthétique, Doublon, Prix.
3. THE Agent SHALL choisir la valeur de Responsabilité exclusivement parmi : Fournisseur, Fabrication, Client, Transport, Hors Garantie, Saisie.
4. THE Agent SHALL choisir la valeur de Solution exclusivement parmi : Envoi Pieces, Envoi Vitrage, Refabrication, Intervention SAV.
5. THE Agent SHALL choisir la valeur de Précision_Produit exclusivement parmi : Crémone/Serrure, Vitrage, Acc Quincaillerie, Moteur.
6. WHEN l'Agent ne peut pas déterminer une valeur avec une Confiance supérieure à 0,5, THE Agent SHALL attribuer la valeur « Indéterminé » au champ concerné et consigner la réclamation dans le journal d'erreurs.
7. WHEN des Pièces_Jointes sont disponibles pour une réclamation, THE Agent SHALL intégrer leur contenu visuel dans son analyse avant de produire les classifications.
8. IF l'appel à AWS Bedrock échoue pour une réclamation, THEN THE Système SHALL effectuer jusqu'à 3 nouvelles tentatives avec un délai exponentiel de 2 secondes entre chaque tentative avant de marquer la réclamation en erreur.

---

### Exigence 4 : Production du CSV de sortie

**User Story :** En tant qu'opérateur SAV, je veux recevoir un fichier CSV enrichi avec les classifications, afin de pouvoir l'importer directement dans le système de gestion SAV d'Atlantem.

#### Critères d'acceptation

1. WHEN le traitement d'un Lot est terminé, THE Système SHALL produire un CSV_Sortie contenant toutes les colonnes du CSV_Entrée plus les colonnes : Type_Litige, Responsabilité, Solution, Précision_Produit et Confiance pour chacun de ces quatre champs.
2. THE Système SHALL conserver dans le CSV_Sortie l'ordre des lignes identique à celui du CSV_Entrée.
3. THE Système SHALL encoder le CSV_Sortie en UTF-8 avec BOM afin d'assurer la compatibilité avec Microsoft Excel.
4. IF une réclamation a été marquée en erreur, THEN THE Système SHALL inclure cette ligne dans le CSV_Sortie avec les champs de classification vides et une colonne « Erreur » décrivant la cause.
5. WHEN le CSV_Sortie est produit, THE Système SHALL écrire le fichier dans le répertoire de sortie spécifié par l'utilisateur avec un nom incluant la date et l'heure d'exécution au format ISO 8601.

---

### Exigence 5 : Traçabilité et journalisation

**User Story :** En tant qu'administrateur système, je veux disposer d'un journal d'exécution détaillé, afin de diagnostiquer les erreurs et d'auditer les décisions de l'Agent.

#### Critères d'acceptation

1. THE Système SHALL produire un fichier journal horodaté pour chaque exécution, consignant : le nombre de réclamations traitées, le nombre de réclamations en erreur, la durée totale de traitement et la version du modèle AWS Bedrock utilisé.
2. WHEN une réclamation est classifiée avec une Confiance inférieure à 0,7 pour au moins un champ, THE Système SHALL consigner l'identifiant de la réclamation et les valeurs de Confiance concernées dans le journal.
3. IF une erreur inattendue survient pendant le traitement d'une réclamation, THEN THE Système SHALL consigner le message d'erreur complet, la trace d'appel et l'identifiant de la réclamation dans le journal, puis poursuivre le traitement des réclamations suivantes.
4. THE Système SHALL conserver les fichiers journaux pendant une durée minimale de 90 jours dans le répertoire de journalisation configuré.

---

### Exigence 6 : Configuration et paramétrage

**User Story :** En tant qu'administrateur système, je veux pouvoir configurer les paramètres d'exécution du Système, afin d'adapter le comportement aux contraintes d'infrastructure d'Atlantem.

#### Critères d'acceptation

1. THE Système SHALL lire sa configuration depuis un fichier de configuration au format YAML ou depuis des variables d'environnement, les variables d'environnement ayant priorité sur le fichier de configuration.
2. THE Système SHALL exposer les paramètres configurables suivants : région AWS, identifiant du modèle Bedrock, répertoire des pièces jointes, répertoire de sortie, répertoire de journalisation et taille de lot.
3. IF un paramètre obligatoire est absent de la configuration, THEN THE Système SHALL interrompre le démarrage et afficher un message d'erreur listant les paramètres manquants.
4. WHERE la variable d'environnement de région AWS est définie, THE Système SHALL utiliser cette région pour tous les appels à AWS Bedrock.

---

### Exigence 7 : Propriétés de robustesse et de cohérence du parseur de réponse

**User Story :** En tant qu'opérateur SAV, je veux que le Système produise des classifications cohérentes et reproductibles, afin de pouvoir faire confiance aux résultats de l'Agent.

#### Critères d'acceptation

1. THE Parseur SHALL extraire les quatre champs de classification depuis la réponse JSON de l'Agent sans perte d'information.
2. FOR ALL réponses JSON valides de l'Agent, le fait de sérialiser puis désérialiser la réponse SHALL produire un objet de classification équivalent (propriété de round-trip).
3. WHEN le Système traite deux fois la même réclamation avec les mêmes pièces jointes et la même configuration, THE Agent SHALL produire des classifications identiques pour les quatre champs (propriété d'idempotence).
4. IF la réponse de l'Agent ne respecte pas le schéma JSON attendu, THEN THE Parseur SHALL retourner une erreur de parsing structurée indiquant le champ manquant ou invalide, sans lever d'exception non gérée.
5. THE Parseur SHALL valider que chaque valeur extraite appartient à l'ensemble de valeurs autorisées pour le champ correspondant avant d'écrire dans le CSV_Sortie.
