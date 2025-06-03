# Visualisation des Recommandations à Froid

Cette section présente l'analyse et la visualisation des recommandations générées par notre système de recommandation Spark. Les recommandations produites sont stockées dans deux formats complémentaires pour faciliter l'analyse et le monitoring.

## Architecture de Stockage des Recommandations

Les recommandations générées par le modèle Spark sont distribuées via deux canaux :

- **Export CSV** : Sauvegarde dans un fichier `merged_recommendations.csv` pour analyse batch
- **Stockage InfluxDB** : Envoi en temps réel pour monitoring et analyse temporelle

### Structure de la Table InfluxDB

Les recommandations sont stockées dans InfluxDB avec la structure suivante :
![Capture d'écran 2025-05-26 182734.png](images%2FCapture%20d%27%C3%A9cran%202025-05-26%20182734.png)
![Capture d'écran 2025-05-26 195331.png](images%2FCapture%20d%27%C3%A9cran%202025-05-26%20195331.png)

*Capture d'écran à insérer : Structure de la table des recommandations dans InfluxDB*

Cette base de données temporelle permet un suivi en temps réel des performances du système de recommandation et facilite la création de dashboards de monitoring.

## Analyse des Données de Recommandation

Le script `visualize_recommendations.py` charge et analyse les données depuis le fichier CSV mergé. Les données analysées sont identiques à celles stockées dans InfluxDB, garantissant la cohérence entre les analyses batch et temps réel.

### Chargement et Traitement des Données

```python
# Chargement du fichier CSV consolidé
df = pd.read_csv("./results/merged_recommendations.csv")

# Génération automatique de 8 visualisations principales
# - Distribution des scores
# - Top catégories et marques
# - Relations prix/score
# - Analyse par utilisateur
```

## Résultats des Visualisations

### Distribution des Scores de Recommandation
![aed12cf4-5991-415d-9a32-867d28ad3301.png](images%2Faed12cf4-5991-415d-9a32-867d28ad3301.png)

La distribution des scores montre une concentration importante des recommandations autour de scores faibles (0-100), avec quelques pics isolés à des scores plus élevés. Cette distribution suggère que la majorité des recommandations sont de qualité standard, avec quelques recommandations exceptionnelles.

### Top 10 Catégories Recommandées
![a94eb5fa-7842-40d8-85b0-b79360b4ea29.png](images%2Fa94eb5fa-7842-40d8-85b0-b79360b4ea29.png)
L'électronique domine largement avec plus de 400K recommandations, suivie par les appareils électroménagers (~90K). Cette répartition reflète probablement les habitudes d'achat des utilisateurs et la disponibilité des produits dans ces catégories.

### Top 10 Marques Recommandées

![8db3703b-6230-415c-a389-1a9c07a1798f.png](images%2F8db3703b-6230-415c-a389-1a9c07a1798f.png)

Apple et Samsung se positionnent comme les marques les plus recommandées, avec respectivement ~240K et ~200K recommandations. Cette dominance s'explique par leur présence forte dans les catégories électroniques populaires.

### Relation Score vs Prix Moyen
![980174d7-e8fa-413f-8903-020be2726a8b.png](images%2F980174d7-e8fa-413f-8903-020be2726a8b.png)

Le graphique de dispersion révèle une absence de corrélation claire entre le prix et le score de recommandation. Les produits à tous niveaux de prix peuvent obtenir des scores élevés, suggérant que l'algorithme privilégie la pertinence utilisateur plutôt que la valeur monétaire.

### Performance par Catégorie et Marque

![f94a8e11-de91-4fbc-ab0e-b0a49bff4448.png](images%2Ff94a8e11-de91-4fbc-ab0e-b0a49bff4448.png)

L'électronique obtient le score moyen le plus élevé (~15), confirmant la qualité des recommandations dans cette catégorie dominante.

![aa35d47d-6b94-49e3-8caa-308e4dca96f4.png](images%2Faa35d47d-6b94-49e3-8caa-308e4dca96f4.png)

Samsung présente le score moyen le plus élevé (~18), suivi d'Apple (~10), suggérant une forte adéquation entre ces marques et les préférences utilisateurs.

### Distribution des Prix
![26d3b002-d87b-4e3d-b9f2-ed718171487b.png](images%2F26d3b002-d87b-4e3d-b9f2-ed718171487b.png)
La distribution des prix montre plusieurs pics distincts, suggérant des gammes de prix privilégiées par les utilisateurs. La présence de pics autour de 150€, 250€ et 450€ indique des segments de marché bien définis.

## Synthèse

Les visualisations révèlent un système de recommandation équilibré avec :
- Une concentration sur l'électronique et les grandes marques
- Des scores de recommandation indépendants du prix
- Une distribution équitable entre utilisateurs
- Des segments de prix clairement identifiés

Ces analyses, disponibles en temps réel via InfluxDB et en batch via les exports CSV, permettent un monitoring continu de la qualité des recommandations.