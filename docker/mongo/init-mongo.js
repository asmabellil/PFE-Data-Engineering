// Exécuté une seule fois à la création du volume MongoDB.
// Principe du moindre privilège : un utilisateur par usage, aucun service n'utilise le compte root.
const dbName = "jobinsight";
const appDb = db.getSiblingDB(dbName);

appDb.createUser({
  user: process.env.MONGO_PIPELINE_USER,
  pwd: process.env.MONGO_PIPELINE_PASSWORD,
  roles: [{ role: "readWrite", db: dbName }],
});

appDb.createUser({
  user: process.env.MONGO_API_USER,
  pwd: process.env.MONGO_API_PASSWORD,
  roles: [{ role: "readWrite", db: dbName }],
});

// lecture seule : Power BI / MongoDB Compass / analystes
appDb.createUser({
  user: process.env.MONGO_BI_USER,
  pwd: process.env.MONGO_BI_PASSWORD,
  roles: [{ role: "read", db: dbName }],
});

print("JobCompass : utilisateurs MongoDB créés (pipeline, api, bi)");
