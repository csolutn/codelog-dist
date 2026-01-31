db = db.getSiblingDB('Codelog'); // DB명을 서비스에 맞게 설정
db.createCollection('Responses');
db.createCollection('Students');
db.createCollection('Sheets');
db.createCollection('Problems');
print("Archive DB: Backup collection initialized.");