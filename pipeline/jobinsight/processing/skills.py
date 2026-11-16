"""Extraction des compétences et technologies (NLP à base de dictionnaire + regex).

Approche : taxonomie contrôlée (nom canonique -> alias regex). Avantages pour le MVP :
explicable, rapide, multilingue (FR / EN / DE) et sans entraînement. La partie IA du projet
(cf. docs/08-ia-ml-dl.md) complète cette approche par des modèles ML/DL.
"""
from __future__ import annotations

import re
from functools import lru_cache

# ------------------------------------------------------------------ technologies
# nom canonique : (catégorie, [alias regex]) – les alias sont en minuscules
TECHNOLOGIES: dict[str, tuple[str, list[str]]] = {
    # Langages
    "Python": ("Langage", [r"python"]),
    "Java": ("Langage", [r"java(?!\s*script)"]),
    "JavaScript": ("Langage", [r"javascript", r"\bjs\b", r"ecmascript"]),
    "TypeScript": ("Langage", [r"typescript"]),
    "C#": ("Langage", [r"c#", r"c sharp", r"\.net core"]),
    "C++": ("Langage", [r"c\+\+"]),
    "C": ("Langage", [r"\bc\b(?![#+])(?= (?:language|programming|developer|and c\+\+))"]),
    "Go": ("Langage", [r"\bgolang\b", r"\bgo\b(?= (?:language|developer|engineer|programming|and|,))"]),
    "Rust": ("Langage", [r"\brust\b"]),
    "PHP": ("Langage", [r"\bphp\b"]),
    "Ruby": ("Langage", [r"\bruby\b(?! on rails)"]),
    "Kotlin": ("Langage", [r"kotlin"]),
    "Swift": ("Langage", [r"\bswift\b"]),
    "Scala": ("Langage", [r"\bscala\b"]),
    "R": ("Langage", [r"\br\b(?= (?:language|programming|studio|and python|,))", r"rstudio"]),
    "SQL": ("Langage", [r"\bsql\b"]),
    "Bash": ("Langage", [r"\bbash\b", r"shell scripting"]),
    "Dart": ("Langage", [r"\bdart\b"]),
    "MATLAB": ("Langage", [r"matlab"]),
    "SAS": ("Langage", [r"\bsas\b(?! platform)"]),
    "ABAP": ("Langage", [r"\babap\b"]),
    "COBOL": ("Langage", [r"cobol"]),
    # Frameworks web / mobile
    "React": ("Framework", [r"react(?:\.?js)?\b(?! native)"]),
    "React Native": ("Framework", [r"react native"]),
    "Angular": ("Framework", [r"angular"]),
    "Vue.js": ("Framework", [r"vue(?:\.?js)?\b"]),
    "Next.js": ("Framework", [r"next\.?js"]),
    "Node.js": ("Framework", [r"node(?:\.?js)?\b"]),
    "Express": ("Framework", [r"express(?:\.?js)?\b"]),
    "Django": ("Framework", [r"django"]),
    "Flask": ("Framework", [r"\bflask\b"]),
    "FastAPI": ("Framework", [r"fastapi"]),
    "Spring": ("Framework", [r"spring(?: boot)?\b"]),
    ".NET": ("Framework", [r"\.net\b", r"asp\.net"]),
    "Laravel": ("Framework", [r"laravel"]),
    "Symfony": ("Framework", [r"symfony"]),
    "Ruby on Rails": ("Framework", [r"ruby on rails", r"\brails\b"]),
    "Flutter": ("Framework", [r"flutter"]),
    "Tailwind CSS": ("Framework", [r"tailwind"]),
    "HTML/CSS": ("Framework", [r"\bhtml5?\b", r"\bcss3?\b"]),
    # Bases de données
    "PostgreSQL": ("Base de données", [r"postgres(?:ql)?"]),
    "MySQL": ("Base de données", [r"mysql", r"mariadb"]),
    "MongoDB": ("Base de données", [r"mongo(?:db)?"]),
    "Redis": ("Base de données", [r"\bredis\b"]),
    "Elasticsearch": ("Base de données", [r"elastic ?search", r"opensearch", r"\belk\b"]),
    "Oracle": ("Base de données", [r"\boracle\b"]),
    "SQL Server": ("Base de données", [r"sql server", r"mssql", r"t-sql"]),
    "Cassandra": ("Base de données", [r"cassandra"]),
    "Neo4j": ("Base de données", [r"neo4j"]),
    "DynamoDB": ("Base de données", [r"dynamodb"]),
    # Data / Big Data
    "Apache Spark": ("Data / Big Data", [r"\bspark\b", r"pyspark"]),
    "Apache Kafka": ("Data / Big Data", [r"kafka"]),
    "Apache Airflow": ("Data / Big Data", [r"airflow"]),
    "Hadoop": ("Data / Big Data", [r"hadoop", r"\bhdfs\b", r"\bhive\b"]),
    "dbt": ("Data / Big Data", [r"\bdbt\b"]),
    "Snowflake": ("Data / Big Data", [r"snowflake"]),
    "BigQuery": ("Data / Big Data", [r"bigquery", r"big query"]),
    "Databricks": ("Data / Big Data", [r"databricks"]),
    "Redshift": ("Data / Big Data", [r"redshift"]),
    "Flink": ("Data / Big Data", [r"\bflink\b"]),
    "Pandas": ("Data / Big Data", [r"pandas"]),
    "NumPy": ("Data / Big Data", [r"numpy"]),
    "ETL": ("Data / Big Data", [r"\betl\b", r"\belt\b"]),
    # BI
    "Power BI": ("BI / Visualisation", [r"power ?bi"]),
    "Tableau": ("BI / Visualisation", [r"\btableau\b(?! de bord)"]),
    "Looker": ("BI / Visualisation", [r"looker"]),
    "Excel": ("BI / Visualisation", [r"\bexcel\b(?! (?:at|in|as))", r"ms excel"]),
    "Qlik": ("BI / Visualisation", [r"qlik"]),
    # IA / ML
    "TensorFlow": ("IA / ML", [r"tensorflow", r"\bkeras\b"]),
    "PyTorch": ("IA / ML", [r"pytorch", r"\btorch\b"]),
    "scikit-learn": ("IA / ML", [r"scikit[- ]?learn", r"sklearn"]),
    "Hugging Face": ("IA / ML", [r"hugging ?face", r"transformers library"]),
    "LangChain": ("IA / ML", [r"langchain"]),
    "OpenAI / LLM APIs": ("IA / ML", [r"openai", r"gpt-?4", r"chatgpt", r"\bllms?\b", r"claude"]),
    "MLflow": ("IA / ML", [r"mlflow"]),
    "Spark MLlib": ("IA / ML", [r"mllib"]),
    # Cloud
    "AWS": ("Cloud", [r"\baws\b", r"amazon web services", r"\bs3\b", r"\bec2\b", r"lambda"]),
    "Azure": ("Cloud", [r"\bazure\b"]),
    "GCP": ("Cloud", [r"\bgcp\b", r"google cloud"]),
    # DevOps
    "Docker": ("DevOps", [r"docker"]),
    "Kubernetes": ("DevOps", [r"kubernetes", r"\bk8s\b", r"\beks\b", r"\baks\b", r"\bgke\b"]),
    "Terraform": ("DevOps", [r"terraform"]),
    "Ansible": ("DevOps", [r"ansible"]),
    "Jenkins": ("DevOps", [r"jenkins"]),
    "GitLab CI": ("DevOps", [r"gitlab"]),
    "GitHub Actions": ("DevOps", [r"github actions"]),
    "Git": ("DevOps", [r"\bgit\b"]),
    "Linux": ("DevOps", [r"linux", r"unix"]),
    "CI/CD": ("DevOps", [r"ci ?/ ?cd", r"continuous integration", r"continuous deployment"]),
    "Prometheus": ("DevOps", [r"prometheus"]),
    "Grafana": ("DevOps", [r"grafana"]),
    # Outils
    "Jira": ("Outil", [r"\bjira\b"]),
    "Figma": ("Outil", [r"figma"]),
    "Salesforce": ("Outil", [r"salesforce"]),
    "SAP": ("Outil", [r"\bsap\b"]),
    "HubSpot": ("Outil", [r"hubspot"]),
    "REST API": ("Outil", [r"rest(?:ful)? ?apis?", r"api design", r"api development"]),
    "GraphQL": ("Outil", [r"graphql"]),
    "Microservices": ("Outil", [r"micro-?services?"]),
}

