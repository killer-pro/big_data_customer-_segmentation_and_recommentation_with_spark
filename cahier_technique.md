# Cahier des Charges Technique
## Projet d'Analyse Comportementale et Système de Recommandation

## 1. Présentation du Projet

### 1.1 Contexte
Développement d'une solution d'analyse comportementale des utilisateurs et d'un système de recommandation de produits basés sur les données e-commerce. Le projet s'inscrit dans un cadre académique avec utilisation de technologies big data et d'intelligence artificielle.

### 1.2 Objectifs Principaux
- Analyser les comportements utilisateurs et identifier des patterns de navigation/achat
- Segmenter les clients selon leurs préférences et comportements
- Développer un système de recommandation personnalisé
- Simuler un environnement temps réel pour le traitement des données

### 1.3 Données Disponibles
- Deux datasets au format CSV représentant les événements e-commerce (octobre et novembre)
- Structure: event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session
- Volume estimé: plusieurs dizaines de millions d'enregistrements

## 2. Architecture Technique

### 2.1 Infrastructure
- **Environnement d'exécution**: Windows local
- **Traitement Big Data**: Apache Spark (PySpark)
- **Stockage**: HDFS local
- **Visualisation**: Grafana
- **Source de données temporelles**: InfluxDB

### 2.2 Schéma Architectural
```
[Fichiers CSV] → [HDFS] → [Spark Processing] → [InfluxDB] → [Grafana]
                   ↓              ↓
            [Modèles ML]  [Temp Storage/Results]
```

## 3. Spécifications Fonctionnelles

### 3.1 Module d'Analyse Comportementale
#### 3.1.1 Fonctionnalités
- Extraction et quantification des séquences de navigation
- Calcul des indicateurs comportementaux par utilisateur/session
- Détection des affinités produits/catégories
- Analyse temporelle des interactions

#### 3.1.2 Métriques à Calculer
- Fréquence de visite par utilisateur
- Durée moyenne des sessions
- Taux de conversion vue → achat
- Produits/catégories les plus consultés
- Distribution horaire des activités

### 3.2 Module de Segmentation Client
#### 3.2.1 Fonctionnalités
- Segmentation initiale basée sur données historiques (octobre)
- Mise à jour incrémentale des segments avec nouvelles données (novembre)
- Classification des nouveaux utilisateurs dans les segments existants

#### 3.2.2 Algorithmes et Méthodes
- K-means clustering pour la segmentation principale (Spark MLlib)
- Analyse RFM (Recency, Frequency, Monetary)
- Validation des segments via silhouette score

### 3.3 Système de Recommandation
#### 3.3.1 Fonctionnalités
- Recommandations basées sur le filtrage collaboratif
- Recommandations basées sur le contenu (catégorie, marque, prix)
- Ajustement des recommandations par segment client
- Évaluation continue de la pertinence des recommandations

#### 3.3.2 Algorithmes et Méthodes
- ALS (Alternating Least Squares) pour le filtrage collaboratif
- TF-IDF et similarité cosinus pour le contenu
- Modèles hybrides pondérés

### 3.4 Module de Simulation Temps Réel
#### 3.4.1 Fonctionnalités
- Découpage du dataset de novembre en micro-batches
- Ingestion cadencée des données vers Spark Streaming
- Mise à jour incrémentale des modèles
- Écriture temps réel des résultats dans InfluxDB

#### 3.4.2 Spécifications
- Fréquence de simulation: toutes les 10 secondes
- Agrégation par heures/journées des données d'origine
- Conservation des timestamps originaux pour l'analyse

## 4. Spécifications Techniques

### 4.1 Configuration Spark
- **Mode**: Local standalone
- **Mémoire allouée**: 8-16 Go (selon machine)
- **Parallélisme**: 4 cores minimum
- **Checkpointing**: Activé pour Spark Streaming

### 4.2 Structure de Données
- **Format principal**: Spark DataFrame
- **Partitionnement HDFS**: Par date
- **Schéma de stockage intermédiaire**:
  ```
  /data/raw/              # Données brutes
  /data/processed/        # Données transformées
  /data/models/           # Modèles entraînés
  /data/temp/             # Résultats intermédiaires
  ```

