## ใช้สำหรับดึงรูปออกมาจาก docker volume แล้วเอาไปเก็บไว้สักทีที่จะ backup
----------------------------------------------------------
docker compose cp app:/app/static/uploads .\uploads_export
----------------------------------------------------------

## คำสั่งลบ folder ที่ดึงมาจาก docker (ใช้หลังจากก๊อปปี้รูปไป backup แล้ว)
Remove-Item .\uploads_export -Recurse -Force



###### Backup Guide สำหรับ Docker Project #######

คู่มือนี้ใช้สำหรับ backup ข้อมูลสำคัญของระบบที่รันด้วย Docker Compose
สิ่งที่ต้อง backup มี 2 ส่วนหลัก:

1. Database (`inventory_db.sql`)
2. รูปภาพ / ไฟล์ upload (`uploads`)

> สำคัญ: ต้อง backup ทั้ง 2 อย่างคู่กัน เพราะ database เก็บชื่อไฟล์รูปไว้ ส่วนไฟล์รูปจริงอยู่ใน uploads

---

## 1. เข้าโฟลเดอร์โปรเจกต์

ให้เปิด PowerShell แล้วเข้า root project ที่มีไฟล์ `docker-compose.yml`

```powershell
cd "C:\Users\User\Desktop\project_for_nas_server"
```

---

## 2. สร้างโฟลเดอร์ backup ตามวันเวลา

```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force ".\backups\$ts"
```

ตัวอย่างผลลัพธ์:

```text
backups/
  20260622_104500/
```

---

## 3. Backup Database เป็นไฟล์ `.sql`

```powershell
docker compose exec -T db sh -c 'mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > ".\backups\$ts\inventory_db.sql"
```

หลังรันเสร็จ จะได้ไฟล์:

```text
backups/<วันเวลา>/inventory_db.sql
```

ไฟล์นี้คือ backup database ทั้งหมดของระบบ

---

## 4. Backup รูปภาพ / uploads

```powershell
docker compose cp app:/app/static/uploads ".\backups\$ts\uploads"
```

หลังรันเสร็จ จะได้โฟลเดอร์:

```text
backups/<วันเวลา>/uploads
```

ข้างในจะเป็นรูปภาพหรือไฟล์ upload ทั้งหมดที่ user เคย upload เข้าเว็บ

---

## 5. เช็กไฟล์ backup

```powershell
Get-ChildItem ".\backups\$ts"
```

ควรเห็นประมาณนี้:

```text
inventory_db.sql
uploads
```

---

###### ชุดคำสั่ง Backup ทั้งหมดแบบใช้งานจริง ######

```powershell
cd "C:\Users\User\Desktop\project_for_nas_server"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force ".\backups\$ts"

docker compose exec -T db sh -c 'mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > ".\backups\$ts\inventory_db.sql"

docker compose cp app:/app/static/uploads ".\backups\$ts\uploads"

Get-ChildItem ".\backups\$ts"
```
## หลังจาก นำ folder : backups ไปทำสำเนาไว้ที่อื่นแล้ว ก็สามารถลบ folder นี้ที่อยู่ในไฟล์ project ได้เลย
Remove-Item .\backups -Recurse -Force
---




## ผลลัพธ์ที่ควรได้

```text
backups/
  20260622_104500/
    inventory_db.sql
    uploads/
      image1.png
      image2.jpg
      ...
```

---

## คำเตือนสำคัญ

ห้ามใช้คำสั่งนี้ถ้าไม่ต้องการลบข้อมูล database:

```powershell
docker compose down -v
```

เพราะ `-v` จะลบ Docker volume ซึ่งอาจทำให้ข้อมูล database และ uploads หายได้

ถ้าต้องการหยุดระบบเฉย ๆ ให้ใช้:

```powershell
docker compose down
```

---

## ควรเก็บ backup ไว้ที่ไหน

หลัง backup เสร็จ ควร copy โฟลเดอร์ใน `backups/<วันเวลา>` ไปเก็บที่อื่น เช่น:

* External Drive
* NAS backup folder
* Google Drive / OneDrive
* เครื่อง backup แยก

ตัวอย่างโฟลเดอร์ที่ต้องเก็บ:

```text
backups/20260622_104500/
```

ในโฟลเดอร์นี้ต้องมีทั้ง:

```text
inventory_db.sql
uploads/
```

---

## สรุป

ทุกครั้งที่ backup ให้เก็บคู่กันเสมอ:

```text
Database  = inventory_db.sql
Uploads   = uploads/
```

ถ้ามีแค่ database แต่ไม่มี uploads รูปจะเปิดไม่ได้
ถ้ามีแค่ uploads แต่ไม่มี database จะไม่รู้ว่ารูปไหนผูกกับข้อมูลรายการไหน
