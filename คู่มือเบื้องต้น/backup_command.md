# Backup / Export Commands

## 1. Backup ทั้งหมด: DB SQL + Uploads + DB Excel

# powershell
---------------------------------------------------------------------------------------------------
cd "C:\Users\User\Desktop\project_for_nas_server"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = ".\backups\$ts"
$containerExcelDir = "/app/backups/$ts/db_excel"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
New-Item -ItemType Directory -Force -Path "$backupDir\db_excel" | Out-Null

docker compose exec -T db sh -c 'mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > "$backupDir\inventory_db.sql"

docker compose cp app:/app/static/uploads "$backupDir\uploads"

docker compose exec -T -e EXPORT_EXCEL_DIR="$containerExcelDir" app python scripts/export_db_to_excel.py

Get-ChildItem -Recurse $backupDir
---------------------------------------------------------------------------------------------------

ผลลัพธ์:

```text
backups/
  YYYYMMDD_HHMMSS/
    inventory_db.sql
    uploads/
    db_excel/
      database_export_YYYYMMDD_HHMMSS.xlsx
```

---

## 2. Backup เฉพาะ DB SQL

```powershell
cd "C:\Users\User\Desktop\project_for_nas_server"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = ".\backups\$ts"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

docker compose exec -T db sh -c 'mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > "$backupDir\inventory_db.sql"

Get-ChildItem $backupDir
```

---

## 3. Export เฉพาะ DB Excel

```powershell

cd "C:\Users\User\Desktop\project_for_nas_server"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$excelDir = ".\backups\$ts\db_excel"
$containerExcelDir = "/app/backups/$ts/db_excel"

New-Item -ItemType Directory -Force -Path $excelDir | Out-Null

docker compose exec -T -e EXPORT_EXCEL_DIR="$containerExcelDir" app python scripts/export_db_to_excel.py

Get-ChildItem -Recurse ".\backups\$ts"

```

ไฟล์จะอยู่ที่:

```text
export_excel/
  database_export_YYYYMMDD_HHMMSS.xlsx
```

---

## 4. Backup เฉพาะ Uploads / รูป

```powershell
cd "C:\Users\User\Desktop\project_for_nas_server"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = ".\backups\$ts"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

docker compose cp app:/app/static/uploads "$backupDir\uploads"

Get-ChildItem -Recurse $backupDir
```

---

## 5. ลบโฟลเดอร์ backups หลังนำไปสำรองที่อื่นแล้ว

```powershell
cd "C:\Users\User\Desktop\project_for_nas_server"

Remove-Item .\backups -Recurse -Force
```

---

## หมายเหตุ

* `backups/` ใช้สำหรับ backup จริง เช่น DB SQL และ uploads
* `export_excel/` ใช้สำหรับ export DB เป็น Excel เพื่อเปิดดูข้อมูล
* ไฟล์ใน `backups/` และ `export_excel/` ไม่ควร commit ขึ้น Git
* ก่อนลบ `backups/` ต้องแน่ใจว่า copy ไปเก็บที่อื่นแล้ว
