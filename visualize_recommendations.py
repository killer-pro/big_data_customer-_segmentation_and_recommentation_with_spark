import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Définir le chemin vers le fichier CSV fusionné
merged_csv_path = "./results/merged_recommendations.csv"

# Vérifier si le fichier existe
if not os.path.exists(merged_csv_path):
    print(f"Error: File not found at {merged_csv_path}")
    print("Please make sure you have run merge_recommendations.py first.")
else:
    # Charger les données
    try:
        df = pd.read_csv(merged_csv_path)
        print(f"Successfully loaded data from {merged_csv_path}. Shape: {df.shape}")

        # --- Visualisations --- 

        # 1. Distribution des scores de recommandation
        plt.figure(figsize=(10, 6))
        sns.histplot(df['rec_score'], bins=50, kde=True)
        plt.title('Distribution des Scores de Recommandation')
        plt.xlabel('Score de Recommandation')
        plt.ylabel('Fréquence')
        plt.grid(axis='y', alpha=0.75)
        plt.show()

        # 2. Top 10 Catégories Recommandées
        top_categories = df['recommended_category_code'].value_counts().nlargest(10)
        plt.figure(figsize=(12, 7))
        top_categories.plot(kind='bar')
        plt.title('Top 10 Catégories Recommandées')
        plt.xlabel('Catégorie')
        plt.ylabel('Nombre de Recommandations')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout() # Ajuste pour éviter le chevauchement
        plt.show()

        # 3. Top 10 Marques Recommandées
        top_brands = df['main_brand'].value_counts().nlargest(10)
        plt.figure(figsize=(12, 7))
        top_brands.plot(kind='bar', color=sns.color_palette('viridis', 10))
        plt.title('Top 10 Marques Recommandées')
        plt.xlabel('Marque')
        plt.ylabel('Nombre de Recommandations')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()

        # 4. Relation entre Score de Recommandation et Prix Moyen
        plt.figure(figsize=(10, 6))
        sns.scatterplot(data=df, x='avg_price', y='rec_score', alpha=0.6)
        plt.title('Score de Recommandation vs Prix Moyen')
        plt.xlabel('Prix Moyen')
        plt.ylabel('Score de Recommandation')
        plt.grid(True, linestyle='--', alpha=0.6)
        # Limiter l'axe x pour mieux visualiser si nécessaire (si quelques prix sont très élevés)
        # plt.xlim(0, 1000) 
        plt.show()

        # 5. Nombre de recommandations par utilisateur (Top N)
        top_users_by_recommendations = df['user_id'].value_counts().nlargest(10)
        plt.figure(figsize=(12, 7))
        top_users_by_recommendations.plot(kind='bar', color=sns.color_palette('plasma', 10))
        plt.title('Top 10 Utilisateurs par Nombre de Recommandations')
        plt.xlabel('ID Utilisateur')
        plt.ylabel('Nombre de Recommandations')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()

        # 6. Score de recommandation moyen par catégorie
        avg_rec_score_by_category = df.groupby('recommended_category_code')['rec_score'].mean().nlargest(10)
        plt.figure(figsize=(12, 7))
        avg_rec_score_by_category.plot(kind='bar', color=sns.color_palette('tab10', 10))
        plt.title('Score de Recommandation Moyen par Catégorie (Top 10)')
        plt.xlabel('Catégorie')
        plt.ylabel('Score de Recommandation Moyen')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()

        # 7. Score de recommandation moyen par marque
        avg_rec_score_by_brand = df.groupby('main_brand')['rec_score'].mean().nlargest(10)
        plt.figure(figsize=(12, 7))
        avg_rec_score_by_brand.plot(kind='bar', color=sns.color_palette('tab20', 10))
        plt.title('Score de Recommandation Moyen par Marque (Top 10)')
        plt.xlabel('Marque')
        plt.ylabel('Score de Recommandation Moyen')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()

        # 8. Distribution du prix moyen des produits recommandés
        plt.figure(figsize=(10, 6))
        sns.histplot(df['avg_price'], bins=50, kde=True)
        plt.title('Distribution du Prix Moyen des Produits Recommandés')
        plt.xlabel('Prix Moyen')
        plt.ylabel('Fréquence')
        plt.grid(axis='y', alpha=0.75)
        # Limiter l'axe x pour mieux visualiser si nécessaire
        # plt.xlim(0, 500) 
        plt.show()

        print("Visualizations generated.")

    except Exception as e:
        print(f"Error loading or processing data: {e}") 