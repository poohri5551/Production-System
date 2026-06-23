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
docker compose exec db sh -c 'mariadb -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" < /tmp/inventory_db.sql'
------------------------------------------------
ถ้าไม่มี error แปลว่า import สำเร็จ


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