### 4.3 Modèles ML
- **Entraînement initial**: Batch processing sur données d'octobre
- **Mise à jour**: Incrémentale lors de la simulation temps réel
- **Persistance**: Sauvegarde des modèles au format Spark ML

### 4.4 InfluxDB
- **Base de données**: `ecommerce_analytics`
- **Mesures principales**:
  - `user_behavior`
  - `segment_evolution`
  - `recommendation_metrics`
  - `product_popularity`
- **Rétention des données**: 30 jours

### 4.5 Grafana
- **Connexion**: InfluxDB comme datasource principale
- **Refresh rate**: 5 secondes
- **Dashboards requis**:
  1. Vue d'ensemble comportementale
  2. Segmentation client et évolution
  3. Performance des recommandations
  4. Activité temps réel

## 5. Phases de Développement

### 5.1 Phase 1: Préparation et Analyses Statiques
- Configuration de l'environnement technique
- Traitement et analyse exploratoire des données d'octobre
- Développement des modèles de segmentation initiaux
- Entraînement du système de recommandation de base

### 5.2 Phase 2: Développement de la Simulation Temps Réel
- Mise en place de Spark Structured Streaming
- Développement du mécanisme de simulation (batches de novembre)
- Configuration d'InfluxDB et intégration avec Spark
- Développement des mécanismes de mise à jour incrémentale

### 5.3 Phase 3: Visualisation et Tableaux de Bord
- Configuration de Grafana
- Création des dashboards analytiques
- Mise en place des métriques temps réel
- Tests d'intégration bout-en-bout

### 5.4 Phase 4: Tests et Optimisation
- Tests de charge
- Optimisation des performances Spark
- Ajustement des algorithmes ML
- Finalisation de la documentation

## 6. Livrables Attendus

### 6.1 Code Source
- Scripts PySpark pour l'analyse comportementale
- Scripts pour les modèles de segmentation et recommandation
- Code de simulation temps réel
- Configuration Grafana (exportée)

### 6.2 Documentation
- Rapport technique complet
- Guide d'installation et configuration
- Documentation des APIs et modules
- Analyse des résultats et interprétations

### 6.3 Démonstration
- Présentation fonctionnelle du système
- Démonstration des dashboards temps réel
- Cas d'utilisation concrets avec données de novembre

## 7. Contraintes Techniques

### 7.1 Performance
- Temps de traitement d'un batch < 5 secondes
- Latence de mise à jour des visualisations < 10 secondes
- Capacité à traiter au moins 10 000 événements par batch

### 7.2 Qualité
- Pertinence des recommandations > 70% (mesurée par validation croisée)
- Stabilité des segments client (variation < 15% entre batches)
- Documentation complète du code (> 80% de couverture)

### 7.3 Environnement
- Compatibilité Windows garantie
- Possibilité d'exécution sur une machine avec 16 Go RAM
- Installation simplifiée (scripts d'automatisation)

## 8. Outils et Bibliothèques

### 8.1 Framework Principal
- Apache Spark 3.4+ / PySpark
- Python 3.8+

### 8.2 Bibliothèques ML
- Spark MLlib
- scikit-learn (pour validation hors-Spark)
- pandas (pour manipulations pré/post traitement)

### 8.3 Stockage et Visualisation
- Hadoop HDFS 3.x
- InfluxDB 2.x
- Grafana 9.x

### 8.4 Outils Annexes
- Git pour versionning
- Jupyter Notebooks pour prototypage
- Docker pour conteneurisation (optionnel)

## 9. Critères d'Acceptation

1. Capacité à traiter l'intégralité des données d'octobre et novembre
2. Convergence des algorithmes de segmentation
3. Pertinence des recommandations validée par métriques objectives
4. Performance temps réel conforme aux spécifications
5. Tableaux de bord Grafana fonctionnels et informatifs
6. Documentation technique complète et claire
