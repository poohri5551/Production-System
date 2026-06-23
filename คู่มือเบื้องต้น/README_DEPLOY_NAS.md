# Deploy บน NAS ด้วย Docker Compose

เอกสารนี้สำหรับนำโปรเจกต์ Flask + Vue + MariaDB/MySQL ไปรันบน NAS เช่น Synology, QNAP หรือ Linux NAS ที่รองรับ Docker Compose / Container Manager

## ภาพรวม

- `app` รัน Flask ผ่าน gunicorn ที่ port `5000`
- `db` รัน MariaDB 11.4 และเก็บข้อมูลใน Docker volume `db_data`
- Vue production build ถูก build ใน Dockerfile แล้ว Flask serve ที่ `/app`
- legacy route `/` และ `/mainpage` ยังอยู่เหมือนเดิม
- API ยังอยู่ใต้ `/api/*`
- ไฟล์ upload ใน `static/uploads` ถูก mount เป็น Docker volume `uploads_data` เพื่อไม่หายตอน rebuild container
- compose ไม่เปิด database port ออกนอกเครื่อง NAS

ถ้าต้องการใช้ MySQL แทน MariaDB ให้เปลี่ยน image ใน `docker-compose.yml` จาก `mariadb:11.4` เป็น `mysql:8` แล้วทดสอบ import และ smoke test อีกครั้ง

## 1. Copy project ไป NAS

เลือกวิธีใดวิธีหนึ่ง:

```bash
# ผ่าน git บน NAS
git clone <repo-url> inventory-production
cd inventory-production
```

หรือ copy โฟลเดอร์โปรเจกต์ผ่าน SMB, File Station, QNAP File Station หรือ rsync ไปยังโฟลเดอร์บน NAS เช่น:

```text
/volume1/docker/inventory-production
```

อย่า copy `frontend/node_modules`, `.venv`, `__pycache__`, หรือ `.env` จริงจากเครื่อง dev ถ้าไม่จำเป็น

## 2. สร้างไฟล์ .env

ในโฟลเดอร์โปรเจกต์บน NAS:

```bash
cp .env.example .env
```

แก้ค่าใน `.env` ให้เป็นรหัสจริง:

```env
DB_HOST=db
DB_PORT=3306
DB_USER=inventory_user
DB_PASSWORD=<strong-db-password>
DB_NAME=inventory_db
FLASK_SECRET_KEY=<long-random-secret>
FLASK_DEBUG=0

MYSQL_DATABASE=inventory_db
MYSQL_USER=inventory_user
MYSQL_PASSWORD=<strong-db-password>
MYSQL_ROOT_PASSWORD=<strong-root-password>
```

ข้อสำคัญ:

