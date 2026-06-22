# GUIDE: วิธีดู Database ของ Docker ผ่าน MySQL Workbench

โปรเจกต์นี้ถ้ารันด้วยคำสั่ง:
------------------------------
docker compose up -d --build
------------------------------
ระบบจะใช้ Database ที่อยู่ใน Docker container ไม่ใช่ MySQL Local instance ของเครื่อง Windows
ดังนั้นถ้าเปิด MySQL Workbench แล้วเข้า connection เดิมชื่อประมาณ:
Local instance MySQL80
อันนั้นจะไม่ใช่ DB ที่เว็บ Docker ใช้อยู่
ต้องสร้าง connection ใหม่สำหรับ Docker DB แยกต่างหาก

1. เปิด port ของ DB container
---
ให้เปิดไฟล์:
## docker-compose.yml
หา service ชื่อ db แล้วเพิ่ม ports แบบนี้:

db:
ports:
- "127.0.0.1:3307:3306" (port นี้สำหรับ localhost)  
   ถ้าอยากใช้คอมเครื่องอื่นเข้ามาดู db เครื่อง server ต้องใช้ (- "0.0.0.0:3307:3306")

### ตัวอย่าง:
services:
db:
image: mariadb:11
ports:
- "127.0.0.1:3307:3306"

### ถ้าอยากใช้คอมเครื่องอื่นเข้ามาดู db เครื่อง server ต้องใช้ (- "0.0.0.0:3307:3306")


เหตุผลที่ใช้ port 3307:
* port 3306 มักถูก MySQL ที่ลงบน Windows ใช้อยู่แล้ว
* Docker DB ข้างในยังใช้ 3306 เหมือนเดิม
* แต่เรา map ออกมาที่เครื่องเป็น 3307 เพื่อให้ MySQL Workbench ต่อเข้าได้


2. รัน Docker ใหม่
---
หลังแก้ docker-compose.yml แล้วให้รัน:
----------------------------
docker compose up -d --build
----------------------------
ถ้า port ยังไม่เปลี่ยนหรือยังต่อไม่ได้ ค่อยใช้:

docker compose down
docker compose up -d --build


## สำคัญมาก:
ห้ามใช้คำสั่งนี้ถ้าไม่อยากลบข้อมูล DB ใน Docker:
----------------------
docker compose down -v
----------------------
เพราะ -v จะลบ Docker volume และทำให้ข้อมูล database ใน Docker หาย


3. ตั้งค่า MySQL Workbench (ขั้นตอนนี้อยู่ในโปรแกรม MySQL Workbench)
---
เปิด MySQL Workbench แล้วกด + เพื่อสร้าง connection ใหม่

## ตั้งค่าประมาณนี้: (ถ้าของจะเชื่อมเพื่อดูของ server ที่รัน app ต้องใช้ ip ของเครื่อง server เช่น 192.168.1.xxx)
Connection Name: Docker inventory_db
Hostname: 127.0.0.1     <-------อันนี้คือ ip localhost เครื่องอื่นจะเชื่อมต่อ db ไม่ได้
Port: 3307
Username: root
Password: ใช้ค่าจาก MYSQL_ROOT_PASSWORD ในไฟล์ .env
Default Schema: inventory_db

จากนั้นกด Test Connection

ถ้าผ่านแล้วให้กด OK แล้วเข้า connection นี้เพื่อดู table ได้เลย


4. ต้องใช้ connection ไหน (ขั้นตอนนี้อยู่ในโปรแกรม MySQL Workbench)
---
ถ้าต้องการดูข้อมูลที่เว็บ Docker ใช้งานจริง ให้ใช้ connection นี้:
Docker inventory_db
Host: 127.0.0.1
Port: 3307



5. สรุปภาพรวม
---
เว็บที่รันด้วย Docker จะทำงานประมาณนี้:

Browser
→ app container
→ db container
→ Docker volume

ส่วน MySQL Workbench จะดู Docker DB ได้ผ่าน port ที่ map ไว้:

Docker DB container port 3306
→ map ออกมาเป็น 127.0.0.1:3307
→ MySQL Workbench ต่อเข้า 127.0.0.1 port 3307


6. เรื่อง password
---
Database ยังมี password อยู่

ถ้า MySQL Workbench กดเข้าได้เลยโดยไม่ถาม password แปลว่า Workbench เคยจำ password ไว้แล้ว ไม่ใช่ว่า DB ไม่มี password

ถ้าอยากให้ถาม password ใหม่:

* ไปที่ Manage Connections
* เลือก connection Docker inventory_db
* Clear password / Clear Vault
* ปิด Workbench แล้วเปิดใหม่
* เข้า connection อีกครั้ง ระบบควรถาม password


7. คำสั่งที่ใช้บ่อย
---
# เปิดระบบ Docker:
docker compose up -d --build

# หยุดระบบ แต่ข้อมูล DB ยังอยู่:
docker compose down

# ดู container ที่กำลังรัน:
docker compose ps

# ดู log:
docker compose logs -f app

# ล้าง DB ทิ้งทั้งหมด ใช้เฉพาะตอนทดสอบเท่านั้น:
docker compose down -v

ระวัง:
คำสั่ง docker compose down -v จะลบ database ใน Docker volume ทั้งหมด

8. วิธีเช็กว่า Workbench ดูถูก DB แล้ว

---

ให้เปิดเว็บแล้วเพิ่มข้อมูลทดสอบ 1 รายการ
จากนั้นเปิด MySQL Workbench connection:
Docker inventory_db
แล้วลอง query:

SELECT * FROM inventory_db.production_plans;

ถ้าเห็นข้อมูลเดียวกับหน้าเว็บ แปลว่าต่อถูก DB แล้ว
ถ้าหน้าเว็บมีข้อมูล แต่ Workbench ไม่เห็นข้อมูล แปลว่าน่าจะเปิดผิด connection เช่นไปเปิด Local instance MySQL80 แทน Docker inventory_db
