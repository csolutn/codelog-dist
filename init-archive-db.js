db = db.getSiblingDB('Codelog');
db.createCollection('Responses'); // 아카이브용 Responses만 존재
print("Archive DB: Backup collection initialized.");