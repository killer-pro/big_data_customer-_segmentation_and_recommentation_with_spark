# Cahier des charges technique — `modele1.py`

## 1. Introduction

Ce document décrit le fonctionnement, l'architecture et les choix techniques du script `modele1.py`, qui constitue le cœur du pipeline de segmentation et de recommandation client pour une plateforme e-commerce, en utilisant Apache Spark et PySpark.

---

## 2. Objectifs du script

- **Prétraitement et analyse des comportements utilisateurs**
- **Segmentation RFM (Récence, Fréquence, Montant)**
- **Clustering comportemental (K-means)**
- **Fusion des segmentations pour des profils utilisateurs enrichis**
- **Système de recommandation de produits (ALS)**
- **Sauvegarde des résultats et visualisations**

---

## 3. Dépendances principales

- Python 3.x
- PySpark
- Numpy
- Matplotlib
- Logging (standard Python)

---

## 4. Structure générale du code

### 4.1. Initialisation et configuration
- **Gestion des logs** : Fichier et console
- **Définition des chemins de données, modèles, résultats**
- **Création des dossiers nécessaires**

### 4.2. Fonctions utilitaires
- `find_latest_file` : Recherche le fichier le plus récent selon un pattern
- `MemoryManager` : Gestion du cache Spark pour éviter les fuites mémoire

### 4.3. Préparation des données
- **RFM** :
  - Nettoyage, gestion des valeurs manquantes
  - Découpage en buckets (quantiles) pour récence, fréquence, montant
  - Attribution de segments RFM (Champions, Loyal, etc.)
- **Clustering comportemental** :
  - Sélection de variables comportementales
  - Vectorisation et standardisation
  - Préparation pour K-means

### 4.4. Modélisation
- **K-means** :
  - Recherche du nombre optimal de clusters (score silhouette)
  - Entraînement et sauvegarde du modèle
  - Analyse des clusters (statistiques descriptives)
- **Fusion des segmentations** :
  - Jointure des résultats RFM et K-means
  - Attribution d'un segment comportemental explicite
  - Analyse des affinités entre segments

### 4.5. Recommandation de produits
- **Préparation des interactions** :
  - Construction d'un score implicite par type d'événement (vue, panier, achat, suppression)
- **ALS (Alternating Least Squares)** :
  - Entraînement avec validation croisée
  - Évaluation (RMSE)
  - Génération de recommandations personnalisées

### 4.6. Sauvegarde et visualisation
- Sauvegarde des modèles, segmentations, profils utilisateurs
- Génération de graphiques (score silhouette)

---

## 5. Détail des principales fonctions

### 5.1. `prepare_rfm_segmentation(user_df)`
- Prépare les données pour la segmentation RFM
- Gère les valeurs manquantes, crée des scores et segments RFM robustes

### 5.2. `prepare_behavioral_clustering(user_df)`
- Sélectionne et prépare les variables pour le clustering
- Applique vectorisation et standardisation

### 5.3. `train_kmeans_model(df, feature_col, k_values)`
- Entraîne plusieurs modèles K-means
- Sélectionne le meilleur selon le score silhouette
- Sauvegarde le modèle et la courbe d'optimisation

### 5.4. `combine_segmentations(cluster_df, rfm_df)`
- Fusionne les résultats RFM et K-means
- Attribue des labels explicites aux clusters
- Analyse les affinités entre segments

### 5.5. `prepare_interaction_data(df)`
- Prépare les données d'interaction utilisateur-produit pour la recommandation
- Calcule un score implicite pondéré

### 5.6. `train_recommendation_models(interactions_df)`
- Entraîne un modèle ALS avec validation croisée
- Évalue la performance (RMSE)
- Sauvegarde le modèle

### 5.7. `generate_recommendations(als_model, user_id, spark, ...)`
- Génère des recommandations personnalisées pour un utilisateur

---

## 6. Architecture et choix techniques

- **Spark local** : Exécution sur plusieurs threads (`local[8]`), paramétrage mémoire optimisé
- **Gestion mémoire** : Cache/décache explicite des DataFrames
- **Robustesse** : Gestion des erreurs, logs détaillés, gestion des cas particuliers (valeurs manquantes, clusters vides)
- **Extensibilité** : Possibilité d'ajouter d'autres types de segmentations ou de modèles de recommandation

---

## 7. Points d'attention et limitations

- **Exécution locale** : Peut être limitée par la RAM/CPU de la machine
- **Compatibilité Windows** : Attention aux chemins et à la version de Python
- **Gestion des erreurs Spark** : Certaines erreurs (ex : workers Python) sont liées à l'environnement, pas au code métier

---

## 8. Conclusion

Le script `modele1.py` propose une chaîne complète de traitement, segmentation et recommandation pour l'e-commerce, en s'appuyant sur Spark pour la scalabilité et la performance. Il est conçu pour être robuste, modulaire et facilement extensible.

---

*Document généré automatiquement à partir de l'analyse du code source.* 