# ------------------------------------------------------------------ compétences
SKILLS: dict[str, tuple[str, list[str]]] = {
    # techniques / métiers
    "Machine Learning": ("Technique", [r"machine learning", r"apprentissage automatique", r"\bml\b"]),
    "Deep Learning": ("Technique", [r"deep learning", r"apprentissage profond", r"neural network", r"r[ée]seaux? de neurones"]),
    "NLP": ("Technique", [r"\bnlp\b", r"natural language processing", r"traitement du langage"]),
    "Computer Vision": ("Technique", [r"computer vision", r"vision par ordinateur"]),
    "Data Analysis": ("Technique", [r"data analy", r"analyse de donn[ée]es", r"datenanalyse"]),
    "Data Engineering": ("Technique", [r"data engineer", r"data pipeline", r"ing[ée]nierie des donn[ée]es"]),
    "Data Visualization": ("Technique", [r"data visuali", r"dashboard", r"tableaux? de bord", r"reporting"]),
    "Statistics": ("Technique", [r"statisti"]),
    "Data Modeling": ("Technique", [r"data model", r"mod[ée]lisation de donn[ée]es"]),
    "Cloud Architecture": ("Technique", [r"cloud architect", r"cloud infrastructure"]),
    "Cybersecurity": ("Technique", [r"cyber ?security", r"cybers[ée]curit[ée]", r"information security", r"\bsiem\b", r"pentest"]),
    "Testing / QA": ("Technique", [r"\bqa\b", r"quality assurance", r"unit test", r"test automation", r"\btdd\b"]),
    "UX/UI Design": ("Technique", [r"\bux\b", r"\bui\b", r"user experience", r"user interface"]),
    "Mobile Development": ("Technique", [r"\bios\b", r"android", r"mobile app"]),
    "Web Development": ("Technique", [r"front-?end", r"back-?end", r"full-?stack", r"web develop"]),
    "SEO": ("Technique", [r"\bseo\b", r"\bsem\b"]),
    "Digital Marketing": ("Technique", [r"digital marketing", r"marketing digital", r"growth", r"google ads"]),
    "Project Management": ("Technique", [r"project manag", r"gestion de projet", r"projektmanagement", r"\bpmp\b"]),
    "Agile / Scrum": ("Technique", [r"\bagile\b", r"scrum", r"kanban", r"m[ée]thodes? agiles?"]),
    "Accounting / Finance": ("Technique", [r"accounting", r"comptabilit", r"buchhaltung", r"financial analy"]),
    "Sales": ("Technique", [r"\bb2b\b", r"business development", r"lead generation", r"\bcrm\b"]),
    "Customer Support": ("Technique", [r"customer support", r"customer service", r"service client", r"kundenservice"]),
    # comportementales (soft skills)
    "Communication": ("Comportementale", [r"communicat", r"kommunikat"]),
    "Travail en équipe": ("Comportementale", [r"team ?work", r"team player", r"travail en [ée]quipe", r"teamf[äa]hig", r"collaborat"]),
    "Leadership": ("Comportementale", [r"leadership", r"f[üu]hrungs"]),
    "Résolution de problèmes": ("Comportementale", [r"problem[- ]solving", r"r[ée]solution de probl[eè]mes", r"analytical skills", r"esprit d.analyse"]),
    "Autonomie": ("Comportementale", [r"autonom", r"self-?motivated", r"self-?starter", r"selbstst[äa]ndig", r"independently"]),
    "Rigueur": ("Comportementale", [r"attention to detail", r"detail-oriented", r"rigueur", r"rigoureu"]),
    "Adaptabilité": ("Comportementale", [r"adaptab", r"flexib"]),
    "Créativité": ("Comportementale", [r"creativ", r"cr[ée]ativit", r"kreativ"]),
    "Gestion du temps": ("Comportementale", [r"time management", r"gestion du temps", r"prioriti"]),
    "Anglais": ("Langue", [r"english", r"anglais", r"englisch"]),
    "Français": ("Langue", [r"french", r"fran[cç]ais", r"franz[öo]sisch"]),
    "Allemand": ("Langue", [r"german\b", r"allemand", r"deutsch"]),
    "Espagnol": ("Langue", [r"spanish", r"espagnol", r"spanisch"]),
}


@lru_cache(maxsize=2)
def _compiled(kind: str):
    table = TECHNOLOGIES if kind == "tech" else SKILLS
    out = []
    for name, (category, patterns) in table.items():
        # (?<![\w.+#-]) : évite de matcher "java" dans "javafx" ou "go" dans "google"
        # compétences : motifs "préfixes" (autonom -> autonomie / autonomous) -> \w* final
        suffix = r"\w*" if kind == "skill" else ""
        pattern = "|".join(f"(?:{p}){suffix}" for p in patterns)
        out.append((name, category, re.compile(rf"(?<![\w])(?:{pattern})(?![\w+#])", re.IGNORECASE)))
    return out


def extract(text: str | None, kind: str = "tech") -> list[str]:
    if not text:
        return []
    found = [name for name, _cat, rx in _compiled(kind) if rx.search(text)]
    return sorted(set(found))


def extract_technologies(text: str | None) -> list[str]:
    return extract(text, "tech")


def extract_skills(text: str | None) -> list[str]:
    return extract(text, "skill")


def technology_category(name: str) -> str | None:
    return TECHNOLOGIES.get(name, (None,))[0]


def skill_category(name: str) -> str | None:
    return SKILLS.get(name, (None,))[0]
