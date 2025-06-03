# big_data_customer-_segmentation_and_recommentation_with_spark

# 1. Présentation du Projet

## Contexte

Le présent projet vise à concevoir une solution d’analyse comportementale des utilisateurs d’une plateforme e-commerce, avec pour finalité l’élaboration d’un système de recommandation intelligent. Ce projet, mené dans un cadre académique, s’appuie sur des technologies Big Data et des approches d’intelligence artificielle afin de traiter efficacement des volumes importants de données générés par les utilisateurs.

## Objectifs du Projet

Le projet vise à concevoir une solution complète d’analyse comportementale et de recommandation intelligente dans un contexte e-commerce. Pour cela, plusieurs objectifs principaux ont été définis :

### • Compréhension et modélisation des comportements utilisateurs

L’objectif initial est d’analyser en profondeur les comportements de navigation et d’achat des utilisateurs à partir des données de logs collectées sur une plateforme e-commerce. Il s’agit notamment d’identifier les actions réalisées par les utilisateurs (consultations, ajouts au panier, achats), d’étudier la chronologie et la fréquence de ces actions, et d’en extraire des tendances comportementales significatives. Ces analyses doivent permettre d’établir un modèle représentatif des interactions typiques entre un utilisateur et la plateforme.

### • Identification des patterns d’interactions et des profils types

À partir des données collectées, il est essentiel d’identifier des schémas d’interactions récurrents, appelés patterns, permettant de regrouper les utilisateurs selon des comportements similaires. Cette étape vise à faire émerger des profils types de clients (par exemple : acheteurs impulsifs, visiteurs réguliers non acheteurs, utilisateurs sensibles au prix, etc.), facilitant ainsi une segmentation fine de la clientèle et une personnalisation plus pertinente des actions marketing ou commerciales.

### • Mise en place d’un système de recommandation dynamique et personnalisé

Sur la base des préférences observées (historique de navigation, fréquence d’achat, catégories préférées, marques consultées), un système de recommandation doit être développé. Ce système devra être capable de proposer de manière dynamique des produits pertinents à chaque utilisateur, en tenant compte à la fois de ses habitudes passées et de son profil comportemental. Les recommandations devront s’appuyer sur des techniques hybrides combinant filtrage collaboratif, analyse de contenu, et segmentation client.

### • Simulation d’un environnement temps réel pour évaluation des performances

Enfin, une infrastructure de simulation en temps réel sera mise en place afin de tester la robustesse et la réactivité de l’ensemble du système. Cette simulation permettra de reproduire l’arrivée continue des données, de déclencher le traitement de ces flux par les modules analytiques et de mesurer les performances en conditions quasi-réelles.

## Données

Les jeux de données fournis sont au format CSV et couvrent les événements de navigation et d’achat sur les mois d’octobre et novembre. Chaque enregistrement contient des informations sur le type d’événement, les produits concernés, les catégories, la marque, le prix, l’utilisateur et sa session. Le volume de données est estimé à plusieurs dizaines de millions de lignes, ce qui justifie l’adoption d’une architecture Big Data.

---

# 2. Architecture Technique

## Infrastructure

L’environnement repose sur une machine locale Windows (8 à 16 Go RAM). Apache Spark (mode local avec PySpark) assure le traitement. Les données sont stockées localement dans un HDFS simulé. InfluxDB est utilisé pour les métriques, visualisées via Grafana.

## Schéma architectural

Les fichiers CSV sont ingérés dans HDFS, traités via Spark, puis les résultats sont stockés dans InfluxDB et visualisés dans Grafana. Les modèles ML sont entraînés et mis à jour en parallèle, avec un stockage intermédiaire pour faciliter les analyses.

---

# 3. Spécifications Fonctionnelles

## Analyse comportementale

Identification des séquences typiques et génération d’indicateurs (fréquence de visite, durée des sessions, taux de conversion, etc.).

## Segmentation client

Initialement réalisée avec K-means sur les données d’octobre, puis affinée via l’analyse RFM. Mise à jour incrémentale avec les données de novembre.

## Système de recommandation

Techniques hybrides combinant :
- Filtrage collaboratif (ALS)
- Analyse de contenu (TF-IDF, similarité cosinus)
- Pondération basée sur le segment client

## Simulation temps réel

Injection des données en micro-lots dans Spark Streaming toutes les 10s. Mise à jour continue des modèles et enregistrement dans InfluxDB.

---

# 4. Spécifications Techniques

## Spark

- Mode standalone local
- Parallélisme : 4 cœurs min
- Mémoire : jusqu’à 16 Go
- Checkpointing activé pour le streaming

## Structure des données

- `/data/raw/` : données brutes  
- `/data/processed/` : données nettoyées  
- `/data/models/` : modèles entraînés  
- `/data/temp/` : résultats intermédiaires  

## Modèles de Machine Learning

- Entraînés en batch sur les données d’octobre
- Mise à jour incrémentale en streaming
- Persistés via Spark ML

## InfluxDB & Grafana

- Stockage des métriques utilisateur et produit
- Tableaux de bord Grafana, actualisés toutes les 5s

---

# 5. Phases de Développement

Le développement est structuré en quatre phases clés :

## 🔹 Phase 1 : Préparation, EDA, premiers modèles

- Installation et configuration des outils (Spark, Kafka, Jupyter)
- Nettoyage et normalisation des données
- EDA pour compréhension des données
- Modèles de clustering et segmentation

## 🔹 Phase 2 : Simulation temps réel et modèles adaptatifs

- Pipeline d’ingestion en micro-lots avec Kafka ou Spark Streaming
- Modules de traitement en flux
- Persistance des résultats intermédiaires

## 🔹 Phase 3 : Intégration des métriques et dashboards

- Sélection des indicateurs clés
- Monitoring et alerting
- Création de dashboards dynamiques (Grafana, Kibana)

## 🔹 Phase 4 : Tests de charge, optimisation, finalisation

- Tests de scalabilité
- Optimisation (latence, ressources, précision)
- Documentation technique complète
- Feedback utilisateurs et ajustements finaux