- `DB_HOST` ต้องเป็น `db` ให้ตรงกับชื่อ service ใน `docker-compose.yml`
- `DB_USER`, `DB_PASSWORD`, `DB_NAME` ต้องตรงกับ `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
- `FLASK_SECRET_KEY` ต้องเป็นค่าสุ่มยาวและเปลี่ยนจากตัวอย่าง
- อย่า commit หรือแชร์ไฟล์ `.env` จริง

## 3. Build และ run บน NAS

รันจากโฟลเดอร์โปรเจกต์:

```bash
docker compose up -d --build
```

ดูสถานะ:

```bash
docker compose ps
```

ดู log ของ Flask/gunicorn:

```bash
docker compose logs -f app
```

เข้าเว็บ:

```text
http://NAS-IP:5000/app
```

ตรวจ legacy route:

```text
http://NAS-IP:5000/
http://NAS-IP:5000/mainpage
```

## 4. Export database จากเครื่องเดิม

ถ้าเครื่องเดิมเป็น MySQL/MariaDB ปกติ:

```bash
mysqldump -u root -p inventory_db > inventory_db.sql
```

ถ้า database เดิมอยู่ใน container:

```bash
docker exec <old-db-container> mysqldump -u root -p inventory_db > inventory_db.sql
```

ย้ายไฟล์ `inventory_db.sql` ไปไว้ในโฟลเดอร์โปรเจกต์บน NAS

## 5. Import .sql เข้า database container

เริ่มเฉพาะ database ก่อน ถ้ายังไม่ได้รัน:

```bash
docker compose up -d db
```

รอให้ database พร้อม แล้ว import:

```bash
docker compose exec -T db sh -c 'mariadb -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < inventory_db.sql
```

จากนั้น restart app:

```bash
docker compose restart app
```

ถ้าเปลี่ยนไปใช้ image `mysql:8` ให้ใช้ client `mysql` แทน:

```bash
docker compose exec -T db sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < inventory_db.sql
```

## 6. Backup database

แนะนำให้ backup เป็น SQL dump:

```bash
mkdir -p backups
docker compose exec -T db sh -c 'mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > backups/inventory_db_$(date +%F).sql
```

ถ้าใช้ `mysql:8`:

```bash
mkdir -p backups
docker compose exec -T db sh -c 'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > backups/inventory_db_$(date +%F).sql
```

เก็บไฟล์ backup ไว้นอก Docker volume ด้วย เช่น NAS shared folder หรือ external backup

## 7. Bootstrap admin ใน container

ใช้เฉพาะจาก server shell เท่านั้น ห้ามทำเป็น public endpoint:

```bash
docker compose exec app python scripts/bootstrap_admin.py --username admin --password "StrongPasswordHere"
```

ถ้ามี Admin อยู่แล้ว script จะ skip โดย default ถ้าจำเป็นต้องสร้าง Admin เพิ่มจริง ๆ:

```bash
docker compose exec app python scripts/bootstrap_admin.py --username admin2 --password "StrongPasswordHere" --force-create-user
```

## 8. Reset password

ระบบมี Admin Reset Password ผ่านหน้า Users และ API เดิมอยู่แล้ว ให้ใช้ flow นั้นเป็นหลัก

ตอนนี้ repo ยังไม่มี server CLI script ชื่อ `scripts/reset_user_password.py` สำหรับ reset password จาก shell ถ้าจะเพิ่มในอนาคตให้เป็น script ที่รันใน container เท่านั้น และห้ามเปิดเป็น route/API สาธารณะ

## 9. Restart และ stop

Restart เฉพาะ app:

```bash
docker compose restart app
```

Stop container แต่เก็บ volume:

```bash
docker compose down
```

ลบ volume จะทำให้ database และ upload หาย จึงห้ามใช้ `docker compose down -v` เว้นแต่มี backup แล้วและตั้งใจลบจริง

## 10. Local Docker test

สร้าง `.env` ก่อน แล้วตรวจ compose syntax:

```bash
cp .env.example .env
# แก้รหัสใน .env ก่อน
docker compose config
```

รันทดสอบ local:

```bash
docker compose up -d --build
docker compose logs -f app
```

เปิด:

```text
http://localhost:5000/app
```

ตรวจ API ตามสถานะ session:

```bash
curl -i http://localhost:5000/api/me
```

ถ้ายังไม่ login ควรได้ `401` พร้อม `auth_required`

## 11. Smoke tests ที่ควรรัน

บนเครื่อง dev ก่อน deploy:

```powershell
python -m py_compile app.py
python scripts/phase8_http_smoke.py
python scripts/users_smoke_test.py
python scripts/session_security_smoke_test.py
python scripts/admin_safety_smoke_test.py
python scripts/reset_password_smoke_test.py
npm.cmd --prefix .\frontend run build
```

หมายเหตุ: smoke tests ที่แตะ database ต้องตั้ง `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` ให้ชี้ไป database ทดสอบที่มี schema พร้อมก่อน

## 12. Security notes

- ใช้รหัสผ่าน database ที่แข็งแรง
- เปลี่ยน `FLASK_SECRET_KEY` จริงทุก environment
- อย่า commit `.env` จริง
- อย่าเปิด port database ออก internet ถ้าไม่จำเป็น
- backup database เป็นประจำ
- ก่อน upgrade image หรือแก้ compose ให้ export SQL backup ก่อน
