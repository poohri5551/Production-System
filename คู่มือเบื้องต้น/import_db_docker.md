##### คำสั่งที่ใช้ในการนำเข้า (IMPORT) Database กรณีที่ใช้คำสั่ง docker compose down -v #####

1. เช็ค container ก่อน
------------------------------------------------
docker compose ps
------------------------------------------------

ควรเห็น db เป็น running
ถ้ายังไม่ได้รัน ให้รันก่อน:

------------------------------------------------
docker compose up -d --build
------------------------------------------------


2. Copy ไฟล์ SQL เข้า DB container
ต้องอยู่ในโฟลเดอร์นี้ก่อน:
------------------------------------------------
cd C:\Users\User\Desktop\project_for_nas_server
แล้วรัน:
docker compose cp .\inventory_db.sql db:/tmp/inventory_db.sql
------------------------------------------------


3. Import SQL เข้า database
ลองคำสั่งนี้ก่อน:
------------------------------------------------
docker compose exec -T db sh -lc 'DB_PASS="${MARIADB_ROOT_PASSWORD:-$MYSQL_ROOT_PASSWORD}"; DB_NAME="${MARIADB_DATABASE:-$MYSQL_DATABASE}"; mariadb -uroot -p"$DB_PASS" "$DB_NAME" < /tmp/inventory_db.sql'
------------------------------------------------



## ตรวจข้อมูลว่า import จริงมั้ย
$sql = @'
SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL SELECT 'parts', COUNT(*) FROM parts
UNION ALL SELECT 'production_plans', COUNT(*) FROM production_plans
UNION ALL SELECT 'setting_dies', COUNT(*) FROM setting_dies
UNION ALL SELECT 'qc_inspections', COUNT(*) FROM qc_inspections
UNION ALL SELECT 'production_starts', COUNT(*) FROM production_starts
UNION ALL SELECT 'production_finishes', COUNT(*) FROM production_finishes
UNION ALL SELECT 'notifications', COUNT(*) FROM notifications
UNION ALL SELECT 'forecast_entries', COUNT(*) FROM forecast_entries
UNION ALL SELECT 'forecast_monthly_values', COUNT(*) FROM forecast_monthly_values
UNION ALL SELECT 'forecast_months', COUNT(*) FROM forecast_months
UNION ALL SELECT 'forecast_sync_state', COUNT(*) FROM forecast_sync_state;

SELECT username, role FROM users;

SELECT COUNT(*) AS obsolete_plan_no_columns
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME = 'plan_no';

SELECT COUNT(*) AS lot_no_columns
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME = 'lot_no';
'@

$sql | docker compose exec -T db sh -lc 'DB_PASS="${MARIADB_ROOT_PASSWORD:-$MYSQL_ROOT_PASSWORD}"; DB_NAME="${MARIADB_DATABASE:-$MYSQL_DATABASE}"; mariadb -uroot -p"$DB_PASS" "$DB_NAME" --table'


## ต้องได้ผลแบบนี้
users                      1
parts                      0
production_plans           0
setting_dies               0
qc_inspections             0
production_starts          0
production_finishes        0
notifications              0

forecast_entries           0
forecast_monthly_values    0
forecast_months            0
forecast_sync_state        0

obsolete_plan_no_columns   0
lot_no_columns             6



## ถ้าต้องการให้ FORECAST กลับมาจาก Excel

รัน Initial Sync:
-----------------------------------------------------
docker compose --profile forecast-sync run --rm forecast-sync python -c "from scripts.forecast_sync_worker import run_once; print(run_once('/forecast_source/1.FORCASE CENTOR.xlsx'))"
-----------------------------------------------------------


## หลังจากนั้นเปิด worker อัตโนมัติกลับ:
-------------------------------------
docker compose --profile forecast-sync up -d forecast-sync
--------------------------------------













4. Restart app
docker compose restart app
แล้วเปิดเว็บ:
http://localhost:5000/app


--------------------------------------------------------------------
cd "path\to\project_for_nas_server"

docker compose down -v

docker compose up -d db

Start-Sleep -Seconds 15

docker compose cp .\inventory_db.sql db:/tmp/inventory_db.sql

docker compose exec db sh -c 'mariadb -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" < /tmp/inventory_db.sql'

docker compose up -d --build app
--------------------------------------------------------------------