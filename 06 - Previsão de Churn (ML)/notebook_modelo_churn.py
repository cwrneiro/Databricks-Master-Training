# Databricks notebook source
# MAGIC %md
# MAGIC # Exercício 6 — Modelo de churn
# MAGIC Treina um modelo que estima a **probabilidade de churn** de cada cliente, registra no Unity Catalog e grava uma **tabela de scores** pronta para os dashboards e o app.
# MAGIC
# MAGIC **Fonte:** `dbacademy.churn.feature_churn` (features comportamentais).
# MAGIC **Cria no seu schema:** `modelo_churn` (o modelo) e `churn_scores` (a tabela de scores).
# MAGIC
# MAGIC Anexe o cluster `dbacademy_workshop_cluster` e rode as células em ordem.

# COMMAND ----------

# MAGIC %pip install scikit-learn mlflow

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 1 — Configure o seu schema
# MAGIC Selecione o seu schema pessoal no widget abaixo.

# COMMAND ----------

dbutils.widgets.text("schema", "", "Seu schema")
SCHEMA = dbutils.widgets.get("schema")
SCHEMA_FQN = f"dbacademy.{SCHEMA}"
MODEL  = f"{SCHEMA_FQN}.modelo_churn"
SCORES = f"{SCHEMA_FQN}.churn_scores"
print("Modelo  ->", MODEL)
print("Scores  ->", SCORES)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 2 — Treinar o modelo
# MAGIC Um `GradientBoostingClassifier` sobre as features comportamentais. Alvo = `churn_flag`.

# COMMAND ----------

import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

df = spark.table("dbacademy.churn.feature_churn").toPandas()
y = df["churn_flag"].astype(int)
X = df.drop(columns=["id_cliente", "churn_flag"])

cat = ["segmento", "nome_plano"]
num = [c for c in X.columns if c not in cat]

pre = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
    ("num", "passthrough", num),
])
pipe = Pipeline([("pre", pre), ("clf", GradientBoostingClassifier(random_state=42))])

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
pipe.fit(Xtr, ytr)
auc = roc_auc_score(yte, pipe.predict_proba(Xte)[:, 1])
print(f"AUC (teste): {auc:.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 3 — Registrar no Unity Catalog
# MAGIC Registramos um modelo **pyfunc** que devolve a **probabilidade** de churn.

# COMMAND ----------

import mlflow

class ChurnProb(mlflow.pyfunc.PythonModel):
    def __init__(self, model):
        self.model = model
    def predict(self, context, model_input):
        return self.model.predict_proba(model_input)[:, 1]

mlflow.set_registry_uri("databricks-uc")
signature = mlflow.models.infer_signature(X, pipe.predict_proba(X)[:, 1])

with mlflow.start_run(run_name="modelo_churn"):
    mlflow.log_metric("auc", auc)
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=ChurnProb(pipe),
        signature=signature,
        input_example=X.head(3),
        registered_model_name=MODEL,
    )
print("Modelo registrado:", MODEL)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 4 — Gerar a tabela de scores
# MAGIC Pontuamos todos os clientes e classificamos em **faixa de risco** + o **sinal principal** por trás do risco. Essa tabela alimenta os dashboards e o app.

# COMMAND ----------

scores = df[["id_cliente", "segmento", "nome_plano", "preco_mensal"]].copy()
scores["prob_churn"] = pipe.predict_proba(X)[:, 1]

# faixa de risco (limiares fixos, interpretáveis)
def faixa(p):
    return "Alto" if p >= 0.50 else ("Médio" if p >= 0.25 else "Baixo")
scores["faixa_risco"] = scores["prob_churn"].apply(faixa)

# sinal principal: o fator de risco que mais se destaca (z-score orientado ao risco)
z = (X[num] - X[num].mean()) / X[num].std(ddof=0)
sinais = pd.DataFrame({
    "Baixo uso":          -z["uso_medio"],
    "Inadimplência":       z["pct_faturas_atraso"],
    "Insatisfação (CSAT)": -z["csat_medio"],
    "Detrator (NPS)":     -z["nps_medio"],
})
scores["fator_principal"] = sinais.idxmax(axis=1)
scores["prob_churn"] = scores["prob_churn"].astype(float).round(4)

spark.createDataFrame(scores).write.mode("overwrite").saveAsTable(SCORES)
print("Tabela de scores gravada:", SCORES)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Confira o resultado

# COMMAND ----------

print(f"AUC (teste): {auc:.3f}")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC     faixa_risco,
# MAGIC     COUNT(*) AS clientes,
# MAGIC     ROUND(AVG(prob_churn), 3) AS prob_media
# MAGIC FROM dbacademy.${schema}.churn_scores
# MAGIC GROUP BY faixa_risco
# MAGIC ORDER BY prob_media DESC


# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC     *
# MAGIC FROM dbacademy.${schema}.churn_scores
# MAGIC ORDER BY prob_churn DESC
# MAGIC LIMIT 10
